#!/usr/bin/env python3
"""
OpenClaw 源码补丁脚本

为 OpenClaw 的 pi-ai 库打补丁，修复 MiMo API 的 reasoning_content 兼容性问题。

问题：MiMo API 要求 assistant 消息包含 tool_calls 时必须同时包含
      reasoning_content 字段（即使是空字符串），否则返回 400 错误。

补丁：在 convertMessages 函数中，当 provider 为 xiaomi-coding 且
      assistant 消息有 tool_calls 但无 reasoning_content 时，注入空字符串。

用法：
    python patch_openclaw.py              # 应用补丁
    python patch_openclaw.py --verify     # 验证补丁
    python patch_openclaw.py --revert     # 还原补丁
    python patch_openclaw.py --path /custom/path  # 指定 OpenClaw 安装路径
"""

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

# ── 补丁配置 ──────────────────────────────────────────────────────────────

# OpenClaw 安装路径（自动检测）
OPENCLAW_PATHS = [
    "/usr/local/lib/node_modules/openclaw",
    "/usr/lib/node_modules/openclaw",
    os.path.expanduser("~/.openclaw/node_modules/openclaw"),
    os.path.expanduser("~/.npm/_npx/*/node_modules/openclaw"),
]

# 需要补丁的文件（相对于 OpenClaw 安装路径）
TARGET_FILE = "node_modules/@mariozechner/pi-ai/dist/providers/openai-completions.js"

# 补丁标记（用于检测是否已打补丁）
PATCH_MARKER = "// MIMO_COMPAT_PATCH"
PATCH_MARKER_END = "// MIMO_COMPAT_PATCH_END"

# 补丁代码
PATCH_CODE = '''
    // MIMO_COMPAT_PATCH - MiMo API reasoning_content compatibility fix
    // When assistant message has tool_calls but no reasoning_content,
    // extract real thinking content from blocks (falls back to empty string).
    if (assistantMsg.tool_calls && assistantMsg.tool_calls.length > 0 
        && assistantMsg.reasoning_content === undefined 
        && model && model.provider && model.provider.startsWith("xiaomi")) {
      if (nonEmptyThinkingBlocks && nonEmptyThinkingBlocks.length > 0) {
        assistantMsg.reasoning_content = nonEmptyThinkingBlocks.map((block) => sanitizeSurrogates(block.thinking)).join("\n\n");
      } else {
        assistantMsg.reasoning_content = "";
      }
    }
    // MIMO_COMPAT_PATCH_END
'''


# ── 辅助函数 ──────────────────────────────────────────────────────────────


