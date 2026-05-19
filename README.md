# MiMo API Compat Fix

> 🛠️ 小米 MiMo API 兼容性修复工具  
> 解决 MiMo V2.5 系列模型在各类 AI 编程工具中的兼容性问题

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.1.0-blue.svg)](https://github.com/Miku-cy/mimo-compat-fix/releases)

---

## 问题背景

小米 MiMo V2.5 系列模型（mimo-v2.5、mimo-v2.5-pro）支持推理（reasoning）模式，API 与 OpenAI/DeepSeek 协议兼容。但存在一个关键兼容性问题：

> **当 assistant 消息包含 `tool_calls` 时，MiMo API 要求同时包含 `reasoning_content` 字段（即使是空字符串），否则返回 400 错误。**

大多数 AI 工具不会发送 `reasoning_content` 字段，导致多轮对话+工具调用时直接报错。

## 解决方案

### 方案对比

| 方案 | reasoning_content | 模型性能 | 适用场景 |
|------|------------------|---------|---------|
| ❌ 不修复 | 缺失 → 400 错误 | - | - |
| ⚠️ 空字符串 | `""` | 丢失上下文 | 快速修复 |
| ✅ **缓存真实值** | 实际思考过程 | **最佳** | **推荐** |

### 推理内容缓存（v1.1.0）

代理自动缓存模型返回的 `reasoning_content`，回放历史时填入真实值：

```
第一轮对话：
  用户: "北京天气如何？"
  模型 → reasoning_content: "用户问天气，需要调用天气API查询..."
         tool_calls: [get_weather]
  → 代理缓存推理内容

第二轮回放历史：
  assistant 消息 → reasoning_content: "用户问天气，需要调用天气API查询..."（缓存）
                   tool_calls: [get_weather]
  → API 不报错 + 模型记得自己当时怎么想的 ✅
```

## 支持的工具

### OpenAI 兼容协议

| 工具 | 修复方式 | 配置文件 |
|------|---------|---------|
| TRAE | API 代理 / 配置模板 | `configs/openai/trae.json` |
| Cursor | API 代理 / 配置模板 | `configs/openai/cursor.json` |
| Roo Code | API 代理 / 配置模板 | `configs/openai/roo-code.json` |
| Codex | API 代理 / 配置模板 | `configs/openai/codex.json` |
| GitHub Copilot CLI | API 代理 / 配置模板 | `configs/openai/copilot-cli.json` |
| Zed | API 代理 / 配置模板 | `configs/openai/zed.json` |
| AutoGen | API 代理 / 配置模板 | `configs/openai/autogen.json` |
| Goose | API 代理 / 配置模板 | `configs/openai/goose.json` |

### Anthropic 兼容协议

| 工具 | 修复方式 | 配置文件 |
|------|---------|---------|
| TRAE | API 代理 | `configs/anthropic/trae.json` |
| GitHub Copilot CLI | API 代理 | `configs/anthropic/copilot-cli.json` |
| AutoGen | API 代理 | `configs/anthropic/autogen.json` |
| Goose | API 代理 | `configs/anthropic/goose.json` |
| OpenClaw | 源码补丁 / 配置 | `configs/anthropic/openclaw.json` |
| OpenCode | API 代理 | `configs/anthropic/opencode.json` |
| Kilo Code | API 代理 | `configs/anthropic/kilo-code.json` |

## 快速开始

### 方式一：API 代理（推荐）

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动代理（默认启用推理缓存）
export MIMO_API_KEY=your-api-key
python proxy/server.py --port 9090

# 3. 将工具的 API Base URL 改为代理地址
# 例如：http://localhost:9090/v1
```

### 方式二：一键修复脚本

```bash
# 检测已安装的工具并自动修复
python scripts/fix_all.py --auto

# 仅修复指定工具
python scripts/fix_all.py --tool cursor --tool openclaw

# 仅检测，不修改
python scripts/fix_all.py --detect
```

### 方式三：OpenClaw 源码补丁

```bash
# 自动打补丁
python scripts/patch_openclaw.py

# 验证补丁
python scripts/patch_openclaw.py --verify
```

## 验证

```bash
# 验证 API 和代理
python scripts/verify.py

# 查看缓存统计
curl http://localhost:9090/cache/stats

# 清空缓存
curl -X POST http://localhost:9090/cache/clear
```

## 项目结构

```
mimo-compat-fix/
├── README.md                    # 本文件
├── LICENSE                      # MIT 许可证
├── requirements.txt             # Python 依赖
├── proxy/
│   ├── server.py                # API 代理服务器
│   ├── patches.py               # 消息补丁逻辑
│   ├── reasoning_cache.py       # 推理内容缓存
│   └── config.py                # 代理配置
├── scripts/
│   ├── fix_all.py               # 一键修复脚本
│   ├── patch_openclaw.py        # OpenClaw 源码补丁
│   └── verify.py                # 验证脚本
├── configs/
│   ├── openai/                  # OpenAI 兼容工具配置
│   └── anthropic/               # Anthropic 兼容工具配置
└── docs/
    ├── troubleshooting.md       # 故障排除
    └── api-compatibility.md     # API 兼容性详情
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MIMO_API_KEY` | - | MiMo API 密钥 |
| `MIMO_API_BASE` | `https://token-plan-cn.xiaomimimo.com/v1` | API 地址 |
| `MIMO_PROXY_HOST` | `127.0.0.1` | 代理监听地址 |
| `MIMO_PROXY_PORT` | `9090` | 代理端口 |
| `MIMO_LOG_LEVEL` | `INFO` | 日志级别 |
| `MIMO_CACHE_FILE` | `reasoning_cache.json` | 缓存文件路径 |
| `MIMO_CACHE_MAX_AGE` | `86400` | 缓存过期时间（秒） |
| `MIMO_CACHE_DISABLED` | `0` | 设为 `1` 禁用缓存 |

## 详细文档

- [故障排除指南](docs/troubleshooting.md)
- [API 兼容性详情](docs/api-compatibility.md)

## License

MIT License - 详见 [LICENSE](LICENSE)
