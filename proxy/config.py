"""MiMo API 代理配置"""

import os

# 代理服务器配置
PROXY_HOST = os.getenv("MIMO_PROXY_HOST", "127.0.0.1")
PROXY_PORT = int(os.getenv("MIMO_PROXY_PORT", "9090"))

# MiMo API 配置
MIMO_API_BASE = os.getenv("MIMO_API_BASE", "https://token-plan-cn.xiaomimimo.com/v1")
MIMO_API_KEY = os.getenv("MIMO_API_KEY", "")

# 支持的模型
MIMO_MODELS = [
    "mimo-v2.5",
    "mimo-v2.5-pro",
    "mimo-v2-flash",
    "mimo-v2-pro",
    "mimo-v2-omni",
]

# 受影响的 MiMo 模型（API 要求 tool_calls 时必须带 reasoning_content）
REASONING_MODELS = [
    "mimo-v2.5",
    "mimo-v2.5-pro",
    "mimo-v2-pro",
    "mimo-v2-omni",
    "mimo-v2-flash",
    "MiMo-V2.5-Pro",
    "MiMo-V2.5",
    "MiMo-V2-Pro",
    "MiMo-V2-Omni",
    "MiMo-V2-Flash",
]

# 日志配置
LOG_LEVEL = os.getenv("MIMO_LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("MIMO_LOG_FILE", "")
