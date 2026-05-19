#!/usr/bin/env python3
"""
MiMo API 兼容性代理服务器

透明代理 MiMo API 请求，自动修复兼容性问题。
支持 OpenAI 和 Anthropic 两种协议格式。

v1.1.0: 支持推理内容缓存，回放历史时填入真实的 reasoning_content。

用法：
    python server.py [--port 9090] [--host 127.0.0.1] [--api-key KEY] [--api-base URL]

环境变量：
    MIMO_API_KEY          MiMo API 密钥
    MIMO_API_BASE         MiMo API 地址（默认：https://token-plan-cn.xiaomimimo.com/v1）
    MIMO_PROXY_HOST       代理监听地址（默认：127.0.0.1）
    MIMO_PROXY_PORT       代理端口（默认：9090）
    MIMO_LOG_LEVEL        日志级别（默认：INFO）
    MIMO_CACHE_FILE       缓存文件路径（默认：reasoning_cache.json）
    MIMO_CACHE_MAX_AGE    缓存过期时间秒数（默认：86400）
    MIMO_CACHE_DISABLED   设为 1 禁用缓存
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from config import (
    LOG_FILE,
    LOG_LEVEL,
    MIMO_API_BASE,
    MIMO_API_KEY,
    PROXY_HOST,
    PROXY_PORT,
    REASONING_MODELS,
)
from patches import patch_request, store_reasoning_from_response
from reasoning_cache import ReasoningCache

# ── 日志配置 ──────────────────────────────────────────────────────────────

log_handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
if LOG_FILE:
    log_handlers.append(logging.FileHandler(LOG_FILE))

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=log_handlers,
)
logger = logging.getLogger("mimo-compat")

# ── 推理缓存 ──────────────────────────────────────────────────────────────

CACHE_DISABLED = os.getenv("MIMO_CACHE_DISABLED", "0") == "1"
CACHE_FILE = os.getenv("MIMO_CACHE_FILE", "reasoning_cache.json")
CACHE_MAX_AGE = int(os.getenv("MIMO_CACHE_MAX_AGE", "86400"))

reasoning_cache: ReasoningCache | None = None

if not CACHE_DISABLED:
    reasoning_cache = ReasoningCache(
        cache_file=CACHE_FILE,
        max_age_seconds=CACHE_MAX_AGE,
        persist=True,
    )
    logger.info(f"Reasoning cache enabled: {CACHE_FILE} (max_age={CACHE_MAX_AGE}s)")
else:
    logger.info("Reasoning cache disabled")

# ── FastAPI 应用 ──────────────────────────────────────────────────────────

app = FastAPI(
    title="MiMo API Compat Proxy",
    description="透明修复小米 MiMo API 兼容性问题的代理服务器",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 全局状态 ──────────────────────────────────────────────────────────────

stats = {
    "requests": 0,
    "patched": 0,
    "cache_filled": 0,
    "errors": 0,
    "start_time": time.time(),
}

# ── 辅助函数 ──────────────────────────────────────────────────────────────


def get_api_key(request: Request) -> str:
    """从请求头或环境变量获取 API Key"""
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return MIMO_API_KEY


def get_api_base(request: Request) -> str:
    """获取 API 基础地址"""
    return request.headers.get("x-mimo-api-base", MIMO_API_BASE)


def should_patch(body: dict) -> bool:
    """判断是否需要补丁"""
    messages = body.get("messages", [])
    for msg in messages:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            if "reasoning_content" not in msg:
                return True
    return False


def build_headers(request: Request, api_key: str) -> dict:
    """构建转发请求头"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    for header in ["user-agent", "accept", "x-request-id"]:
        if header in request.headers:
            headers[header] = request.headers[header]
    return headers


