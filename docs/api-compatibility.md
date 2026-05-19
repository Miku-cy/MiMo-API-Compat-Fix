# API 兼容性详情

## MiMo API 协议特征

小米 MiMo API 基于 OpenAI 协议，但有以下特殊行为：

### 1. reasoning_content 字段要求

**规则：** 当 `assistant` 消息包含 `tool_calls` 时，必须同时包含 `reasoning_content` 字段。

```json
// ✅ 正确
{
  "role": "assistant",
  "content": "",
  "reasoning_content": "用户问天气，需要调用工具",
  "tool_calls": [{...}]
}

// ❌ 错误（返回 400）
{
  "role": "assistant",
  "content": "",
  "tool_calls": [{...}]
}
```

> 此规则适用于**所有 MiMo V2 系列模型**，包括非推理模型 MiMo-V2-Flash。

> 数据来源：[官方定价与模型详情](https://platform.xiaomimimo.com/docs/zh-CN/pricing)

### 2. 推理输出格式

MiMo 使用 DeepSeek 兼容的推理格式：

```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "1+1=2",
      "reasoning_content": "这是一个简单的数学问题..."
    }
  }],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 50,
    "completion_tokens_details": {
      "reasoning_tokens": 45
    }
  }
}
```

### 3. 受影响模型

| 模型 | 推理 | 图像 | 上下文 | 最大输出 |
|------|------|------|--------|---------|
| MiMo-V2.5-Pro | ✅ | ❌ | 1M | 128K |
| MiMo-V2.5 | ✅ | ✅ | 1M | 128K |
| MiMo-V2-Pro | ✅ | ❌ | 1M | 128K |
| MiMo-V2-Omni | ✅ | ✅ | 256K | 128K |
| MiMo-V2-Flash | ✅ | ❌ | 256K | 64K |

### 4. 流式响应格式

```
data: {"id":"...","choices":[{"delta":{"reasoning_content":"思考..."},"index":0}]}
data: {"id":"...","choices":[{"delta":{"content":"回答..."},"index":0}]}
data: [DONE]
```

### 5. Tool Calls 格式

```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "",
      "reasoning_content": "需要调用工具查询...",
      "tool_calls": [{
        "id": "call_xxx",
        "type": "function",
        "function": {
          "name": "get_weather",
          "arguments": "{\"city\":\"北京\"}"
        }
      }]
    },
    "finish_reason": "tool_calls"
  }]
}
```

## OpenClaw 修复方案

### OpenAI 协议（配置 + 源码补丁）

OpenClaw 使用 OpenAI 协议连接 MiMo API 时，需要两个修复：

**1. 配置修复** — 在 `openclaw.json` 中声明模型支持推理：

```json
{
  "id": "mimo-v2.5-pro",
  "reasoning": true,
  "compat": {
    "thinkingFormat": "deepseek"
  }
}
```

**2. 源码补丁** — 修改 pi-ai 库，回放历史时提取真实 thinking content：

```bash
python scripts/patch_openclaw.py
```

补丁逻辑：
- 有 thinking blocks → 提取真实内容填入 `reasoning_content`
- 无 thinking blocks → 降级为空字符串（保证不报错）

### Anthropic 协议（源码补丁）

Anthropic 协议同样需要源码补丁，逻辑相同。补丁脚本同时覆盖两种协议。

## 各工具兼容性

### OpenAI 协议工具

| 工具 | 原生支持 | 需要代理 | 需要补丁 |
|------|---------|---------|---------|
| Cursor | ⚠️ 部分 | ✅ 推荐 | 否 |
| TRAE | ⚠️ 部分 | ✅ 推荐 | 否 |
| Roo Code | ⚠️ 部分 | ✅ 推荐 | 否 |
| Codex | ⚠️ 部分 | ✅ 推荐 | 否 |
| Copilot CLI | ⚠️ 部分 | ✅ 推荐 | 否 |
| Zed | ⚠️ 部分 | ✅ 推荐 | 否 |
| AutoGen | ⚠️ 部分 | ✅ 推荐 | 否 |
| Goose | ⚠️ 部分 | ✅ 推荐 | 否 |
| OpenClaw | ✅ 配置 | 可选 | ✅ 源码补丁 |

### Anthropic 协议工具

| 工具 | 原生支持 | 需要代理 | 需要补丁 |
|------|---------|---------|---------|
| OpenClaw | ✅ 配置 | 可选 | ✅ 源码补丁 |
| OpenCode | ❌ | ✅ 推荐 | 否 |
| Kilo Code | ❌ | ✅ 推荐 | 否 |
| AutoGen | ❌ | ✅ 推荐 | 否 |
| Goose | ❌ | ✅ 推荐 | 否 |
| TRAE | ❌ | ✅ 推荐 | 否 |
| Copilot CLI | ❌ | ✅ 推荐 | 否 |

## 代理工作原理

```
客户端 → 代理服务器 → MiMo API
         ↓
    1. 解析请求
    2. 检测 tool_calls 消息
    3. 注入 reasoning_content（优先从缓存获取真实内容）
    4. 转发到上游
    5. 缓存响应中的推理内容
    6. 返回响应
```

代理对客户端完全透明，无需修改客户端代码。
