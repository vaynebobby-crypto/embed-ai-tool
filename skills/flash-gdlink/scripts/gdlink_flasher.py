#!/usr/bin/env python3
"""GigaDevice GD-Link 烧录工具。

为 `flash-gdlink` skill 提供可重复调用的执行入口，支持：

- 探测 GD_Link_CLI.exe 环境
- 通过 stdin 管道驱动 GD_Link_CLI 交互式命令行
- 支持 ELF/HEX/BIN 烧录
- 输出结构化的烧录结果报告
"""

from __future__ import annotations

import argparse
import configparser
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

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
from tool_config import get_tool_path, set_tool_path

ARTIFACT_EXTENSIONS = {".elf": "elf", ".hex": "hex", ".bin": "bin", ".axf": "elf"}
ARTIFACT_PRIORITY = {"elf": 1, "hex": 2, "bin": 3}


@dataclass
class FlashResult:
    status: str  # success, failure, blocked
    summary: str
    command: str | None = None
    device: str | None = None
    interface: str | None = None
    speed: int | None = None
    artifact_path: str | None = None
    artifact_kind: str | None = None
    verified: bool = False
    failure_category: str | None = None
    evidence: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# GD_Link_CLI 探测
# ---------------------------------------------------------------------------

def _gdlink_cli_candidates() -> list[str]:
    candidates = []
    configured = get_tool_path("gdlink-cli")
    if configured:
        candidates.append(configured)

    if platform.system() == "Windows":
        candidates.append("GD_Link_CLI.exe")
        # 搜索常见安装路径
        for drive in ["D:\\", "C:\\"]:
            try:
                for root, dirs, _files in os.walk(drive):
                    depth = root.replace(drive, "").count(os.sep)
                    if depth > 5:
                        dirs.clear()
                        continue
                    if "GD_Link_CLI.exe" in _files:
                        candidates.append(str(Path(root) / "GD_Link_CLI.exe"))
            except (PermissionError, OSError):
                pass

    return candidates


def find_gdlink_cli() -> str | None:
    for candidate in _gdlink_cli_candidates():
        path = shutil.which(candidate)
        if path:
            return path
        if Path(candidate).is_file():
            return candidate
    return None