async def process_response(
    resp: httpx.Response,
    original_body: dict,
    is_stream: bool,
) -> Response | StreamingResponse:
    """
    处理上游响应，提取并缓存 reasoning_content。

    对于非流式响应：直接解析 JSON，缓存后返回。
    对于流式响应：收集完整响应，缓存后以流式形式返回。
    """
    if is_stream:
        # 流式响应：收集完整数据用于缓存
        chunks = []
        full_content = ""
        full_reasoning = ""
        tool_calls = []

        async def stream_and_collect():
            nonlocal full_content, full_reasoning, tool_calls
            try:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            yield "data: [DONE]\n\n"
                            continue

                        try:
                            chunk = json.loads(data_str)
                            choices = chunk.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})

                                # 收集 reasoning_content
                                rc = delta.get("reasoning_content", "")
                                if rc:
                                    full_reasoning += rc

                                # 收集 content
                                c = delta.get("content", "")
                                if c:
                                    full_content += c

                                # 收集 tool_calls
                                tc = delta.get("tool_calls", [])
                                if tc:
                                    for t in tc:
                                        idx = t.get("index", 0)
                                        while len(tool_calls) <= idx:
                                            tool_calls.append({
                                                "id": "",
                                                "type": "function",
                                                "function": {"name": "", "arguments": ""},
                                            })
                                        if t.get("id"):
                                            tool_calls[idx]["id"] = t["id"]
                                        if t.get("function", {}).get("name"):
                                            tool_calls[idx]["function"]["name"] = t["function"]["name"]
                                        if t.get("function", {}).get("arguments"):
                                            tool_calls[idx]["function"]["arguments"] += t["function"]["arguments"]

                        except json.JSONDecodeError:
                            pass

                    yield line + "\n\n"
            finally:
                await resp.aclose()

                # 缓存推理内容
                if full_reasoning and tool_calls and reasoning_cache:
                    store_reasoning_from_response(
                        original_body.get("messages", []),
                        {
                            "reasoning_content": full_reasoning,
                            "tool_calls": tool_calls,
                            "content": full_content,
                        },
                        reasoning_cache,
                    )
                    stats["cache_filled"] += 1

        return StreamingResponse(
            stream_and_collect(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    else:
        # 非流式响应：直接解析并缓存
        resp_body = resp.content

        try:
            resp_data = json.loads(resp_body)
            choices = resp_data.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                if msg.get("reasoning_content") and msg.get("tool_calls"):
                    store_reasoning_from_response(
                        original_body.get("messages", []),
                        msg,
                        reasoning_cache,
                    )
                    stats["cache_filled"] += 1
        except (json.JSONDecodeError, Exception):
            pass

        return Response(
            content=resp_body,
            status_code=resp.status_code,
            media_type="application/json",
        )


# ── OpenAI 兼容端点 ──────────────────────────────────────────────────────


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """OpenAI Chat Completions 代理"""
    stats["requests"] += 1

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"error": {"message": "Invalid JSON body", "type": "invalid_request_error"}},
        )

    api_key = get_api_key(request)
    api_base = get_api_base(request)
    model = body.get("model", "")
    is_stream = body.get("stream", False)
    original_messages = body.get("messages", [])

    # 检查是否需要补丁
    needs_patch = should_patch(body)
    if needs_patch:
        body = patch_request(body, REASONING_MODELS, reasoning_cache)
        stats["patched"] += 1
        logger.info(f"Patched request: model={model} stream={is_stream}")

    url = f"{api_base}/chat/completions"
    headers = build_headers(request, api_key)

    # 移除不应转发的字段
    body.pop("stream_options", None)

    try:
        client = httpx.AsyncClient(timeout=300.0)

        if is_stream:
            req = client.build_request("POST", url, json=body, headers=headers)
            resp = await client.send(req, stream=True)

            if resp.status_code != 200:
                error_body = await resp.aread()
                await resp.aclose()
                await client.aclose()
                stats["errors"] += 1
                logger.error(f"Upstream error: {resp.status_code} {error_body[:500]}")
                return Response(
                    content=error_body,
                    status_code=resp.status_code,
                    media_type="application/json",
                )

            # 使用带缓存的响应处理
            return await process_response(resp, {"messages": original_messages}, is_stream)
        else:
            resp = await client.post(url, json=body, headers=headers)
            await client.aclose()

            if resp.status_code != 200:
                stats["errors"] += 1
                logger.error(f"Upstream error: {resp.status_code} {resp.text[:500]}")

            return await process_response(resp, {"messages": original_messages}, is_stream)

    except httpx.ConnectError as e:
        stats["errors"] += 1
        logger.error(f"Connection error: {e}")
        return JSONResponse(
            status_code=502,
            content={"error": {"message": f"Cannot connect to upstream: {e}", "type": "proxy_error"}},
        )
    except Exception as e:
        stats["errors"] += 1
        logger.error(f"Proxy error: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": {"message": f"Proxy error: {e}", "type": "proxy_error"}},
        )


@app.get("/v1/models")
async def list_models(request: Request):
    """模型列表代理"""
    api_key = get_api_key(request)
    api_base = get_api_base(request)
    headers = build_headers(request, api_key)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{api_base}/models", headers=headers)
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                media_type="application/json",
            )
    except Exception as e:
        logger.error(f"Models list error: {e}")
        return JSONResponse(
            status_code=502,
            content={"error": {"message": str(e), "type": "proxy_error"}},
        )


# ── Anthropic 兼容端点 ───────────────────────────────────────────────────


