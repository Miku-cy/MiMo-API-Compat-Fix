"""
MiMo API 消息补丁逻辑

核心问题：MiMo API 要求 assistant 消息包含 tool_calls 时必须同时包含
reasoning_content 字段（即使是空字符串），否则返回 400 错误。

本模块提供自动补丁逻辑，在代理层透明修复此问题。
"""

import copy
import logging
from typing import Any

logger = logging.getLogger("mimo-compat")


def is_reasoning_model(model: str, reasoning_models: list[str]) -> bool:
    """判断是否为推理模型"""
    model_lower = model.lower()
    return any(m in model_lower for m in reasoning_models)


def patch_messages(
    messages: list[dict[str, Any]],
    model: str,
    reasoning_models: list[str],
) -> list[dict[str, Any]]:
    """
    补丁消息列表，修复 MiMo API 兼容性问题。
    
    核心修复：
    1. assistant 消息有 tool_calls 但无 reasoning_content → 注入空字符串
    2. 非推理模型的 reasoning_content → 移除（避免 API 报错）
    3. 修复空 content 的 assistant 消息（部分工具发送 null）
    
    Args:
        messages: 原始消息列表
        model: 模型名称
        reasoning_models: 推理模型列表
    
    Returns:
        补丁后的消息列表
    """
    if not messages:
        return messages

    patched = copy.deepcopy(messages)
    is_reasoning = is_reasoning_model(model, reasoning_models)
    patch_count = 0

    for msg in patched:
        if msg.get("role") != "assistant":
            continue

        has_tool_calls = bool(msg.get("tool_calls"))
        has_reasoning = "reasoning_content" in msg

        # 核心修复：有 tool_calls 但没有 reasoning_content
        if has_tool_calls and not has_reasoning:
            msg["reasoning_content"] = ""
            patch_count += 1
            logger.debug(
                "Patched assistant message: injected reasoning_content=\"\" "
                "(tool_calls present)"
            )

        # 修复 null content（部分工具发送 null 而非空字符串）
        if msg.get("content") is None:
            msg["content"] = ""
            patch_count += 1
            logger.debug("Patched assistant message: null content → \"\"")

        # 非推理模型：移除 reasoning_content（避免 API 不识别）
        if not is_reasoning and has_reasoning:
            del msg["reasoning_content"]
            patch_count += 1
            logger.debug(
                "Patched assistant message: removed reasoning_content "
                "(non-reasoning model)"
            )

    if patch_count > 0:
        logger.info(f"Patched {patch_count} message(s) for model={model}")

    return patched


def patch_request(
    request_body: dict[str, Any],
    reasoning_models: list[str],
) -> dict[str, Any]:
    """
    补丁整个请求体。
    
    Args:
        request_body: 原始请求体
        reasoning_models: 推理模型列表
    
    Returns:
        补丁后的请求体
    """
    body = copy.deepcopy(request_body)
    model = body.get("model", "")
    messages = body.get("messages", [])

    if messages:
        body["messages"] = patch_messages(messages, model, reasoning_models)

    return body


def patch_stream_chunk(chunk: dict[str, Any]) -> dict[str, Any]:
    """
    补丁流式响应块。
    
    MiMo API 的流式响应中，reasoning_content 在 delta 中。
    某些客户端可能不识别此字段，需要根据需要处理。
    
    Args:
        chunk: 流式响应块
    
    Returns:
        补丁后的响应块
    """
    # 目前直接透传，未来可根据客户端需求做转换
    return chunk