def check_gdlink() -> tuple[bool, str | None, str | None]:
    gdlink = find_gdlink_cli()
    if not gdlink:
        return False, None, None

    try:
        proc = subprocess.Popen(
            [gdlink],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        proc.stdin.write("q\n")
        proc.stdin.flush()
        try:
            stdout, stderr = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()

        output = stdout + "\n" + stderr
        version = None
        for line in output.split("\n"):
            line_stripped = line.strip()
            if "GD-Link" in line_stripped or "GigaDevice" in line_stripped:
                version = line_stripped
                break
            if re.search(r'v?\d+\.\d+', line_stripped):
                version = line_stripped
                break
        return True, gdlink, version
    except Exception:
        return True, gdlink, None


# ---------------------------------------------------------------------------
# GDConfig.ini 解析
# ---------------------------------------------------------------------------

def read_gdconfig(cli_path: str) -> dict[str, str]:
    config = {}
    cli_dir = Path(cli_path).parent
    ini_path = cli_dir / "GDConfig.ini"
    if not ini_path.exists():
        return config

    try:
        parser = configparser.ConfigParser()
        content = ini_path.read_text(encoding="utf-8", errors="ignore")
        if not content.strip().startswith("["):
            content = "[DEFAULT]\n" + content
        parser.read_string(content)

        for section in parser.sections():
            for key, value in parser.items(section):
                config[key.lower()] = value
        for key, value in parser.defaults().items():
            config[key.lower()] = value
    except Exception:
        pass

    return config


# ---------------------------------------------------------------------------
# 产物验证
# ---------------------------------------------------------------------------

def identify_artifact(artifact_path: str) -> tuple[str | None, int]:
    p = Path(artifact_path)
    if not p.exists():
        return None, 0
    ext = p.suffix.lower()
    kind = ARTIFACT_EXTENSIONS.get(ext)
    try:
        size = p.stat().st_size
    except OSError:
        size = 0
    return kind, size


# ---------------------------------------------------------------------------
# 烧录命令执行（通过 stdin 管道驱动 GD_Link_CLI 交互式命令行）
# ---------------------------------------------------------------------------

def build_gdlink_commands(
    device: str,
    artifact: str,
    artifact_kind: str,
    interface: str,
    speed: int,
    base_address: str | None,
) -> list[str]:
    """生成发送给 GD_Link_CLI 的命令序列。"""
    artifact_posix = artifact.replace("\\", "/")
    commands = []

    if artifact_kind == "bin" and base_address:
        commands.append(f"load {artifact_posix} {base_address}")
    else:
        commands.append(f"load {artifact_posix}")

    commands.append("r")   # reset
    commands.append("g")   # go (运行)
    commands.append("q")   # quit

    return commands


def run_flash(
    gdlink: str,
    commands: list[str],
    verbose: bool,
) -> tuple[bool, list[str]]:
    evidence: list[str] = []

    try:
        proc = subprocess.Popen(
            [gdlink],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError:
        return False, [f" 未找到 GD_Link_CLI: {gdlink}"]

    cmd_sequence = "\n".join(commands) + "\n"
    print(f" 烧录命令序列: {commands}")

    try:
        stdout, stderr = proc.communicate(input=cmd_sequence, timeout=60)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
        return False, [" GD-Link 烧录超时（60 秒）"]

    combined = (stdout or "") + "\n" + (stderr or "")

    if verbose:
        for line in combined.strip().split("\n")[-30:]:
            if line.strip():
                evidence.append(line.strip())

    combined_lower = combined.lower()

    success_markers = ["o.k.", "ok", "success", "verify ok", "programming completed"]
    error_markers = ["error", "fail", "timeout", "cannot", "no target", "no device", "can not"]

    has_success = any(m in combined_lower for m in success_markers)
    has_error = any(m in combined_lower for m in error_markers)

    if proc.returncode == 0 and not has_error:
        print(" 烧录成功，校验通过")
        return True, evidence

    if has_success and not has_error:
        print(" 烧录成功")
        return True, evidence

    last_lines = combined.strip().split("\n")[-15:]
    evidence.extend(last_lines)

    if "no target" in combined_lower or "no device" in combined_lower or "connect" in combined_lower:
        evidence.insert(0, "failure_hint: connection-failure (GD-Link 探针未连接)")
    elif "unknown" in combined_lower or "not supported" in combined_lower:
        evidence.insert(0, "failure_hint: project-config-error (设备名无效)")
    elif "failed" in combined_lower:
        evidence.insert(0, "failure_hint: target-response-abnormal")

    return False, evidence


# ---------------------------------------------------------------------------
# 报告输出
# ---------------------------------------------------------------------------

def print_detect_report(
    available: bool,
    gdlink: str | None,
    version: str | None,
    config: dict[str, str],
) -> None:
    print("\n GD-Link 环境探测结果：")
    status = " " if available else " "
    ver = f" ({version})" if version else ""
    path = f" @ {gdlink}" if gdlink else ""
    print(f"  {status} GD_Link_CLI{ver}{path}")

    if config:
        print(f"\n  GDConfig.ini 参数:")
        for key, value in sorted(config.items()):
            if key not in ("connectinterface", "connectspeed"):
                continue
            print(f"    {key} = {value}")


def print_flash_report(result: FlashResult) -> None:
    icon = {"success": " ", "failure": " ", "blocked": " "}.get(result.status, " ")
    print(f"\n 烧录结果: {icon} {result.summary}")

    if result.command:
        print(f"\n  烧录命令:   {result.command}")
    if result.device:
        print(f"  目标设备:   {result.device}")
    if result.interface:
        print(f"  调试接口:   {result.interface}")
    if result.speed:
        print(f"  连接速度:   {result.speed} kHz")
    if result.artifact_path:
        print(f"  固件产物:   {result.artifact_path} [{result.artifact_kind or '?'}]")
    print(f"  校验: {'是' if result.verified else '否'}")

    if result.evidence:
        print("\n 证据:")
        for line in result.evidence[:15]:
            print(f"  {line}")

    if result.failure_category:
        print(f"\n  失败分类: {result.failure_category}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="GigaDevice GD-Link 烧录工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --detect
  %(prog)s --artifact build/app.elf --device GD32F303RET6
  %(prog)s --artifact build/app.hex --device GD32F303RET6 --interface JTAG
  %(prog)s --artifact build/fw.bin --device GD32F303RET6 --base-address 0x08000000
        """,
    )
    parser.add_argument("--detect", action="store_true", help="探测 GD-Link 环境")
    parser.add_argument("--artifact", help="固件产物路径")
    parser.add_argument("--device", help="目标芯片型号（如 GD32F303RET6）")
    parser.add_argument("--interface", choices=["SWD", "JTAG"], default="SWD", help="调试接口（默认 SWD）")
    parser.add_argument("--speed", type=int, default=10000, help="连接速度 kHz（默认 10000）")
    parser.add_argument("--base-address", help="BIN 文件烧录基地址（十六进制）")
    parser.add_argument("--save-config", action="store_true", help="探测成功后保存工具路径到配置")
    parser.add_argument("-v", "--verbose", action="store_true", help="详细输出")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # 探测模式
    if args.detect:
        available, gdlink, version = check_gdlink()
        config = read_gdconfig(gdlink) if gdlink else {}
        print_detect_report(available, gdlink, version, config)
        if args.save_config and available and gdlink:
            cfg_path = set_tool_path("gdlink-cli", gdlink)
            print(f"   已保存到 {cfg_path}")
        return 0 if available else 1

    # 烧录模式
    if not args.artifact:
        print(" 请提供 --artifact（固件产物路径）。")
        return 1

    if not args.device:
        print(" GD-Link 烧录需要 --device 参数（如 GD32F303RET6）。")
        print("   GD_Link_CLI 需要明确的设备名，无法安全推断。")
        result = FlashResult(
            status="blocked",
            summary="缺少设备名（--device）",
            artifact_path=args.artifact,
            failure_category="ambiguous-context",
        )
        print_flash_report(result)
        return 1

    # 检查 GD_Link_CLI
    gdlink = find_gdlink_cli()
    if not gdlink:
        print(" 未找到 GD_Link_CLI.exe。")
        print("   请确保已安装 GigaDevice GD-Link Programmer。")
        print("   或使用 --detect --save-config 探测并保存路径。")
        return 1

    # 验证产物
    artifact_path = str(Path(args.artifact).resolve())
    kind, size = identify_artifact(artifact_path)
    if kind is None:
        print(f" 产物不存在或类型无法识别: {artifact_path}")
        return 1
    print(f" 固件产物: {artifact_path} [{kind.upper()}, {size / 1024:.1f} KB]")

    # BIN 需要基地址
    if kind == "bin" and not args.base_address:
        print(" BIN 文件必须提供 --base-address（烧录基地址）。")
        result = FlashResult(
            status="blocked",
            summary="BIN 文件缺少烧录基地址",
            artifact_path=artifact_path,
            artifact_kind=kind,
            failure_category="artifact-missing",
        )
        print_flash_report(result)
        return 1

    # 读取 GDConfig.ini 获取默认接口和速度
    config = read_gdconfig(gdlink)
    interface = args.interface
    speed = args.speed
    if config.get("connectinterface", "").upper() in ("SWD", "JTAG"):
        interface = config["connectinterface"].upper()
    if config.get("connectspeed"):
        try:
            speed_khz = int(re.sub(r"[^0-9]", "", config["connectspeed"]))
            if speed_khz > 0:
                speed = speed_khz
        except ValueError:
            pass

    # 生成命令序列
    commands = build_gdlink_commands(
        device=args.device,
        artifact=artifact_path,
        artifact_kind=kind,
        interface=interface,
        speed=speed,
        base_address=args.base_address,
    )

    # 执行烧录
    ok, evidence = run_flash(gdlink, commands, verbose=args.verbose)

    failure_category = None
    if not ok:
        for line in evidence:
            if "connection-failure" in line:
                failure_category = "connection-failure"
                break
            if "project-config-error" in line:
                failure_category = "project-config-error"
                break
            if "target-response-abnormal" in line:
                failure_category = "target-response-abnormal"
                break
        if not failure_category:
            failure_category = "connection-failure"

    result = FlashResult(
        status="success" if ok else "failure",
        summary="烧录成功" if ok else "烧录失败",
        command=f"{gdlink} < {len(commands)} commands via stdin",
        device=args.device,
        interface=interface,
        speed=speed,
        artifact_path=artifact_path,
        artifact_kind=kind,
        verified=ok,
        failure_category=failure_category,
        evidence=evidence,
    )
    print_flash_report(result)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