def find_openclaw(custom_path: str = "") -> Path | None:
    """查找 OpenClaw 安装路径"""
    if custom_path:
        p = Path(custom_path)
        if p.exists():
            return p
        print(f"❌ 指定路径不存在: {p}")
        return None

    for path_str in OPENCLAW_PATHS:
        # 处理通配符
        if "*" in path_str:
            import glob
            matches = glob.glob(path_str)
            if matches:
                return Path(matches[0])
        else:
            p = Path(path_str)
            if p.exists():
                return p

    # 尝试 which openclaw
    try:
        import subprocess
        result = subprocess.run(
            ["which", "openclaw"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            bin_path = Path(result.stdout.strip()).resolve()
            # 通常是 /usr/local/bin/openclaw -> ../lib/node_modules/openclaw/bin/openclaw
            openclaw_path = bin_path.parent.parent / "lib" / "node_modules" / "openclaw"
            if openclaw_path.exists():
                return openclaw_path
    except Exception:
        pass

    return None


def get_target_file(openclaw_path: Path) -> Path | None:
    """获取需要补丁的目标文件"""
    target = openclaw_path / TARGET_FILE
    if target.exists():
        return target
    return None


def is_patched(content: str) -> bool:
    """检查文件是否已打补丁"""
    return PATCH_MARKER in content


# ── 补丁操作 ──────────────────────────────────────────────────────────────


def apply_patch(file_path: Path) -> bool:
    """应用补丁"""
    content = file_path.read_text(encoding="utf-8")

    if is_patched(content):
        print("✅ 补丁已存在，无需重复应用")
        return True

    # 查找插入点：在 assistant 消息处理循环中，tool_calls 检查之后
    # 寻找模式：if (assistantMsg.tool_calls 或类似的处理逻辑
    patterns = [
        # 模式1：常见的 tool_calls 处理
        (r'(\s*if\s*\(\s*[\w.]+\.tool_calls\s*)', r'\1'),
        # 模式2：assistant 消息处理
        (r'(\s*if\s*\(\s*msg\.role\s*===?\s*["\']assistant["\']\s*\))', r'\1'),
    ]

    # 尝试找到合适的插入点
    lines = content.split("\n")
    insert_line = -1

    for i, line in enumerate(lines):
        stripped = line.strip()
        # 查找 assistant 消息处理区域中的 tool_calls 相关代码
        if "tool_calls" in stripped and ("assistant" in stripped.lower() or 
                                          "assistantMsg" in stripped or
                                          "msg.role" in stripped):
            # 找到 tool_calls 相关的 if 块，在其后插入
            # 往后找最近的 } 或下一个语句
            for j in range(i, min(i + 20, len(lines))):
                if lines[j].strip().startswith("}") or (j > i and lines[j].strip() and not lines[j].strip().startswith("//")):
                    insert_line = j
                    break
            if insert_line > 0:
                break

    if insert_line < 0:
        # 备选方案：在文件末尾的函数内查找合适位置
        print("⚠️  未找到理想的插入点，尝试备选方案...")

        # 查找 convertMessages 函数
        for i, line in enumerate(lines):
            if "convertMessages" in line and ("function" in line or "=>" in line):
                # 在函数开始后查找
                for j in range(i, min(i + 100, len(lines))):
                    if "tool_calls" in lines[j]:
                        insert_line = j + 1
                        break
                break

    if insert_line < 0:
        print("❌ 无法找到合适的插入点，请手动打补丁")
        print(f"   文件: {file_path}")
        print(f"   需要在 assistant 消息处理逻辑中添加以下代码：")
        print(PATCH_CODE)
        return False

    # 备份
    backup_path = file_path.with_suffix(".js.bak")
    if not backup_path.exists():
        shutil.copy2(file_path, backup_path)
        print(f"📦 备份: {backup_path}")

    # 插入补丁
    patch_lines = PATCH_CODE.strip().split("\n")
    for idx, patch_line in enumerate(patch_lines):
        lines.insert(insert_line + idx, patch_line)

    file_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ 补丁已应用: {file_path}")
    print(f"   插入位置: 第 {insert_line + 1} 行")
    return True


def verify_patch(file_path: Path) -> bool:
    """验证补丁"""
    content = file_path.read_text(encoding="utf-8")
    if is_patched(content):
        print("✅ 补丁验证通过")
        return True
    else:
        print("❌ 补丁未应用")
        return False


def revert_patch(file_path: Path) -> bool:
    """还原补丁"""
    backup_path = file_path.with_suffix(".js.bak")
    if backup_path.exists():
        shutil.copy2(backup_path, file_path)
        print(f"✅ 已还原: {file_path}")
        return True

    # 没有备份，尝试手动移除补丁
    content = file_path.read_text(encoding="utf-8")
    if not is_patched(content):
        print("ℹ️  文件未打补丁，无需还原")
        return True

    # 移除补丁代码
    start = content.find(PATCH_MARKER)
    end = content.find(PATCH_MARKER_END)
    if start >= 0 and end >= 0:
        end += len(PATCH_MARKER_END)
        # 移除整行（包括前后换行）
        while start > 0 and content[start - 1] == "\n":
            start -= 1
        while end < len(content) and content[end] == "\n":
            end += 1
        new_content = content[:start] + content[end:]
        file_path.write_text(new_content, encoding="utf-8")
        print(f"✅ 补丁已移除: {file_path}")
        return True

    print("❌ 无法自动移除补丁，请手动编辑")
    return False


# ── 主流程 ────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="OpenClaw 源码补丁脚本")
    parser.add_argument("--path", default="", help="OpenClaw 安装路径")
    parser.add_argument("--verify", action="store_true", help="验证补丁")
    parser.add_argument("--revert", action="store_true", help="还原补丁")
    args = parser.parse_args()

    print("\n🔧 OpenClaw MiMo 兼容性补丁工具\n")

    # 查找 OpenClaw
    openclaw_path = find_openclaw(args.path)
    if not openclaw_path:
        print("❌ 未找到 OpenClaw 安装路径")
        print("   请通过 --path 参数指定，例如：")
        print("   python patch_openclaw.py --path /usr/local/lib/node_modules/openclaw")
        sys.exit(1)

    print(f"📂 OpenClaw 路径: {openclaw_path}")

    # 查找目标文件
    target = get_target_file(openclaw_path)
    if not target:
        print(f"❌ 未找到目标文件: {TARGET_FILE}")
        print(f"   请确认 OpenClaw 安装完整")
        sys.exit(1)

    print(f"📄 目标文件: {target}")

    # 执行操作
    if args.verify:
        ok = verify_patch(target)
    elif args.revert:
        ok = revert_patch(target)
    else:
        ok = apply_patch(target)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
