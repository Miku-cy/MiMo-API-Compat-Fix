# AI Agent 使用指南

> 本文档面向 AI Agent（如 OpenClaw、Claude、Cursor Agent 等），提供本项目的完整技术细节和集成指引。

---

## 项目概述

**MiMo API Compat Fix** 解决小米 MiMo V2 系列模型的 API 兼容性问题。

**核心问题：** MiMo API 要求 assistant 消息在包含 `tool_calls` 时必须同时包含 `reasoning_content` 字段（即使是空字符串），否则返回 HTTP 400。

**影响范围：** 所有 MiMo V2 模型（V2.5-Pro、V2.5、V2-Pro、V2-Omni、V2-Flash）。

---

## 技术细节

### 问题根因

MiMo API 继承自 DeepSeek V4 协议，有一个硬性约束：

```
当 messages 中的 assistant 消息包含 tool_calls 字段时，
必须同时包含 reasoning_content 字段，否则返回 400 Bad Request。
```

大多数 AI 工具（Cursor、TRAE 等）遵循标准 OpenAI 协议，不会发送 `reasoning_content`，导致请求失败。

### 修复策略

#### 策略 1：API 代理（通用方案）

代理服务器拦截请求，检测并修复不合规的消息：

```
客户端 → 代理(:9090) → MiMo API
         ↓
  1. 解析请求体 JSON
  2. 遍历 messages 数组
  3. 找到 role=assistant 且有 tool_calls 但无 reasoning_content 的消息
  4. 从缓存获取真实推理内容，或注入空字符串
  5. 转发到上游 API
  6. 从响应中提取 reasoning_content 并缓存
  7. 返回响应给客户端
```

**关键代码位置：** `proxy/patches.py` → `patch_messages()` 函数

**缓存机制：**
- 缓存 key：`(context_hash, message_index, tool_call_ids)`
- 缓存值：模型返回的 `reasoning_content` 文本
- 过期时间：默认 24 小时
- 存储：JSON 文件持久化

#### 策略 2：源码补丁（OpenClaw 专用）

修改 OpenClaw 的 pi-ai 库，在消息回放时从 thinking blocks 提取真实推理内容：

**补丁位置：**
```
/usr/local/lib/node_modules/openclaw/node_modules/@mariozechner/pi-ai/dist/providers/openai-completions.js
```

**补丁逻辑：**
```javascript
// 在 convertMessages 函数中，assistant 消息处理区域
if (assistantMsg.tool_calls && assistantMsg.tool_calls.length > 0 
    && assistantMsg.reasoning_content === undefined 
    && model.provider === "xiaomi-coding") {
  // 优先从 thinking blocks 提取真实内容
  if (nonEmptyThinkingBlocks.length > 0) {
    assistantMsg.reasoning_content = nonEmptyThinkingBlocks
      .map(block => sanitizeSurrogates(block.thinking))
      .join("\n\n");
  } else {
    assistantMsg.reasoning_content = "";  // 降级
  }
}
```

**注意：** OpenClaw 更新后需要重新应用此补丁。

---

## API 端点

### 代理端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/chat/completions` | POST | OpenAI Chat Completions 代理 |
| `/v1/messages` | POST | Anthropic Messages API 代理 |
| `/v1/models` | GET | 模型列表代理 |
| `/health` | GET | 健康检查 |
| `/stats` | GET | 请求统计 |
| `/cache/stats` | GET | 缓存统计 |
| `/cache/clear` | POST | 清空缓存 |

### 请求转发

代理将请求原样转发到 MiMo API，仅修改以下内容：
- 补全缺失的 `reasoning_content` 字段
- 修复 `null` content 为 `""`
- 非推理模型移除 `reasoning_content`

### 响应处理

- **非流式：** 解析 JSON，缓存 `reasoning_content`，返回原响应
- **流式：** 收集完整数据块，缓存后以 SSE 格式返回

