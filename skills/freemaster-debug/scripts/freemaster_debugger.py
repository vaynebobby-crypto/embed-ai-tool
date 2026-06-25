#!/usr/bin/env python3
"""FreeMASTER 调试主控工具。

为 `freemaster-debug` skill 提供一体化执行入口，支持：

- 环境探测与就绪检查
- 调用 .pmpx 生成器
- 启动 FreeMASTER GUI 加载项目
- 输出结构化的调试会话报告

模式:
  start     — 生成 .pmpx 并启动 FreeMASTER（默认）
  generate  — 仅生成 .pmpx，不启动 GUI
"""

from __future__ import annotations

import argparse
import platform
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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

_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILLS_DIR = _SCRIPT_DIR.parent.parent
for _candidate in [_SKILLS_DIR / "shared", _SKILLS_DIR.parent / "shared"]:
    if (_candidate / "tool_config.py").exists():
        sys.path.insert(0, str(_candidate))
        break
from tool_config import get_tool_path

from freemaster_detect import detect_environment, print_detect_report
from freemaster_pmpx_gen import generate_pmpx


@dataclass
class DebugResult:
    status: str  # success, partial_success, blocked, failure
    summary: str
    mode: str | None = None
    freemaster_exe: str | None = None
    pmpx_path: str | None = None
    elf_path: str | None = None
    vars_count: int = 0
    evidence: list[str] = field(default_factory=list)
    failure_category: str | None = None


def find_freemaster() -> str | None:
    """查找 FreeMASTER.exe，优先级：配置文件 → PATH → 安装路径盲搜."""
    configured = get_tool_path("freemaster")
    if configured and Path(configured).is_file():
        return configured

    import shutil
    for exe in ["pcmaster.exe", "FreeMASTER.exe", "FreeMASTER Lite.exe"]:
        found = shutil.which(exe)
        if found:
            return found

    env = detect_environment()
    installations = env.get("freemaster", {}).get("installations", [])
    if installations:
        return str(installations[0]["path"])

    return None


def launch_freemaster(freemaster_exe: str, pmpx_path: str) -> bool:
    """使用 PowerShell Start-Process 启动 FreeMASTER 并打开指定项目."""
    cmd = [
        "powershell", "-Command",
        f"Start-Process '{freemaster_exe}' -ArgumentList '\"{pmpx_path}\"'",
    ]
    print(f"🚀 启动 FreeMASTER: {freemaster_exe} \"{pmpx_path}\"")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✅ FreeMASTER 已启动")
            return True
        else:
            stderr = (result.stderr or "").strip()
            if stderr:
                print(f"⚠️ 启动警告: {stderr}")
            return True
    except subprocess.TimeoutExpired:
        print("⚠️ 启动命令超时，但 FreeMASTER 可能已在后台启动")
        return True
    except FileNotFoundError:
        print(f"❌ 未找到 FreeMASTER: {freemaster_exe}")
        return False
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        return False


def run_start_mode(args: argparse.Namespace) -> DebugResult:
    """start 模式：生成 .pmpx 并启动 FreeMASTER."""
    evidence: list[str] = []

    if platform.system() != "Windows":
        return DebugResult(
            status="blocked",
            summary="FreeMASTER 仅支持 Windows 平台",
            failure_category="platform-unsupported",
            evidence=[f"当前平台: {platform.system()}"],
        )

    freemaster_exe = find_freemaster()
    if not freemaster_exe:
        return DebugResult(
            status="blocked",
            summary="未找到 FreeMASTER 安装",
            failure_category="environment-missing",
            evidence=["搜索路径: C:\\NXP\\, C:\\Program Files\\NXP\\, PATH"],
        )
    evidence.append(f"FreeMASTER: {freemaster_exe}")

    if not args.elf:
        return DebugResult(
            status="blocked",
            summary="缺少 ELF 固件文件路径",
            failure_category="artifact-missing",
            evidence=evidence,
        )
    elf_path = str(Path(args.elf).resolve())
    if not Path(elf_path).exists():
        return DebugResult(
            status="blocked",
            summary=f"ELF 文件不存在: {elf_path}",
            failure_category="artifact-missing",
            evidence=evidence,
        )
    evidence.append(f"ELF: {elf_path}")

    device = args.device
    if not device:
        return DebugResult(
            status="blocked",
            summary="缺少目标 MCU 型号（--device）",
            failure_category="ambiguous-context",
            evidence=evidence,
        )
    evidence.append(f"目标设备: {device}")

    output_dir = Path(args.output_dir) if args.output_dir else Path.cwd()
    pmpx_path = output_dir / f"{device}.pmpx"

    variables = [v.strip() for v in args.vars.split(",") if v.strip()] if args.vars else []

    gen_result = generate_pmpx(
        output_path=pmpx_path,
        elf_path=elf_path,
        device=device,
        template_path=Path(args.template) if args.template else None,
        variables=variables,
        sample_rate_hz=args.sample_rate,
        jlink_speed_khz=args.jlink_speed,
    )

    if gen_result["status"] == "failure":
        return DebugResult(
            status="failure",
            summary=f".pmpx 生成失败: {gen_result.get('error', '未知错误')}",
            failure_category="environment-missing",
            evidence=evidence + [f"error: {gen_result.get('error')}"],
        )

    pmpx_str = gen_result["path"]
    vars_count = gen_result["vars_count"]
    evidence.append(f".pmpx: {pmpx_str}")

    launched = launch_freemaster(freemaster_exe, pmpx_str)

    if launched:
        summary = f"FreeMASTER 已启动，项目 {Path(pmpx_str).name} 已加载"
        if vars_count > 0:
            summary += f"（预置 {vars_count} 个变量）"

        return DebugResult(
            status="success",
            summary=summary,
            mode="start",
            freemaster_exe=freemaster_exe,
            pmpx_path=pmpx_str,
            elf_path=elf_path,
            vars_count=vars_count,
            evidence=evidence,
        )
    else:
        return DebugResult(
            status="partial_success",
            summary=f".pmpx 已生成但 FreeMASTER 启动失败。请手动打开: {pmpx_str}",
            mode="start",
            pmpx_path=pmpx_str,
            elf_path=elf_path,
            vars_count=vars_count,
            evidence=evidence + ["⚠️ FreeMASTER 启动失败"],
            failure_category="environment-missing",
        )


