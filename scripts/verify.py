#!/usr/bin/env python3
"""
MiMo API 兼容性验证脚本

验证代理是否正常工作，以及各工具的配置是否正确。

用法：
    python verify.py                       # 验证全部
    python verify.py --proxy               # 仅验证代理
    python verify.py --api                 # 仅验证 API 连通性
    python verify.py --proxy-url http://localhost:9090
"""

import argparse
import json
import sys
import time

import httpx


def test_api_direct(api_base: str, api_key: str) -> bool:
    """直接测试 MiMo API"""
    print("\n🔌 测试 MiMo API 直连...")

    # 1. 连通性
    try:
        resp = httpx.get(
            f"{api_base}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10.0,
        )
        if resp.status_code == 200:
            print("  ✅ API 连通性正常")
        else:
            print(f"  ❌ API 返回 {resp.status_code}: {resp.text[:200]}")
            return False
    except Exception as e:
        print(f"  ❌ 连接失败: {e}")
        return False

    # 2. 简单对话
    try:
        resp = httpx.post(
            f"{api_base}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "mimo-v2.5-pro",
                "messages": [{"role": "user", "content": "回复OK"}],
                "max_tokens": 10,
            },
            timeout=30.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            print(f"  ✅ 对话测试通过: {content[:50]}")
        else:
            print(f"  ❌ 对话测试失败: {resp.status_code}")
            return False
    except Exception as e:
        print(f"  ❌ 对话测试失败: {e}")
        return False

    # 3. 推理模式
    try:
        resp = httpx.post(
            f"{api_base}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "mimo-v2.5-pro",
                "messages": [{"role": "user", "content": "1+1=?"}],
                "max_tokens": 100,
            },
            timeout=30.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            msg = data["choices"][0]["message"]
            if "reasoning_content" in msg:
                print(f"  ✅ 推理模式正常 (reasoning_content 存在)")
            else:
                print(f"  ⚠️  推理模式可能未启用 (无 reasoning_content)")
        else:
            print(f"  ⚠️  推理测试返回 {resp.status_code}")
    except Exception as e:
        print(f"  ⚠️  推理测试失败: {e}")

    # 4. Tool calls 兼容性（核心问题）
    print("\n🧪 测试 tool_calls 兼容性...")
    try:
        resp = httpx.post(
            f"{api_base}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "mimo-v2.5-pro",
                "messages": [
                    {"role": "user", "content": "北京天气"},
                    {
                        "role": "assistant",
                        "content": "",
                        "reasoning_content": "需要查天气",
                        "tool_calls": [{
                            "id": "c1",
                            "type": "function",
                            "function": {
                                "name": "get_weather",
                                "arguments": '{"city":"北京"}',
                            },
                        }],
                    },
                    {"role": "tool", "tool_call_id": "c1", "content": "晴天25°C"},
                    {"role": "user", "content": "上海呢？"},
                ],
                "tools": [{
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "description": "查天气",
                        "parameters": {
                            "type": "object",
                            "properties": {"city": {"type": "string"}},
                            "required": ["city"],
                        },
                    },
                }],
                "max_tokens": 200,
            },
            timeout=30.0,
        )
        if resp.status_code == 200:
            print("  ✅ tool_calls + reasoning_content 兼容性测试通过")
        else:
            print(f"  ❌ tool_calls 测试失败: {resp.status_code}")
            print(f"     {resp.text[:300]}")
            return False
    except Exception as e:
        print(f"  ❌ tool_calls 测试失败: {e}")
        return False

    # 5. 无 reasoning_content 的 tool_calls（应触发 400）
    try:
        resp = httpx.post(
            f"{api_base}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "mimo-v2.5-pro",
                "messages": [
                    {"role": "user", "content": "北京天气"},
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [{
                            "id": "c1",
                            "type": "function",
                            "function": {
                                "name": "get_weather",
                                "arguments": '{"city":"北京"}',
                            },
                        }],
                    },
                    {"role": "tool", "tool_call_id": "c1", "content": "晴天25°C"},
                    {"role": "user", "content": "上海呢？"},
                ],
                "tools": [{
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "description": "查天气",
                        "parameters": {
                            "type": "object",
                            "properties": {"city": {"type": "string"}},
                            "required": ["city"],
                        },
                    },
                }],
                "max_tokens": 200,
            },
            timeout=30.0,
        )
        if resp.status_code == 400:
            print("  ✅ 无 reasoning_content 时正确返回 400（确认问题存在）")
        elif resp.status_code == 200:
            print("  ℹ️  无 reasoning_content 也返回 200（API 可能已修复）")
        else:
            print(f"  ⚠️  未预期的状态码: {resp.status_code}")
    except Exception as e:
        print(f"  ⚠️  测试失败: {e}")

    return True


