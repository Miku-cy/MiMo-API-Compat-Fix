<div align="right">

**English** | [中文](README.md)

</div>

# MiMo API Compat Fix

> 🛠️ Xiaomi MiMo API Compatibility Fix  
> Solves compatibility issues with MiMo models across AI coding tools

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.1.0-blue.svg)](https://github.com/Miku-cy/MiMo-API-Compat-Fix/releases)

---

## Problem

Xiaomi MiMo models support reasoning mode with an OpenAI/DeepSeek-compatible API. However, there's a critical issue:

> **When an assistant message contains `tool_calls`, the MiMo API requires a `reasoning_content` field to be present — otherwise it returns a 400 error.**

Most AI tools don't send this field, causing multi-turn conversations with tool calls to fail.

### Affected Models

| Model | Reasoning | Vision | Context | Max Output |
|-------|-----------|--------|---------|------------|
| MiMo-V2.5-Pro | ✅ | ❌ | 1M | 32K |
| MiMo-V2.5 | ✅ | ✅ | 256K | 32K |
| MiMo-V2-Pro | ✅ | ❌ | 1M | 32K |
| MiMo-V2-Omni | ✅ | ✅ | 256K | 32K |
| MiMo-V2-Flash | ❌ | ❌ | 256K | 8K |

> ⚠️ All MiMo V2 models are affected, not just V2.5.

## Solutions

| Approach | For | How |
|----------|-----|-----|
| **API Proxy** | Cursor, TRAE, etc. | Proxy auto-injects missing fields |
| **Source Patch** | OpenClaw | Patches pi-ai to extract real reasoning from thinking blocks |
| **Config Fix** | OpenClaw (OpenAI protocol) | Set `reasoning: true` + `thinkingFormat: deepseek` |

### Reasoning Cache (v1.1.0)

The proxy caches `reasoning_content` from model responses and replays it in history — no more empty strings:

```
Turn 1: Model returns reasoning_content → cached automatically
Turn 2: History replay → real reasoning content filled → model retains context ✅
```

## Supported Tools

<details>
<summary><b>OpenAI Compatible (8 tools)</b></summary>

| Tool | Config |
|------|--------|
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
<summary><b>Anthropic Compatible (7 tools)</b></summary>

| Tool | Config |
|------|--------|
| OpenClaw | Source patch / Config |
| TRAE | `configs/anthropic/trae.json` |
| GitHub Copilot CLI | `configs/anthropic/copilot-cli.json` |
| AutoGen | `configs/anthropic/autogen.json` |
| Goose | `configs/anthropic/goose.json` |
| OpenCode | `configs/anthropic/opencode.json` |
| Kilo Code | `configs/anthropic/kilo-code.json` |

</details>

## Quick Start

### API Proxy (for third-party tools)

```bash
pip install -r requirements.txt
export MIMO_API_KEY=your-api-key
python proxy/server.py --port 9090
# Point your tool's API Base URL to http://localhost:9090/v1
```

### One-Click Fix

```bash
python scripts/fix_all.py --auto        # Detect and fix all
python scripts/fix_all.py --detect      # Detect only
python scripts/fix_all.py --tool cursor  # Fix specific tool
```

### OpenClaw Fix

**Method 1: Source Patch (Recommended)**

```bash
python scripts/patch_openclaw.py          # Apply patch
python scripts/patch_openclaw.py --verify # Verify
python scripts/patch_openclaw.py --revert # Revert
```

Extracts real reasoning content from thinking blocks during history replay, preserving context.

**Method 2: Config Fix (OpenAI Protocol)**

Add to model config in `openclaw.json`:

```json
{
  "id": "mimo-v2.5-pro",
  "reasoning": true,
  "compat": {
    "thinkingFormat": "deepseek"
  }
}
```

> 💡 Both methods can be used together: config tells OpenClaw the model supports reasoning, source patch ensures history replay carries real thinking content.

## Verify

```bash
python scripts/verify.py                 # Full verification
curl http://localhost:9090/cache/stats    # Cache stats
curl -X POST http://localhost:9090/cache/clear  # Clear cache
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MIMO_API_KEY` | - | MiMo API key |
| `MIMO_API_BASE` | `https://token-plan-cn.xiaomimimo.com/v1` | API endpoint |
| `MIMO_PROXY_PORT` | `9090` | Proxy port |
| `MIMO_CACHE_DISABLED` | `0` | Set `1` to disable cache |
| `MIMO_CACHE_MAX_AGE` | `86400` | Cache TTL (seconds) |

## Project Structure

```
MiMo-API-Compat-Fix/
├── proxy/                  # API proxy server
│   ├── server.py           # FastAPI proxy
│   ├── patches.py          # Message patching logic
│   ├── reasoning_cache.py  # Reasoning content cache
│   └── config.py           # Config (all affected models)
├── scripts/
│   ├── fix_all.py          # One-click fix
│   ├── patch_openclaw.py   # OpenClaw patcher
│   └── verify.py           # Verification
├── configs/                # Tool config templates
│   ├── openai/
│   └── anthropic/
└── docs/
    ├── troubleshooting.md
    └── api-compatibility.md
```

## Docs

- [Troubleshooting](docs/troubleshooting.md)
- [API Compatibility Details](docs/api-compatibility.md)

## License

[MIT](LICENSE)
