"""
MiMo API 消息补丁逻辑

核心问题：MiMo API 要求 assistant 消息包含 tool_calls 时必须同时包含
reasoning_content 字段（即使是空字符串），否则返回 400 错误。

本模块提供自动补丁逻辑，在代理层透明修复此问题。

v1.1.0: 支持推理内容缓存，回放历史时填入真实的 reasoning_content。
"""

import copy
import logging
from typing import Any, Optional

logger = logging.getLogger("mimo-compat")


def is_reasoning_model(model: str, reasoning_models: list[str]) -> bool:
    """判断是否为推理模型"""
    model_lower = model.lower()
    return any(m in model_lower for m in reasoning_models)


def patch_messages(
    messages: list[dict[str, Any]],
    model: str,
    reasoning_models: list[str],
    reasoning_cache=None,
) -> list[dict[str, Any]]:
    """
    补丁消息列表，修复 MiMo API 兼容性问题。

    核心修复：
    1. assistant 消息有 tool_calls 但无 reasoning_content → 从缓存获取或注入空字符串
    2. 非推理模型的 reasoning_content → 移除
    3. 修复 null content

    缓存策略（v1.1.0）：
    - 回放历史时，先查缓存是否有该消息的真实 reasoning_content
    - 缓存命中 → 填入真实内容（保留上下文，提升模型性能）
    - 缓存未命中 → 注入空字符串（保证不报错）

    Args:
        messages: 原始消息列表
        model: 模型名称
        reasoning_models: 推理模型列表
        reasoning_cache: ReasoningCache 实例（可选）

    Returns:
        补丁后的消息列表
    """
    if not messages:
        return messages

    patched = copy.deepcopy(messages)
    is_reasoning = is_reasoning_model(model, reasoning_models)
    patch_count = 0
    cache_hits = 0

    for i, msg in enumerate(patched):
        if msg.get("role") != "assistant":
            continue

        has_tool_calls = bool(msg.get("tool_calls"))
        has_reasoning = "reasoning_content" in msg

        # 核心修复：有 tool_calls 但没有 reasoning_content
        if has_tool_calls and not has_reasoning:
            # 尝试从缓存获取真实推理内容
            cached_reasoning = None
            if reasoning_cache:
                tool_call_ids = [
                    tc.get("id", "") for tc in msg.get("tool_calls", [])
                ]
                cached_reasoning = reasoning_cache.get(
                    patched, i, tool_call_ids
                )

            if cached_reasoning:
                msg["reasoning_content"] = cached_reasoning
                cache_hits += 1
                logger.debug(
                    f"Patched message {i}: filled reasoning_content from cache "
                    f"({len(cached_reasoning)} chars)"
                )
            else:
                msg["reasoning_content"] = ""
                logger.debug(
                    f"Patched message {i}: injected empty reasoning_content "
                    f"(cache miss)"
                )

            patch_count += 1

        # 修复 null content
        if msg.get("content") is None:
            msg["content"] = ""
            patch_count += 1

        # 非推理模型：移除 reasoning_content
        if not is_reasoning and has_reasoning:
            del msg["reasoning_content"]
            patch_count += 1

    if patch_count > 0:
        logger.info(
            f"Patched {patch_count} message(s) for model={model} "
            f"(cache_hits={cache_hits})"
        )

    return patched


def store_reasoning_from_response(
    request_messages: list[dict[str, Any]],
    response_message: dict[str, Any],
    reasoning_cache,
):
    """
    从 API 响应中提取并缓存 reasoning_content。

    当模型返回带 tool_calls 的响应时，将 reasoning_content 存入缓存，
    以便后续回放历史时使用。

    Args:
        request_messages: 请求时的消息列表
        response_message: API 返回的 assistant 消息
        reasoning_cache: ReasoningCache 实例
    """
    if not reasoning_cache:
        return

    reasoning = response_message.get("reasoning_content", "")
    tool_calls = response_message.get("tool_calls", [])

    if not reasoning or not tool_calls:
        return

    tool_call_ids = [tc.get("id", "") for tc in tool_calls]

    # assistant 消息是请求消息列表的下一条
    assistant_index = len(request_messages)

    reasoning_cache.store(
        request_messages, assistant_index, tool_call_ids, reasoning
    )
    logger.info(
        f"Cached reasoning_content: {len(reasoning)} chars, "
        f"tool_call_ids={tool_call_ids}"
    )


def patch_request(
    request_body: dict[str, Any],
    reasoning_models: list[str],
    reasoning_cache=None,
) -> dict[str, Any]:
    """补丁整个请求体"""
    body = copy.deepcopy(request_body)
    model = body.get("model", "")
    messages = body.get("messages", [])

    if messages:
        body["messages"] = patch_messages(
            messages, model, reasoning_models, reasoning_cache
        )

    return body