def test_proxy(proxy_url: str) -> bool:
    """测试代理服务器"""
    print(f"\n🔀 测试代理服务器: {proxy_url}")

    # 1. 健康检查
    try:
        resp = httpx.get(f"{proxy_url}/health", timeout=5.0)
        if resp.status_code == 200:
            data = resp.json()
            print(f"  ✅ 代理健康: uptime={data.get('uptime', 0):.0f}s")
        else:
            print(f"  ❌ 代理不健康: {resp.status_code}")
            return False
    except Exception as e:
        print(f"  ❌ 无法连接代理: {e}")
        print(f"     请确保代理正在运行: python proxy/server.py")
        return False

    # 2. 统计
    try:
        resp = httpx.get(f"{proxy_url}/stats", timeout=5.0)
        if resp.status_code == 200:
            data = resp.json()
            print(f"  📊 请求: {data.get('requests', 0)} | 补丁: {data.get('patched', 0)} | 错误: {data.get('errors', 0)}")
    except Exception:
        pass

    # 3. 通过代理测试对话
    try:
        resp = httpx.post(
            f"{proxy_url}/v1/chat/completions",
            json={
                "model": "mimo-v2.5-pro",
                "messages": [{"role": "user", "content": "回复OK"}],
                "max_tokens": 10,
            },
            timeout=30.0,
        )
        if resp.status_code == 200:
            print("  ✅ 代理对话测试通过")
        else:
            print(f"  ❌ 代理对话测试失败: {resp.status_code}")
            return False
    except Exception as e:
        print(f"  ❌ 代理对话测试失败: {e}")
        return False

    # 4. 通过代理测试 tool_calls 修复
    print("  🧪 测试代理自动补丁...")
    try:
        resp = httpx.post(
            f"{proxy_url}/v1/chat/completions",
            json={
                "model": "mimo-v2.5-pro",
                "messages": [
                    {"role": "user", "content": "北京天气"},
                    {
                        "role": "assistant",
                        "content": "",
                        # 故意不带 reasoning_content，测试代理是否自动补丁
                        "tool_calls": [{
                            "id": "c1",
                            "type": "function",
                            "function": {
                                "name": "get_weather",
                                "arguments": '{"city":"北京"}',
                            },
                        }],
                    },
                    {"role": "tool", "tool_call_id": "c1", "content": "晴天25°C"},
                    {"role": "user", "content": "上海呢？"},
                ],
                "tools": [{
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "description": "查天气",
                        "parameters": {
                            "type": "object",
                            "properties": {"city": {"type": "string"}},
                            "required": ["city"],
                        },
                    },
                }],
                "max_tokens": 200,
            },
            timeout=30.0,
        )
        if resp.status_code == 200:
            print("  ✅ 代理自动补丁测试通过（无 reasoning_content 的请求被正确修复）")
        else:
            print(f"  ❌ 代理自动补丁测试失败: {resp.status_code}")
            print(f"     {resp.text[:300]}")
            return False
    except Exception as e:
        print(f"  ❌ 代理自动补丁测试失败: {e}")
        return False

    return True


def main():
    parser = argparse.ArgumentParser(description="MiMo API 兼容性验证")
    parser.add_argument("--api", action="store_true", help="仅测试 API 直连")
    parser.add_argument("--proxy", action="store_true", help="仅测试代理")
    parser.add_argument("--api-base", default="https://token-plan-cn.xiaomimimo.com/v1")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--proxy-url", default="http://127.0.0.1:9090")
    args = parser.parse_args()

    print("\n" + "=" * 50)
    print("🔍 MiMo API 兼容性验证")
    print("=" * 50)

    api_key = args.api_key or os.environ.get("MIMO_API_KEY", "")
    if not api_key:
        print("\n⚠️  未设置 API Key，部分测试将跳过")
        print("   设置方式: export MIMO_API_KEY=your_key 或 --api-key your_key")

    results = {}

    if args.api or not args.proxy:
        if api_key:
            results["api"] = test_api_direct(args.api_base, api_key)
        else:
            print("\n⏭️  跳过 API 直连测试（无 API Key）")

    if args.proxy or not args.api:
        results["proxy"] = test_proxy(args.proxy_url)

    # 汇总
    print("\n" + "=" * 50)
    all_pass = all(results.values()) if results else False
    if all_pass:
        print("✅ 所有测试通过！")
    else:
        print("⚠️  部分测试未通过，请检查上述输出")

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    import os
    main()
