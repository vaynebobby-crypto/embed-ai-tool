#!/usr/bin/env python3
"""GigaDevice GD-Link 烧录工具。

为 `flash-gdlink` skill 提供可重复调用的执行入口，支持：

- 探测 GD_Link_CLI.exe 环境和版本
- 读取 GDConfig.ini 获取 SWD/JTAG 和速度配置
- 通过 stdin 管道驱动 GD_Link_CLI 交互式命令行执行烧录
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


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

ARTIFACT_EXTENSIONS = {".elf": "elf", ".hex": "hex", ".bin": "bin", ".axf": "elf"}
ARTIFACT_PRIORITY = {"elf": 1, "hex": 2, "bin": 3}

GD_LINK_EXE_NAME = "GD_Link_CLI.exe"

SUCCESS_MARKERS = [
    "o.k.", "ok", "success", "verify ok", "programming completed",
]
ERROR_MARKERS = [
    "error", "fail", "timeout", "cannot", "no target", "no device",
]

# GD_Link_CLI 常见安装根路径（深度搜索限制 5）
_COMMON_INSTALL_ROOTS: list[str] = []


def _init_common_roots() -> list[str]:
    """构建常见安装根路径列表（仅 Windows）。"""
    roots: list[str] = []
    for drive in ["D:", "C:"]:
        roots.append(f"{drive}\\GD_Link_CLI")
        roots.append(f"{drive}\\GigaDevice")
        roots.append(f"{drive}\\GigaDevice\\GD_Link_CLI")
        roots.append(f"{drive}\\")  # 全盘回退扫描（depth 受限，需调大）
        for prog_key in ["ProgramFiles", "ProgramFiles(x86)"]:
            prog_dir = os.environ.get(prog_key, "")
            if not prog_dir or drive not in prog_dir:
                continue
            roots.append(str(Path(prog_dir) / "GigaDevice"))
            roots.append(str(Path(prog_dir) / "GigaDevice" / "GD_Link_CLI"))
            roots.append(str(Path(prog_dir) / "GD_Link_CLI"))
    return roots


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

def _gdlink_exe_candidates() -> list[str]:
    """按优先级返回 GD_Link_CLI.exe 候选路径列表。

    查找顺序：
    1. 配置文件 tool_config("gdlink-cli")
    2. PATH 中的 GD_Link_CLI.exe
    3. D:\\ 和 C:\\ 下常见安装路径（深度限制 5）
    """
    candidates: list[str] = []

    configured = get_tool_path("gdlink-cli")
    if configured:
        candidates.append(configured)

    candidates.append(GD_LINK_EXE_NAME)

    global _COMMON_INSTALL_ROOTS
    if not _COMMON_INSTALL_ROOTS:
        _COMMON_INSTALL_ROOTS = _init_common_roots()

    seen: set[str] = set()
    for root_str in _COMMON_INSTALL_ROOTS:
        root_path = Path(root_str)
        if not root_path.is_dir():
            continue
        try:
            for dirpath, dirnames, filenames in os.walk(root_path):
                rel_depth = len(Path(dirpath).relative_to(root_path).parts)
                if rel_depth >= 5:
                    dirnames.clear()
                    continue
                if GD_LINK_EXE_NAME in filenames:
                    found = str(Path(dirpath) / GD_LINK_EXE_NAME)
                    normalized = str(Path(found).resolve())
                    if normalized not in seen:
                        seen.add(normalized)
                        candidates.append(found)
        except (PermissionError, OSError):
            continue

    return candidates


def find_gdlink_exe() -> str | None:
    """依次检查候选路径，返回第一个可用的 GD_Link_CLI.exe 路径。"""
    seen: set[str] = set()
    for candidate in _gdlink_exe_candidates():
        normalized = str(Path(candidate).resolve()) if os.path.isabs(candidate) else candidate
        if normalized in seen:
            continue
        seen.add(normalized)
        path = shutil.which(candidate)
        if path:
            return path
        p = Path(candidate)
        if p.is_file():
            return str(p.resolve())
    return None


def check_gdlink() -> tuple[bool, str | None, str | None]:
    """启动 GD_Link_CLI 发送 q 退出，提取版本信息。

    @retval  (available, exe_path, version_string)
    """
    gdlink = find_gdlink_exe()
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
        try:
            stdout, stderr = proc.communicate(input="q\n", timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
        output = stdout + "\n" + stderr

        version = None
        for line in output.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            # 匹配版本信息行：GD-Link Programmer v4.x.x 或类似
            if re.search(r"version|v\d+\.\d+|gd.link|programmer",
                         stripped, re.IGNORECASE):
                version = stripped
                break
        if not version:
            first_line = output.strip().split("\n")[0] if output.strip() else None
            if first_line:
                version = first_line
        return True, gdlink, version
    except Exception:
        return True, gdlink, None


# ---------------------------------------------------------------------------
# GDConfig.ini 读取
# ---------------------------------------------------------------------------

def read_gdconfig(config_dir: str | Path | None = None) -> tuple[str | None, int | None]:
    """读取 GDConfig.ini，返回 (interface, speed_khz)。

    若 GDConfig.ini 缺少 [DEFAULT] section 头则自动补齐后解析。
    未找到文件或解析失败时返回 (None, None)。

    @param  config_dir: 配置文件所在目录，默认当前工作目录
    @retval (interface, speed_khz): 接口类型（SWD/JTAG）和速度（kHz 整数）
    """
    directory = Path(config_dir) if config_dir else Path.cwd()
    ini_path = directory / "GDConfig.ini"

    if not ini_path.is_file():
        return None, None

    try:
        raw = ini_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None, None

    # 未检测到 section 头时自动添加 [DEFAULT]
    if not re.match(r"^\s*\[", raw.strip()):
        raw = "[DEFAULT]\n" + raw

    config = configparser.ConfigParser()
    try:
        config.read_string(raw)
    except configparser.Error:
        return None, None

    interface: str | None = None
    speed: int | None = None

    # 遍历所有 section（包括 DEFAULT）查找 ConnectInterface / ConnectSpeed
    sections_to_check = config.sections() + ["DEFAULT"]
    for section in sections_to_check:
        if interface is None and config.has_option(section, "ConnectInterface"):
            val = config.get(section, "ConnectInterface", fallback="").strip().upper()
            if val in ("SWD", "JTAG"):
                interface = val
        if speed is None and config.has_option(section, "ConnectSpeed"):
            val = config.get(section, "ConnectSpeed", fallback="")
            match = re.search(r"(\d+)", val)
            if match:
                speed = int(match.group(1))
        if interface is not None and speed is not None:
            break

    return interface, speed


# ---------------------------------------------------------------------------
# 产物验证
# ---------------------------------------------------------------------------

def identify_artifact(artifact_path: str) -> tuple[str | None, int]:
    """按扩展名判断固件产物类型。

    @retval  (kind, size_bytes): 类型为 elf/hex/bin 或 None（无法识别）
    """
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
# 烧录命令组装与执行
# ---------------------------------------------------------------------------

def _build_command_sequence(
    artifact: str,
    artifact_kind: str,
    base_address: str | None,
) -> str:
    """构建通过 stdin 发送给 GD_Link_CLI 的命令序列。

    GD_Link_CLI 为交互式 REPL 命令行，每行一条命令：
      load <file> [<addr>]  - 加载固件
      r                     - 复位目标
      g                     - 运行目标
      q                     - 退出
    """
    lines: list[str] = []

    if artifact_kind == "bin" and base_address:
        lines.append(f"load {artifact} {base_address}")
    else:
        lines.append(f"load {artifact}")

    lines.append("r")
    lines.append("g")
    lines.append("q")
    return "\n".join(lines) + "\n"


def _classify_failure(output: str) -> str | None:
    """根据 GD_Link_CLI 输出对失败进行分类。

    - "no target" / "no device" / "connect" → connection-failure
    - "unknown" / "not supported"            → project-config-error
    - "failed"                               → target-response-abnormal
    """
    output_lower = output.lower()
    if "no target" in output_lower or "no device" in output_lower or "connect" in output_lower:
        return "connection-failure"
    if "unknown" in output_lower or "not supported" in output_lower:
        return "project-config-error"
    if "failed" in output_lower:
        return "target-response-abnormal"
    return None


def run_flash(
    gdlink: str,
    artifact: str,
    artifact_kind: str,
    base_address: str | None,
    verbose: bool,
    gdconfig_dir: str | None = None,
) -> tuple[bool, list[str]]:
    """通过 stdin 管道驱动 GD_Link_CLI 交互式命令行执行烧录。

    @param  gdlink:        GD_Link_CLI.exe 路径
    @param  artifact:      固件产物文件路径
    @param  artifact_kind: 产物类型 elf / hex / bin
    @param  base_address:  BIN 文件烧录基地址（十六进制字符串）
    @param  verbose:       是否输出详细日志
    @param  gdconfig_dir:  GDConfig.ini 所在目录（作为 GD_Link_CLI 工作目录）
    @retval (success, evidence_lines): 成功标志与证据行列表
    """
    cmd_sequence = _build_command_sequence(artifact, artifact_kind, base_address)

    cwd = str(Path(gdconfig_dir).resolve()) if gdconfig_dir else None
    cmd_display = f"echo '<commands>' | {gdlink}"
    print(f"⚡ 烧录命令: {cmd_display}")

    try:
        proc = subprocess.Popen(
            [gdlink],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
        )
        try:
            stdout, stderr = proc.communicate(input=cmd_sequence, timeout=60)
            returncode = proc.returncode
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            return False, ["❌ GD_Link_CLI 烧录超时（60 秒）"]
    except FileNotFoundError:
        return False, [f"❌ 未找到 GD_Link_CLI: {gdlink}"]
    except OSError as e:
        return False, [f"❌ 启动 GD_Link_CLI 失败: {e}"]

    combined = stdout + "\n" + stderr
    combined_lower = combined.lower()
    evidence: list[str] = []

    if verbose:
        for line in combined.strip().split("\n")[-40:]:
            if line.strip():
                evidence.append(line.strip())

    has_error = any(marker in combined_lower for marker in ERROR_MARKERS)
    has_success = any(marker in combined_lower for marker in SUCCESS_MARKERS)

    # 成功：无 error marker 且 returncode == 0
    if not has_error and returncode == 0:
        print(f"✅ 烧录{'并校验通过' if has_success else '成功'}")
        return True, evidence

    # 有 success marker 且无 error marker
    if has_success and not has_error:
        print("✅ 烧录成功")
        return True, evidence

    # 失败分析
    last_lines = combined.strip().split("\n")[-15:]
    evidence.extend(last_lines)

    failure_category = _classify_failure(combined)
    if failure_category:
        evidence.insert(0, f"failure_hint: {failure_category}")

    return False, evidence


# ---------------------------------------------------------------------------
# 报告输出
# ---------------------------------------------------------------------------

def print_detect_report(
    available: bool,
    gdlink: str | None,
    version: str | None,
    config_iface: str | None = None,
    config_speed: int | None = None,
) -> None:
    """输出 GD-Link 环境探测结果报告。"""
    print("\n📊 GD-Link 环境探测结果：")
    status = "✅" if available else "❌"
    ver = f" ({version})" if version else ""
    path = f" @ {gdlink}" if gdlink else ""
    print(f"  {status} GD_Link_CLI{ver}{path}")

    if config_iface or config_speed:
        print(f"\n  📝 GDConfig.ini 配置:")
        if config_iface:
            print(f"    接口: {config_iface}")
        if config_speed:
            print(f"    速度: {config_speed} kHz")
    elif available:
        print("\n  ⚠️ 未找到 GDConfig.ini 配置文件")


def print_flash_report(result: FlashResult) -> None:
    """输出烧录结果结构化报告。"""
    icon = {"success": "✅", "failure": "❌", "blocked": "⚠️"}.get(result.status, "❓")
    print(f"\n📊 烧录结果: {icon} {result.summary}")

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
        print("\n📝 证据:")
        for line in result.evidence[:15]:
            print(f"  {line}")

    if result.failure_category:
        print(f"\n  失败分类: {result.failure_category}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        description="GigaDevice GD-Link 烧录工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --detect
  %(prog)s --artifact build/app.elf --device GD32F303RET6
  %(prog)s --artifact build/app.hex --device GD32F303RET6 --interface JTAG
  %(prog)s --artifact build/fw.bin --device GD32F303RET6 --base-address 0x08000000
  %(prog)s --detect --save-config
        """,
    )
    parser.add_argument("--detect", action="store_true",
                        help="探测 GD-Link 环境和 GDConfig.ini")
    parser.add_argument("--artifact", help="固件产物路径")
    parser.add_argument("--device", help="目标芯片型号（如 GD32F303RET6）")
    parser.add_argument("--interface", choices=["SWD", "JTAG"], default=None,
                        help="调试接口（默认从 GDConfig.ini 读取，未配置则 SWD）")
    parser.add_argument("--speed", type=int, default=None,
                        help="连接速度 kHz（默认从 GDConfig.ini 读取，未配置则 10000）")
    parser.add_argument("--base-address", help="BIN 文件烧录基地址（十六进制）")
    parser.add_argument("--gdconfig", help="GDConfig.ini 所在目录（默认当前工作目录）")
    parser.add_argument("--save-config", action="store_true",
                        help="探测成功后保存 GD_Link_CLI 路径到配置")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="详细输出")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # ---- 探测模式 ----
    if args.detect:
        available, gdlink_path, version = check_gdlink()
        # GDConfig.ini 优先从 CLI 所在目录读取
        config_dir = args.gdconfig or (str(Path(gdlink_path).parent) if gdlink_path else None)
        config_iface, config_speed = read_gdconfig(config_dir)
        print_detect_report(available, gdlink_path, version, config_iface, config_speed)
        if args.save_config and available and gdlink_path:
            cfg_path = set_tool_path("gdlink-cli", gdlink_path)
            print(f"  💾 已保存到 {cfg_path}")
        return 0 if available else 1

    # ---- 烧录模式 ----
    if not args.artifact:
        print("❌ 请提供 --artifact（固件产物路径）。")
        return 1

    if not args.device:
        print("❌ GD-Link 烧录需要 --device 参数（如 GD32F303RET6）。")
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
    gdlink = find_gdlink_exe()
    if not gdlink:
        print("❌ 未找到 GD_Link_CLI.exe。请安装 GigaDevice GD-Link 工具链。")
        print("   搜索路径: 配置文件 → PATH → D:\\ & C:\\ 常见路径")
        return 1

    # 读取 GDConfig.ini，CLI 参数可覆盖
    config_iface, config_speed = read_gdconfig(args.gdconfig)
    interface = args.interface or config_iface or "SWD"
    speed = args.speed or config_speed or 10000

    # 验证产物
    artifact_path = str(Path(args.artifact).resolve())
    kind, size = identify_artifact(artifact_path)
    if kind is None:
        print(f"❌ 产物不存在或类型无法识别: {artifact_path}")
        return 1
    print(f"📦 固件产物: {artifact_path} [{kind.upper()}, {size / 1024:.1f} KB]")

    # BIN 需要基地址
    if kind == "bin" and not args.base_address:
        print("❌ BIN 文件必须提供 --base-address（烧录基地址）。")
        result = FlashResult(
            status="blocked",
            summary="BIN 文件缺少烧录基地址",
            artifact_path=artifact_path,
            artifact_kind=kind,
            failure_category="artifact-missing",
        )
        print_flash_report(result)
        return 1

    # 确定 GDConfig.ini 所在目录（用于 GD_Link_CLI 工作目录）
    gdconfig_dir: str | None = None
    if args.gdconfig:
        gdconfig_dir = str(Path(args.gdconfig).resolve())
    else:
        # 默认使用产物所在目录
        artifact_dir = str(Path(artifact_path).parent)
        if Path(artifact_dir, "GDConfig.ini").is_file():
            gdconfig_dir = artifact_dir

    # 执行烧录
    ok, evidence = run_flash(
        gdlink=gdlink,
        artifact=artifact_path,
        artifact_kind=kind,
        base_address=args.base_address,
        verbose=args.verbose,
        gdconfig_dir=gdconfig_dir,
    )

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
        command=f"echo '<commands>' | {gdlink}",
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
