#!/usr/bin/env python3
"""
MiMo 兼容性一键修复脚本

自动检测已安装的 AI 编程工具，应用兼容性修复。
支持：TRAE、Cursor、Roo Code、Codex、GitHub Copilot CLI、Zed、AutoGen、Goose、
      OpenClaw、OpenCode、Kilo Code

用法：
    python fix_all.py --auto              # 自动检测并修复所有工具
    python fix_all.py --detect            # 仅检测，不修改
    python fix_all.py --tool cursor       # 修复指定工具
    python fix_all.py --tool cursor --tool openclaw  # 修复多个工具
    python fix_all.py --proxy http://localhost:9090   # 指定代理地址
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ── 工具定义 ──────────────────────────────────────────────────────────────


@dataclass
class ToolConfig:
    """工具配置"""
    name: str
    display_name: str
    protocol: str  # "openai" or "anthropic"
    config_paths: list[str] = field(default_factory=list)
    detect_commands: list[str] = field(default_factory=list)
    config_format: str = "json"  # "json" or "toml" or "yaml"
    api_key_env: str = ""
    base_url_field: str = "base_url"
    api_key_field: str = "api_key"
    notes: str = ""


TOOLS: dict[str, ToolConfig] = {
    # ── OpenAI 兼容 ──
    "cursor": ToolConfig(
        name="cursor",
        display_name="Cursor",
        protocol="openai",
        config_paths=[
            "~/.cursor/config.json",
            "~/Library/Application Support/Cursor/config.json",
            "%APPDATA%\\Cursor\\config.json",
        ],
        detect_commands=["cursor --version"],
        api_key_env="CURSOR_API_KEY",
        base_url_field="openaiBaseUrl",
        api_key_field="openaiApiKey",
    ),
    "trae": ToolConfig(
        name="trae",
        display_name="TRAE",
        protocol="openai",
        config_paths=[
            "~/.trae/config.json",
            "~/Library/Application Support/Trae/config.json",
            "%APPDATA%\\Trae\\config.json",
        ],
        detect_commands=["trae --version"],
        notes="TRAE 同时支持 OpenAI 和 Anthropic 协议，需分别配置",
    ),
    "roo-code": ToolConfig(
        name="roo-code",
        display_name="Roo Code",
        protocol="openai",
        config_paths=[
            "~/.roo/config.json",
            "~/Library/Application Support/Roo Code/config.json",
            "%APPDATA%\\Roo Code\\config.json",
        ],
        detect_commands=["roo --version"],
    ),
    "codex": ToolConfig(
        name="codex",
        display_name="Codex (OpenAI)",
        protocol="openai",
        config_paths=[
            "~/.codex/config.json",
            "~/.config/codex/config.json",
        ],
        detect_commands=["codex --version"],
        api_key_env="OPENAI_API_KEY",
    ),
    "copilot-cli": ToolConfig(
        name="copilot-cli",
        display_name="GitHub Copilot CLI",
        protocol="openai",
        config_paths=[
            "~/.config/github-copilot/config.json",
            "~/.copilot/config.json",
        ],
        detect_commands=["gh copilot --version"],
    ),
    "zed": ToolConfig(
        name="zed",
        display_name="Zed",
        protocol="openai",
        config_paths=[
            "~/.config/zed/settings.json",
            "~/Library/Application Support/Zed/settings.json",
            "%APPDATA%\\Zed\\settings.json",
        ],
        detect_commands=["zed --version"],
        config_format="json",
        notes="Zed 使用 settings.json 中的 language_model 配置",
    ),
    "autogen": ToolConfig(
        name="autogen",
        display_name="AutoGen",
        protocol="openai",
        config_paths=[
            "~/.autogen/config.json",
            "./autogen_config.json",
        ],
        detect_commands=["python -c 'import autogen'"],
        api_key_env="OPENAI_API_KEY",
    ),
    "goose": ToolConfig(
        name="goose",
        display_name="Goose",
        protocol="openai",
        config_paths=[
            "~/.config/goose/config.json",
            "~/.goose/config.json",
        ],
        detect_commands=["goose --version"],
    ),
    # ── Anthropic 兼容 ──
    "openclaw": ToolConfig(
        name="openclaw",
        display_name="OpenClaw",
        protocol="anthropic",
        config_paths=[
            "~/.openclaw/openclaw.json",
        ],
        detect_commands=["openclaw --version"],
        notes="OpenClaw 需要源码补丁 + 配置修改",
    ),
    "opencode": ToolConfig(
        name="opencode",
        display_name="OpenCode",
        protocol="anthropic",
        config_paths=[
            "~/.opencode/config.json",
            "~/.config/opencode/config.json",
        ],
        detect_commands=["opencode --version"],
    ),
    "kilo-code": ToolConfig(
        name="kilo-code",
        display_name="Kilo Code",
        protocol="anthropic",
        config_paths=[
            "~/.kilo/config.json",
            "~/Library/Application Support/Kilo Code/config.json",
            "%APPDATA%\\Kilo Code\\config.json",
        ],
        detect_commands=["kilo --version"],
    ),
}


# ── 检测 ──────────────────────────────────────────────────────────────────


def detect_tool(tool: ToolConfig) -> dict:
    """检测工具是否已安装"""
    result = {
        "installed": False,
        "config_found": False,
        "config_path": None,
        "version": None,
    }

    # 检测命令
    for cmd in tool.detect_commands:
        try:
            proc = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=10
            )
            if proc.returncode == 0:
                result["installed"] = True
                result["version"] = proc.stdout.strip()[:100]
                break
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue

    # 检测配置文件
    for path_str in tool.config_paths:
        path = Path(os.path.expandvars(os.path.expanduser(path_str)))
        if path.exists():
            result["config_found"] = True
            result["config_path"] = str(path)
            result["installed"] = True
            break

    return result


def detect_all() -> dict[str, dict]:
    """检测所有工具"""
    results = {}
    for name, tool in TOOLS.items():
        results[name] = detect_tool(tool)
    return results


# ── 修复 ──────────────────────────────────────────────────────────────────


def fix_openai_tool(
    tool: ToolConfig,
    config_path: str,
    proxy_url: str,
    api_key: str,
    dry_run: bool = False,
) -> bool:
    """修复 OpenAI 兼容工具"""
    path = Path(config_path)

    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                config = json.load(f)
        else:
            config = {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        config = {}

    # 备份
    if path.exists() and not dry_run:
        backup_path = path.with_suffix(".bak")
        shutil.copy2(path, backup_path)
        print(f"  📦 备份: {backup_path}")

    # 应用配置
    base_url = f"{proxy_url}/v1"
    config[tool.base_url_field] = base_url
    if api_key:
        config[tool.api_key_field] = api_key

    if dry_run:
        print(f"  🔍 [DRY RUN] 将写入: {json.dumps(config, indent=2, ensure_ascii=False)}")
        return True

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    print(f"  ✅ 已写入: {path}")
    return True


def fix_anthropic_tool(
    tool: ToolConfig,
    config_path: str,
    proxy_url: str,
    api_key: str,
    dry_run: bool = False,
) -> bool:
    """修复 Anthropic 兼容工具"""
    path = Path(config_path)

    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                config = json.load(f)
        else:
            config = {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        config = {}

    # 备份
    if path.exists() and not dry_run:
        backup_path = path.with_suffix(".bak")
        shutil.copy2(path, backup_path)
        print(f"  📦 备份: {backup_path}")

    # Anthropic 工具使用 anthropic_base_url 或类似字段
    config["anthropic_base_url"] = f"{proxy_url}/v1"
    if api_key:
        config["anthropic_api_key"] = api_key

    if dry_run:
        print(f"  🔍 [DRY RUN] 将写入: {json.dumps(config, indent=2, ensure_ascii=False)}")
        return True

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    print(f"  ✅ 已写入: {path}")
    return True


def fix_openclaw(
    config_path: str,
    proxy_url: str,
    api_key: str,
    dry_run: bool = False,
) -> bool:
    """修复 OpenClaw（配置修改 + 源码补丁提示）"""
    path = Path(config_path)

    if not path.exists():
        print(f"  ❌ 配置文件不存在: {path}")
        return False

    try:
        with open(path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError):
        print(f"  ❌ 配置文件格式错误: {path}")
        return False

    # 备份
    if not dry_run:
        backup_path = path.with_suffix(".bak")
        shutil.copy2(path, backup_path)
        print(f"  📦 备份: {backup_path}")

    # 确保 models 配置正确
    providers = config.get("models", {}).get("providers", {})
    if "xiaomi-coding" in providers:
        models = providers["xiaomi-coding"].get("models", [])
        for model in models:
            if "mimo-v2.5" in model.get("id", ""):
                if not model.get("reasoning"):
                    model["reasoning"] = True
                    print(f"  🔧 设置 {model['id']} reasoning=true")
                if "compat" not in model:
                    model["compat"] = {"thinkingFormat": "deepseek"}
                    print(f"  🔧 设置 {model['id']} thinkingFormat=deepseek")

    if dry_run:
        print(f"  🔍 [DRY RUN] OpenClaw 配置将更新")
        return True

    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    print(f"  ✅ OpenClaw 配置已更新: {path}")
    print(f"  ⚠️  还需要应用源码补丁: python scripts/patch_openclaw.py")
    return True


# ── 主流程 ────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="MiMo 兼容性一键修复脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--auto", action="store_true", help="自动检测并修复所有工具")
    parser.add_argument("--detect", action="store_true", help="仅检测，不修改")
    parser.add_argument("--tool", action="append", help="修复指定工具（可多次指定）")
    parser.add_argument("--proxy", default="http://127.0.0.1:9090", help="代理地址")
    parser.add_argument("--api-key", default="", help="MiMo API Key")
    parser.add_argument("--dry-run", action="store_true", help="模拟运行，不实际修改")
    parser.add_argument("--list", action="store_true", help="列出所有支持的工具")
    args = parser.parse_args()

    if args.list:
        print("\n支持的工具：\n")
        for name, tool in TOOLS.items():
            print(f"  {name:<15} {tool.display_name:<20} ({tool.protocol})")
        return

    if args.detect:
        print("\n🔍 检测已安装的工具...\n")
        results = detect_all()
        for name, info in results.items():
            tool = TOOLS[name]
            status = "✅ 已安装" if info["installed"] else "❌ 未安装"
            config = "📄 有配置" if info["config_found"] else "📄 无配置"
            version = f" ({info['version']})" if info.get("version") else ""
            path = f" → {info['config_path']}" if info.get("config_path") else ""
            print(f"  {status} {tool.display_name:<20}{version}  {config}{path}")
        return

    if not args.auto and not args.tool:
        parser.print_help()
        return

    # 确定要修复的工具
    if args.auto:
        tools_to_fix = list(TOOLS.keys())
    else:
        tools_to_fix = args.tool

    print(f"\n🛠️  MiMo 兼容性修复\n")
    print(f"代理地址: {args.proxy}")
    print(f"Dry Run: {'是' if args.dry_run else '否'}\n")

    # 检测并修复
    success = 0
    failed = 0
    skipped = 0

    for tool_name in tools_to_fix:
        if tool_name not in TOOLS:
            print(f"⚠️  未知工具: {tool_name}")
            continue

        tool = TOOLS[tool_name]
        print(f"\n📦 {tool.display_name} ({tool.protocol})")

        # 检测
        info = detect_tool(tool)
        if not info["installed"]:
            print(f"  ⏭️  未安装，跳过")
            skipped += 1
            continue

        config_path = info.get("config_path")
        if not config_path:
            # 使用第一个配置路径
            config_path = os.path.expandvars(
                os.path.expanduser(tool.config_paths[0])
            )

        try:
            if tool_name == "openclaw":
                ok = fix_openclaw(config_path, args.proxy, args.api_key, args.dry_run)
            elif tool.protocol == "openai":
                ok = fix_openai_tool(tool, config_path, args.proxy, args.api_key, args.dry_run)
            else:
                ok = fix_anthropic_tool(tool, config_path, args.proxy, args.api_key, args.dry_run)

            if ok:
                success += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  ❌ 修复失败: {e}")
            failed += 1

    # 汇总
    print(f"\n{'='*50}")
    print(f"✅ 成功: {success}  ❌ 失败: {failed}  ⏭️  跳过: {skipped}")

    if success > 0 and not args.dry_run:
        print(f"\n💡 提示：")
        print(f"   1. 确保代理服务器正在运行: python proxy/server.py")
        print(f"   2. OpenClaw 还需要源码补丁: python scripts/patch_openclaw.py")
        print(f"   3. 重启相关工具以使配置生效")


if __name__ == "__main__":
    main()