---

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MIMO_API_KEY` | （必填） | MiMo API 密钥 |
| `MIMO_API_BASE` | `https://token-plan-cn.xiaomimimo.com/v1` | 上游 API 地址 |
| `MIMO_PROXY_HOST` | `127.0.0.1` | 代理监听地址 |
| `MIMO_PROXY_PORT` | `9090` | 代理端口 |
| `MIMO_LOG_LEVEL` | `INFO` | 日志级别 |
| `MIMO_CACHE_FILE` | `reasoning_cache.json` | 缓存文件路径 |
| `MIMO_CACHE_MAX_AGE` | `86400` | 缓存过期秒数 |
| `MIMO_CACHE_DISABLED` | `0` | 设为 `1` 禁用缓存 |

---

## 文件结构

```
MiMo-API-Compat-Fix/
├── proxy/
│   ├── server.py           # FastAPI 代理服务器
│   ├── patches.py          # 消息补丁逻辑（核心）
│   ├── reasoning_cache.py  # 推理内容缓存
│   └── config.py           # 配置常量
├── scripts/
│   ├── fix_all.py          # 一键检测 + 修复
│   ├── patch_openclaw.py   # OpenClaw 源码补丁
│   └── verify.py           # 验证脚本
├── configs/
│   ├── openai/             # OpenAI 协议工具配置模板
│   └── anthropic/          # Anthropic 协议工具配置模板
├── docs/
│   ├── ai-agent-guide.md   # 本文件
│   ├── troubleshooting.md  # 故障排除
│   └── api-compatibility.md
├── requirements.txt        # Python 依赖
└── LICENSE                 # MIT 许可
```

---

## 集成指引

### 作为代理使用

```bash
# 启动代理
pip install fastapi uvicorn httpx
MIMO_API_KEY=your-key python proxy/server.py --port 9090

# 验证
curl http://localhost:9090/health
# → {"status":"ok","uptime":...}
```

### 编程式调用

```python
from proxy.patches import patch_request, store_reasoning_from_response
from proxy.reasoning_cache import ReasoningCache

# 初始化缓存
cache = ReasoningCache(cache_file="cache.json")

# 修复请求
fixed_body = patch_request(request_body, REASONING_MODELS, cache)

# 缓存响应推理内容
store_reasoning_from_response(messages, response_message, cache)
```

### OpenClaw 补丁

```bash
# 应用
python scripts/patch_openclaw.py

# 验证
python scripts/patch_openclaw.py --verify

# 还原
python scripts/patch_openclaw.py --revert
```

---

## 测试用例

### 1. 基础连通性

```bash
curl -s http://localhost:9090/health
# 期望: {"status":"ok"}
```

### 2. 代理补丁（无 reasoning_content 的 tool_calls）

```bash
curl -s http://localhost:9090/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mimo-v2.5-pro",
    "messages": [
      {"role":"user","content":"北京天气"},
      {"role":"assistant","content":"","tool_calls":[{"id":"c1","type":"function","function":{"name":"get_weather","arguments":"{\"city\":\"北京\"}"}}]},
      {"role":"tool","tool_call_id":"c1","content":"晴天25°C"},
      {"role":"user","content":"上海呢？"}
    ],
    "tools":[{"type":"function","function":{"name":"get_weather","description":"查天气","parameters":{"type":"object","properties":{"city":{"type":"string"}},"required":["city"]}}}],
    "max_tokens":200
  }'
# 期望: 200 OK（直接打 MiMo API 会返回 400）
```

### 3. 缓存命中

```bash
# 第二次发送相同请求，检查缓存统计
curl http://localhost:9090/cache/stats
# 期望: hits > 0
```

---

## 受影响模型 ID

```
mimo-v2.5-pro
mimo-v2.5
mimo-v2-pro
mimo-v2-omni
mimo-v2-flash
MiMo-V2.5-Pro
MiMo-V2.5
MiMo-V2-Pro
MiMo-V2-Omni
MiMo-V2-Flash
```

大小写不敏感，代理会自动匹配。

---

## 已知限制

1. **代理需要持续运行** — 工具依赖代理，停止代理则工具无法使用
2. **源码补丁需维护** — OpenClaw 更新后需重新打补丁
3. **缓存有容量限制** — 默认 10000 条目，LRU 淘汰
4. **流式响应有延迟** — 代理需要收集完整数据块用于缓存，会引入少量延迟

---

## License

MIT
