#!/usr/bin/env python3
"""FreeMASTER 安装自动探测工具。

为 `freemaster-debug` skill 提供可重复调用的探测入口，支持：

- 按已知安装路径盲搜 FreeMASTER.exe
- 识别 Lite 版与完整版
- 支持保存探测结果到工具配置
"""

from __future__ import annotations

import argparse
import platform
import shutil
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILLS_DIR = _SCRIPT_DIR.parent.parent
for _candidate in [_SKILLS_DIR / "shared", _SKILLS_DIR.parent / "shared"]:
    if (_candidate / "tool_config.py").exists():
        sys.path.insert(0, str(_candidate))
        break
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from tool_config import get_tool_path, set_tool_path


FREEMASTER_SEARCH_ROOTS: list[str] = [
    "C:\\NXP",
    "C:\\Program Files\\NXP",
    "C:\\Program Files (x86)\\NXP",
    "D:\\NXP",
]

FREEMASTER_EXE_PATTERNS: list[str] = [
    "FreeMASTER*.exe",
    "**/FreeMASTER*.exe",
]


def _is_freemaster_lite(path: Path) -> bool:
    """通过文件名判断是否为 Lite 版."""
    return "lite" in path.stem.lower()


def _search_known_paths() -> list[Path]:
    """在已知安装根目录下盲搜 FreeMASTER.exe."""
    found: list[Path] = []
    for root in FREEMASTER_SEARCH_ROOTS:
        root_path = Path(root)
        if not root_path.is_dir():
            continue
        for pattern in FREEMASTER_EXE_PATTERNS:
            try:
                for candidate in root_path.glob(pattern):
                    if candidate.is_file() and candidate.suffix == ".exe":
                        # 过滤卸载程序
                        if "unins" in candidate.stem.lower():
                            continue
                        # 去重（可能同一文件匹配多个 pattern）
                        resolved = candidate.resolve()
                        if resolved not in found:
                            found.append(resolved)
            except OSError:
                continue
    return found


def search_freemaster() -> list[dict[str, object]]:
    """搜索所有 FreeMASTER 安装，返回列表，每项含 path/version/is_lite."""
    configured = get_tool_path("freemaster")
    results: list[dict[str, object]] = []
    seen: set[str] = set()

    # 1. 配置文件中的路径
    if configured:
        p = Path(configured)
        if p.is_file():
            seen.add(str(p.resolve()))
            results.append({
                "path": str(p.resolve()),
                "version": "configured",
                "is_lite": _is_freemaster_lite(p),
            })

    # 2. PATH 环境变量
    for exe_name in ["FreeMASTER.exe", "FreeMASTER Lite.exe"]:
        found = shutil.which(exe_name)
        if found:
            p = Path(found)
            key = str(p.resolve())
            if key not in seen:
                seen.add(key)
                results.append({
                    "path": key,
                    "version": "PATH",
                    "is_lite": "lite" in p.stem.lower(),
                })

    # 3. 已知安装路径盲搜
    for p in _search_known_paths():
        key = str(p)
        if key not in seen:
            seen.add(key)
            results.append({
                "path": key,
                "version": "auto-detected",
                "is_lite": _is_freemaster_lite(p),
            })

    return results


def detect_environment() -> dict[str, object]:
    """探测 FreeMASTER 环境，返回结构化结果."""
    installations = search_freemaster()
    available = len(installations) > 0

    result: dict[str, object] = {
        "freemaster": {
            "available": available,
            "installations": installations,
            "preferred": installations[0] if available else None,
        },
        "platform": {
            "system": platform.system(),
            "supported": platform.system() == "Windows",
        },
    }
    return result


def print_detect_report(env: dict[str, object]) -> None:
    """打印格式化的探测报告."""
    fm = env["freemaster"]
    plat = env["platform"]

    print("\n📊 FreeMASTER 环境探测结果：")

    system_info = plat["system"]
    supported = plat["supported"]
    icon = "✅" if supported else "⚠️"
    print(f"  {icon} 操作系统: {system_info} {'(支持)' if supported else '(不支持 — FreeMASTER 仅 Windows)'}")

    available = fm["available"]
    icon = "✅" if available else "❌"
    print(f"  {icon} FreeMASTER: {'已找到' if available else '未找到'}")

    if available:
        installations = fm["installations"]
        for i, inst in enumerate(installations):
            marker = "⭐" if i == 0 else "  "
            path = inst["path"]
            is_lite = inst["is_lite"]
            flavor = "Lite 版" if is_lite else "完整版"
            print(f"  {marker} {path} ({flavor})")
    else:
        print("    搜索路径:")
        for root in FREEMASTER_SEARCH_ROOTS:
            print(f"      - {root}")
        print("    请在 FreeMASTER 安装后运行:")
        print("      python scripts/em_config.py set freemaster <FreeMASTER.exe 路径>")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="FreeMASTER 安装探测工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --detect
  %(prog)s --detect --save-config
        """,
    )
    parser.add_argument("--detect", action="store_true", help="探测 FreeMASTER 安装")
    parser.add_argument("--save-config", action="store_true", help="探测成功后保存工具路径到配置")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.detect:
        env = detect_environment()
        print_detect_report(env)

        if args.save_config and env["freemaster"]["available"]:
            inst = env["freemaster"]["preferred"]
            if inst:
                cfg_path = set_tool_path("freemaster", str(inst["path"]))
                print(f"  💾 FreeMASTER 路径已保存到 {cfg_path}")

        ok = env["freemaster"]["available"] and env["platform"]["supported"]
        return 0 if ok else 1

    # 默认行为：打印报告
    env = detect_environment()
    print_detect_report(env)
    ok = env["freemaster"]["available"] and env["platform"]["supported"]
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