def run_generate_mode(args: argparse.Namespace) -> DebugResult:
    """generate 模式：仅生成 .pmpx，不启动 GUI."""
    evidence: list[str] = []

    if platform.system() != "Windows":
        evidence.append(f"⚠️ 当前平台 {platform.system()} 不支持运行 FreeMASTER，但 .pmpx 文件仍可生成")

    if not args.elf:
        return DebugResult(
            status="blocked",
            summary="缺少 ELF 固件文件路径",
            failure_category="artifact-missing",
        )
    elf_path = str(Path(args.elf).resolve())
    if not Path(elf_path).exists():
        return DebugResult(
            status="blocked",
            summary=f"ELF 文件不存在: {elf_path}",
            failure_category="artifact-missing",
        )
    evidence.append(f"ELF: {elf_path}")

    if not args.device:
        return DebugResult(
            status="blocked",
            summary="缺少目标 MCU 型号（--device）",
            failure_category="ambiguous-context",
        )
    device = args.device
    evidence.append(f"目标设备: {device}")

    output_dir = Path(args.output_dir) if args.output_dir else Path.cwd()
    pmpx_path = output_dir / f"{device}.pmpx"

    variables = [v.strip() for v in args.vars.split(",") if v.strip()] if args.vars else []

    gen_result = generate_pmpx(
        output_path=pmpx_path,
        elf_path=elf_path,
        device=device,
        template_path=Path(args.template) if args.template else None,
        variables=variables,
        sample_rate_hz=args.sample_rate,
        jlink_speed_khz=args.jlink_speed,
    )

    if gen_result["status"] == "failure":
        return DebugResult(
            status="failure",
            summary=f".pmpx 生成失败: {gen_result.get('error', '未知错误')}",
            failure_category="environment-missing",
            evidence=evidence + [f"error: {gen_result.get('error')}"],
        )

    return DebugResult(
        status=gen_result["status"],
        summary=f".pmpx 已生成: {gen_result['path']}",
        mode="generate",
        pmpx_path=gen_result["path"],
        elf_path=elf_path,
        vars_count=gen_result["vars_count"],
        evidence=evidence,
    )


def print_debug_report(result: DebugResult) -> None:
    """打印调试结果报告."""
    icon = {"success": "✅", "partial_success": "⚠️", "blocked": "⛔", "failure": "❌"}.get(result.status, "❓")
    print(f"\n📊 FreeMASTER 调试结果: {icon} {result.summary}")

    if result.mode:
        print(f"\n  模式:           {result.mode}")
    if result.freemaster_exe:
        print(f"  FreeMASTER:     {result.freemaster_exe}")
    if result.elf_path:
        print(f"  ELF:            {result.elf_path}")
    if result.pmpx_path:
        print(f"  .pmpx:          {result.pmpx_path}")
    if result.vars_count > 0:
        print(f"  预置变量:       {result.vars_count} 个")

    if result.evidence:
        print(f"\n📝 证据:")
        for line in result.evidence:
            print(f"  {line}")

    if result.failure_category:
        print(f"\n  失败分类: {result.failure_category}")

    if result.status == "success":
        print("\n💡 下一步: 在 FreeMASTER GUI 中将变量拖入 Scope/Oscilloscope 开始监控")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="FreeMASTER 调试主控工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --elf build/app.elf --device GD32F450IK
  %(prog)s --elf build/app.elf --device GD32F450IK --vars adc_value,pid_output
  %(prog)s --elf build/app.elf --device STM32F407VG --mode generate
  %(prog)s --detect
        """,
    )
    parser.add_argument("--detect", action="store_true", help="仅探测 FreeMASTER 环境")
    parser.add_argument("--elf", help="带符号的 ELF 文件路径")
    parser.add_argument("--device", help="目标 MCU 型号（如 GD32F450IK）")
    parser.add_argument(
        "--mode", choices=["start", "generate"], default="start",
        help="执行模式: start（默认，生成+启动），generate（仅生成）",
    )
    parser.add_argument("--vars", default="", help="预置变量名，逗号分隔")
    parser.add_argument("--sample-rate", type=int, default=1000, help="Recorder 采样率 Hz（默认 1000）")
    parser.add_argument("--jlink-speed", type=int, default=4000, help="J-Link SWD 速度 kHz（默认 4000）")
    parser.add_argument("--output-dir", default=None, help=".pmpx 输出目录（默认当前工作目录）")
    parser.add_argument("--template", default=None, help="参考 .pmpx 模板路径")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.detect:
        env = detect_environment()
        print_detect_report(env)
        ok = env["freemaster"]["available"] and env["platform"]["supported"]
        return 0 if ok else 1

    if args.mode == "generate":
        result = run_generate_mode(args)
    else:
        result = run_start_mode(args)

    print_debug_report(result)

    status_codes = {"success": 0, "partial_success": 0, "blocked": 1, "failure": 1}
    return status_codes.get(result.status, 1)


if __name__ == "__main__":
    sys.exit(main())