@app.post("/v1/messages")
async def messages(request: Request):
    """Anthropic Messages API 代理（转换层）"""
    stats["requests"] += 1

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"error": {"message": "Invalid JSON body", "type": "invalid_request_error"}},
        )

    api_key = get_api_key(request)
    api_base = get_api_base(request)

    openai_body = convert_anthropic_to_openai(body)
    original_messages = openai_body.get("messages", [])

    if should_patch(openai_body):
        openai_body = patch_request(openai_body, REASONING_MODELS, reasoning_cache)
        stats["patched"] += 1

    headers = build_headers(request, api_key)
    url = f"{api_base}/chat/completions"

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(url, json=openai_body, headers=headers)

            if resp.status_code != 200:
                stats["errors"] += 1
                return Response(
                    content=resp.content,
                    status_code=resp.status_code,
                    media_type="application/json",
                )

            openai_resp = resp.json()

            # 缓存推理内容
            choices = openai_resp.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                if msg.get("reasoning_content") and msg.get("tool_calls"):
                    store_reasoning_from_response(
                        original_messages, msg, reasoning_cache
                    )
                    stats["cache_filled"] += 1

            anthropic_resp = convert_openai_to_anthropic(openai_resp, body)
            return JSONResponse(content=anthropic_resp)

    except Exception as e:
        stats["errors"] += 1
        logger.error(f"Anthropic proxy error: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": {"message": str(e), "type": "proxy_error"}},
        )


# ── 协议转换 ──────────────────────────────────────────────────────────────


def convert_anthropic_to_openai(body: dict) -> dict:
    """Anthropic Messages API → OpenAI Chat Completions 格式转换"""
    messages = []
    system = body.get("system", "")
    if system:
        messages.append({"role": "system", "content": system})

    for msg in body.get("messages", []):
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if isinstance(content, list):
            text_parts = []
            tool_calls = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        tool_calls.append({
                            "id": block.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": block.get("name", ""),
                                "arguments": json.dumps(block.get("input", {})),
                            },
                        })
                    elif block.get("type") == "tool_result":
                        messages.append({
                            "role": "tool",
                            "tool_call_id": block.get("tool_use_id", ""),
                            "content": str(block.get("content", "")),
                        })
                        continue

            if tool_calls:
                messages.append({
                    "role": role,
                    "content": "\n".join(text_parts) if text_parts else "",
                    "tool_calls": tool_calls,
                })
            else:
                messages.append({"role": role, "content": "\n".join(text_parts)})
        else:
            messages.append({"role": role, "content": content})

    tools = []
    for tool in body.get("tools", []):
        tools.append({
            "type": "function",
            "function": {
                "name": tool.get("name", ""),
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {}),
            },
        })

    result = {
        "model": body.get("model", ""),
        "messages": messages,
        "max_tokens": body.get("max_tokens", 4096),
        "stream": body.get("stream", False),
    }

    if tools:
        result["tools"] = tools
    if "temperature" in body:
        result["temperature"] = body["temperature"]

    return result


def convert_openai_to_anthropic(openai_resp: dict, original_body: dict) -> dict:
    """OpenAI Chat Completions → Anthropic Messages API 格式转换"""
    choice = openai_resp.get("choices", [{}])[0]
    message = choice.get("message", {})
    finish_reason = choice.get("finish_reason", "end_turn")

    content = []
    reasoning = message.get("reasoning_content", "")
    if reasoning:
        content.append({"type": "thinking", "thinking": reasoning})

    text = message.get("content", "")
    if text:
        content.append({"type": "text", "text": text})

    for tc in message.get("tool_calls", []):
        func = tc.get("function", {})
        try:
            args = json.loads(func.get("arguments", "{}"))
        except json.JSONDecodeError:
            args = {}
        content.append({
            "type": "tool_use",
            "id": tc.get("id", ""),
            "name": func.get("name", ""),
            "input": args,
        })

    stop_reason_map = {
        "stop": "end_turn",
        "length": "max_tokens",
        "tool_calls": "tool_use",
        "function_call": "tool_use",
    }

    usage = openai_resp.get("usage", {})

    return {
        "id": openai_resp.get("id", ""),
        "type": "message",
        "role": "assistant",
        "model": openai_resp.get("model", ""),
        "content": content,
        "stop_reason": stop_reason_map.get(finish_reason, "end_turn"),
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        },
    }


# ── 管理端点 ──────────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok", "uptime": time.time() - stats["start_time"]}


