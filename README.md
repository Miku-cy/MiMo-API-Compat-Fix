# MiMo API Compat Fix

> 🛠️ 小米 MiMo API 兼容性修复工具  
> 解决 MiMo V2.5 系列模型在各类 AI 编程工具中的兼容性问题

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/Miku-cy/mimo-compat-fix/releases)

---

## 问题背景

小米 MiMo V2.5 系列模型（mimo-v2.5、mimo-v2.5-pro）支持推理（reasoning）模式，API 与 OpenAI/DeepSeek 协议兼容。但存在一个关键兼容性问题：

> **当 assistant 消息包含 `tool_calls` 时，MiMo API 要求同时包含 `reasoning_content` 字段（即使是空字符串），否则返回 400 错误。**

大多数 AI 工具不会发送 `reasoning_content` 字段，导致多轮对话+工具调用时直接报错。

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

API 代理是最通用的方案，对所有工具透明，无需修改工具源码。

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动代理
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

## 项目结构

```
mimo-compat-fix/
├── README.md                    # 本文件
├── LICENSE                      # MIT 许可证
├── requirements.txt             # Python 依赖
├── proxy/
│   ├── server.py                # API 代理服务器
│   ├── patches.py               # 消息补丁逻辑
│   └── config.py                # 代理配置
├── scripts/
│   ├── fix_all.py               # 一键修复脚本
│   ├── patch_openclaw.py        # OpenClaw 源码补丁
│   ├── verify.py                # 验证脚本
│   └── detect.py                # 工具检测脚本
├── configs/
│   ├── openai/                  # OpenAI 兼容工具配置
│   └── anthropic/               # Anthropic 兼容工具配置
└── docs/
    ├── troubleshooting.md       # 故障排除
    └── api-compatibility.md     # API 兼容性详情
```

## 详细文档

- [故障排除指南](docs/troubleshooting.md)
- [API 兼容性详情](docs/api-compatibility.md)

## License

MIT License - 详见 [LICENSE](LICENSE)
