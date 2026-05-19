<div align="right">

[English](README_EN.md) | **中文**

</div>

# MiMo API Compat Fix

> 🛠️ 小米 MiMo API 兼容性修复工具  
> 解决 MiMo V2.5 系列模型在各类 AI 编程工具中的兼容性问题

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.1.0-blue.svg)](https://github.com/Miku-cy/mimo-compat-fix/releases)

---

## 问题背景

小米 MiMo V2.5 系列模型（mimo-v2.5、mimo-v2.5-pro）支持推理模式，API 与 OpenAI/DeepSeek 协议兼容。但存在一个关键问题：

> **当 assistant 消息包含 `tool_calls` 时，MiMo API 要求同时包含 `reasoning_content` 字段，否则返回 400 错误。**

大多数 AI 工具不会发送此字段，导致多轮对话 + 工具调用时直接报错。

## 解决方案

| 方案 | 适用场景 | 原理 |
|------|---------|------|
| **API 代理** | Cursor、TRAE 等第三方工具 | 代理层自动补全缺失字段 |
| **源码补丁** | OpenClaw | 直接修改 pi-ai 库，从 thinking blocks 提取真实推理内容 |

### 推理内容缓存（v1.1.0）

代理自动缓存模型返回的 `reasoning_content`，回放历史时填入**真实值**而非空字符串：

```
第一轮：模型返回 reasoning_content → 自动缓存
第二轮：回放历史 → 填入缓存的真实推理内容 → 模型保留上下文 ✅
```

## 支持的工具

<details>
<summary><b>OpenAI 兼容协议（8 个）</b></summary>

| 工具 | 配置文件 |
|------|---------|
| Cursor | `configs/openai/cursor.json` |
| TRAE | `configs/openai/trae.json` |
| Roo Code | `configs/openai/roo-code.json` |
| Codex | `configs/openai/codex.json` |
| GitHub Copilot CLI | `configs/openai/copilot-cli.json` |
| Zed | `configs/openai/zed.json` |
| AutoGen | `configs/openai/autogen.json` |
| Goose | `configs/openai/goose.json` |

</details>

<details>
<summary><b>Anthropic 兼容协议（7 个）</b></summary>

| 工具 | 配置文件 |
|------|---------|
| OpenClaw | 源码补丁 |
| TRAE | `configs/anthropic/trae.json` |
| GitHub Copilot CLI | `configs/anthropic/copilot-cli.json` |
| AutoGen | `configs/anthropic/autogen.json` |
| Goose | `configs/anthropic/goose.json` |
| OpenCode | `configs/anthropic/opencode.json` |
| Kilo Code | `configs/anthropic/kilo-code.json` |

</details>

## 快速开始

### API 代理（第三方工具）

```bash
pip install -r requirements.txt
export MIMO_API_KEY=your-api-key
python proxy/server.py --port 9090
# 将工具的 API Base URL 改为 http://localhost:9090/v1
```

### 一键修复

```bash
python scripts/fix_all.py --auto        # 自动检测并修复
python scripts/fix_all.py --detect      # 仅检测
python scripts/fix_all.py --tool cursor  # 修复指定工具
```

### OpenClaw 源码补丁

```bash
python scripts/patch_openclaw.py          # 应用补丁
python scripts/patch_openclaw.py --verify # 验证补丁
python scripts/patch_openclaw.py --revert # 还原
```

## 验证

```bash
python scripts/verify.py                 # 完整验证
curl http://localhost:9090/cache/stats    # 缓存统计
curl -X POST http://localhost:9090/cache/clear  # 清空缓存
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MIMO_API_KEY` | - | MiMo API 密钥 |
| `MIMO_API_BASE` | `https://token-plan-cn.xiaomimimo.com/v1` | API 地址 |
| `MIMO_PROXY_PORT` | `9090` | 代理端口 |
| `MIMO_CACHE_DISABLED` | `0` | 设为 `1` 禁用缓存 |
| `MIMO_CACHE_MAX_AGE` | `86400` | 缓存过期（秒） |

## 项目结构

```
mimo-compat-fix/
├── proxy/                  # API 代理服务器
│   ├── server.py           # FastAPI 代理
│   ├── patches.py          # 消息补丁逻辑
│   ├── reasoning_cache.py  # 推理内容缓存
│   └── config.py           # 配置
├── scripts/
│   ├── fix_all.py          # 一键修复
│   ├── patch_openclaw.py   # OpenClaw 补丁
│   └── verify.py           # 验证
├── configs/                # 各工具配置模板
│   ├── openai/
│   └── anthropic/
└── docs/
    ├── troubleshooting.md
    └── api-compatibility.md
```

## 相关文档

- [故障排除](docs/troubleshooting.md)
- [API 兼容性详情](docs/api-compatibility.md)

## License

[MIT](LICENSE)