@app.get("/health/upstream")
async def health_upstream(request: Request):
    """探测上游 MiMo API 可用性"""
    api_key = get_api_key(request)
    api_base = get_api_base(request)
    result = {
        "upstream": api_base,
        "model_list": None,
        "chat_test": None,
        "latency_ms": None,
    }

    # 1. 测试模型列表
    try:
        start = time.time()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{api_base}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            latency = (time.time() - start) * 1000
            result["model_list"] = {
                "status": resp.status_code,
                "ok": resp.status_code == 200,
                "latency_ms": round(latency, 1),
            }
    except Exception as e:
        result["model_list"] = {"status": "error", "ok": False, "error": str(e)}

    # 2. 测试简单对话（轻量级）
    try:
        start = time.time()
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{api_base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "mimo-v2-flash",
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 5,
                },
            )
            latency = (time.time() - start) * 1000
            result["chat_test"] = {
                "status": resp.status_code,
                "ok": resp.status_code == 200,
                "latency_ms": round(latency, 1),
            }
            result["latency_ms"] = round(latency, 1)
    except Exception as e:
        result["chat_test"] = {"status": "error", "ok": False, "error": str(e)}

    # 综合状态
    all_ok = (
        result["model_list"]
        and result["model_list"].get("ok")
        and result["chat_test"]
        and result["chat_test"].get("ok")
    )
    result["status"] = "ok" if all_ok else "degraded"

    return JSONResponse(
        content=result,
        status_code=200 if all_ok else 503,
    )


@app.get("/stats")
async def get_stats():
    """统计信息"""
    cache_stats = reasoning_cache.get_stats() if reasoning_cache else {"disabled": True}
    return {
        **stats,
        "uptime": time.time() - stats["start_time"],
        "patch_rate": (
            f"{stats['patched'] / stats['requests'] * 100:.1f}%"
            if stats["requests"] > 0
            else "N/A"
        ),
        "cache": cache_stats,
    }


@app.get("/cache/stats")
async def cache_stats():
    """缓存统计"""
    if not reasoning_cache:
        return {"disabled": True}
    return reasoning_cache.get_stats()


@app.post("/cache/clear")
async def cache_clear():
    """清空缓存"""
    if not reasoning_cache:
        return {"disabled": True}
    reasoning_cache.clear()
    return {"status": "cleared"}


@app.get("/")
async def root():
    """根路径"""
    return {
        "name": "MiMo API Compat Proxy",
        "version": "1.2.0",
        "description": "透明修复小米 MiMo API 兼容性问题（支持推理内容缓存）",
        "features": [
            "reasoning_content 自动补丁",
            "推理内容缓存（回放时填入真实思考过程）",
            "OpenAI + Anthropic 双协议",
        ],
        "endpoints": {
            "openai": "/v1/chat/completions",
            "anthropic": "/v1/messages",
            "models": "/v1/models",
            "health": "/health",
            "health_upstream": "/health/upstream",
            "stats": "/stats",
            "cache_stats": "/cache/stats",
            "cache_clear": "POST /cache/clear",
        },
        "upstream": MIMO_API_BASE,
        "cache_enabled": reasoning_cache is not None,
    }


# ── 入口 ──────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="MiMo API Compat Proxy")
    parser.add_argument("--host", default=PROXY_HOST, help=f"监听地址 (默认: {PROXY_HOST})")
    parser.add_argument("--port", type=int, default=PROXY_PORT, help=f"监听端口 (默认: {PROXY_PORT})")
    parser.add_argument("--api-key", default="", help="MiMo API Key")
    parser.add_argument("--api-base", default="", help="MiMo API 地址")
    parser.add_argument("--log-level", default=LOG_LEVEL, help="日志级别")
    parser.add_argument("--no-cache", action="store_true", help="禁用推理缓存")
    parser.add_argument("--cache-file", default="", help="缓存文件路径")
    args = parser.parse_args()

    global MIMO_API_KEY, MIMO_API_BASE, reasoning_cache

    if args.api_key:
        MIMO_API_KEY = args.api_key
    if args.api_base:
        MIMO_API_BASE = args.api_base
    if args.log_level:
        logging.getLogger().setLevel(getattr(logging, args.log_level.upper(), logging.INFO))
    if args.no_cache:
        reasoning_cache = None
        logger.info("Reasoning cache disabled via CLI")
    if args.cache_file:
        if reasoning_cache:
            reasoning_cache._cache_file = Path(args.cache_file)

    if not MIMO_API_KEY:
        logger.error("未设置 API Key，请通过 --api-key 参数或 MIMO_API_KEY 环境变量设置")
        sys.exit(1)

    logger.info(f"Starting MiMo API Compat Proxy v1.1.0 on {args.host}:{args.port}")
    logger.info(f"Upstream: {MIMO_API_BASE}")
    logger.info(f"Reasoning models: {REASONING_MODELS}")
    logger.info(f"Cache: {'enabled' if reasoning_cache else 'disabled'}")

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level=LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    main()
