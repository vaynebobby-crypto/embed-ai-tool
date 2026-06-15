# GD-Link Flash & Debug Skills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建 flash-gdlink 和 debug-gdlink 两个 skill，对标现有 flash-jlink / debug-jlink，为 GD-Link 探针提供烧录和调试能力。

**Architecture:** 每个 skill 包含 SKILL.md（8 个必需章节）、scripts/*.py（独立 CLI 工具）、references/usage.md（用户文档）、agents/openai.yaml（Agent SDK 元数据）。flash-gdlink 通过 stdin 管道驱动 GD_Link_CLI.exe 交互式命令行；debug-gdlink 通过 pyocd gdbserver + arm-none-eabi-gdb 实现完整源码级调试。

**Tech Stack:** Python 3, subprocess (stdin piping), pyOCD 0.44.1+, arm-none-eabi-gdb, shared/tool_config.py (路径持久化), GDConfig.ini (连接参数)

---

### Task 1: 创建 flash-gdlink 目录结构和 SKILL.md

**Files:**
- Create: `skills/flash-gdlink/SKILL.md`

- [ ] **Step 1: 创建 flash-gdlink 目录并写入 SKILL.md**

```bash
mkdir -p skills/flash-gdlink/scripts skills/flash-gdlink/references skills/flash-gdlink/agents
```

- [ ] **Step 2: 写入 SKILL.md**

```markdown
---
name: flash-gdlink
description: 当需要使用 GigaDevice GD-Link 探针烧录固件到 GD32 或其他 Cortex-M 目标板时使用。
---

# GD-Link 烧录

## 适用场景

- 工作区已有可用固件产物，且目标板连接了 GD-Link 探针。
- 需要使用 GigaDevice 官方 GD_Link_CLI 进行烧录和校验。
- 需要扫描工作区中的 `GDConfig.ini` 配置文件或 `ToolSetting.ini` 设置。

## 必要输入

- 固件产物路径，或包含 `artifact_path` 的 `Project Profile`。
- `--device` 参数指定目标芯片型号（如 `GD32F303RET6`），GD_Link_CLI 要求指定。
- 可选的接口类型（SWD 或 JTAG，默认 SWD）。
- 若产物为 BIN，还需要 `--base-address` 烧录基地址。

## 自动探测

- 按 `ELF > HEX > BIN` 选择固件产物。
- 脚本自动查找 `GD_Link_CLI.exe`，按 Project Profile 配置、常见安装路径、用户提示的顺序搜索。
- 首次找到后自动写入 Project Profile，后续无需重复搜索。
- 读取同目录下 `GDConfig.ini` 获取 SWD/JTAG 接口和连接速度参数。
- 不会猜测设备名；当 `--device` 缺失时阻塞并返回 `ambiguous-context`。

## 执行步骤

1. 先阅读 [references/usage.md](references/usage.md)，确认本次是环境探测还是执行烧录。
2. 若不确定 GD-Link 环境状态，先运行自带脚本 [scripts/gdlink_flasher.py](scripts/gdlink_flasher.py) 的 `--detect` 模式。
3. 使用 `--artifact` + `--device` 执行烧录，可选 `--interface` 和 `--speed`。
4. 对 BIN 文件，必须同时提供 `--base-address`。
5. 读取脚本输出的烧录结果报告，重点关注校验状态和失败分类。

## 失败分流

- 当 `GD_Link_CLI.exe` 不可用时，返回 `environment-missing`。
- 当无法安全解析到产物，或 `BIN` 缺少烧录基地址时，返回 `artifact-missing`。
- 当 GD-Link 无法发现目标时，返回 `connection-failure`。
- 当 `GDConfig.ini` 配置无效或设备名不被 GD-Link 识别时，返回 `project-config-error`。
- 当烧录开始但校验或复位失败时，返回 `target-response-abnormal`。
- 当 `--device` 缺失且无法从工作区推断时，返回 `ambiguous-context`。

## 平台说明

- GD_Link_CLI.exe 为 Windows 原生可执行文件，不支持 Linux/macOS。
- 自带脚本通过 subprocess stdin 管道与交互式 CLI 通信。
- 首次使用时需要探测 GD_Link_CLI.exe 路径，写入 Project Profile 后复用。

## 输出约定

- 输出 GD_Link_CLI 命令、设备名、接口类型、产物路径和校验结果。
- 在 `Project Profile` 中保留或更新 `artifact_path`、`artifact_kind`、`gdlink_device`、`gdlink_cli_path`。
- 烧录成功后推荐 `serial-monitor` 或 `debug-gdlink`。

## 交接关系

- 当下一步要看运行日志时，将成功烧录结果交给 `serial-monitor`。
- 当用户需要 GDB 调试时，将结果交给 `debug-gdlink`。
```

- [ ] **Step 3: Commit**

```bash
git add skills/flash-gdlink/SKILL.md
git commit -m "feat: add flash-gdlink SKILL.md"
```

---

### Task 2: 创建 flash-gdlink/agents/openai.yaml

**Files:**
- Create: `skills/flash-gdlink/agents/openai.yaml`

- [ ] **Step 1: 写入 openai.yaml**

```yaml
interface:
  display_name: "GD-Link 烧录"
  short_description: "通过 GigaDevice GD-Link 探针烧录固件到目标板。"
  default_prompt: "使用 flash-gdlink skill，探测 GD-Link 探针，选择合适的烧录参数，执行烧录与校验，并输出下一步建议。"
```

- [ ] **Step 2: Commit**

```bash
git add skills/flash-gdlink/agents/openai.yaml
git commit -m "feat: add flash-gdlink agents/openai.yaml"
```

---

### Task 3: 创建 flash-gdlink/references/usage.md

**Files:**
- Create: `skills/flash-gdlink/references/usage.md`

- [ ] **Step 1: 写入 usage.md**

````markdown
# GD-Link 烧录 Skill 用法

这个 skill 自带了一个可执行脚本 [scripts/gdlink_flasher.py](../scripts/gdlink_flasher.py)，适合在需要探测 GD-Link 探针、执行烧录时直接调用。

## 能力概览

- 检测 GD_Link_CLI.exe 是否可用并获取版本信息
- 列出已连接的 GD-Link 设备
- 扫描工作区中的 `GDConfig.ini` 配置文件
- 通过 stdin 管道驱动 GD_Link_CLI 交互式命令行执行烧录
- 支持 ELF/HEX/BIN 烧录
- 输出结构化的烧录结果报告

## 基础用法

```bash
# 探测 GD-Link 环境
python3 skills/flash-gdlink/scripts/gdlink_flasher.py --detect

# 烧录 ELF
python3 skills/flash-gdlink/scripts/gdlink_flasher.py \
  --artifact /path/to/firmware.elf \
  --device GD32F303RET6

# 烧录 BIN（需要指定基地址）
python3 skills/flash-gdlink/scripts/gdlink_flasher.py \
  --artifact /path/to/firmware.bin \
  --device GD32F303RET6 \
  --base-address 0x08000000

# 烧录 HEX
python3 skills/flash-gdlink/scripts/gdlink_flasher.py \
  --artifact /path/to/firmware.hex \
  --device GD32F303RET6

# 使用 JTAG 接口
python3 skills/flash-gdlink/scripts/gdlink_flasher.py \
  --artifact build/app.elf \
  --device GD32F303RET6 \
  --interface JTAG
```

## 常见模式

### 1. 环境探测

```bash
python3 skills/flash-gdlink/scripts/gdlink_flasher.py --detect
```

输出 GD_Link_CLI 版本信息。

### 2. SWD 模式烧录（默认）

```bash
python3 skills/flash-gdlink/scripts/gdlink_flasher.py \
  --artifact build/debug/app.elf \
  --device GD32F303RET6
```

### 3. BIN 烧录（需指定基地址）

```bash
python3 skills/flash-gdlink/scripts/gdlink_flasher.py \
  --artifact build/fw.bin \
  --device GD32F303RET6 \
  --base-address 0x08000000
```

## 参数说明

| 参数 | 说明 |
| --- | --- |
| `--detect` | 探测 GD-Link 环境 |
| `--artifact` | 固件产物路径（ELF、HEX 或 BIN） |
| `--device` | 目标芯片型号（如 GD32F303RET6） |
| `--interface` | 调试接口：`SWD`（默认）或 `JTAG` |
| `--speed` | 连接速度 kHz（默认 10000） |
| `--base-address` | BIN 文件的烧录基地址（十六进制） |
| `--save-config` | 探测成功后保存 GD_Link_CLI 路径到配置 |
| `-v`, `--verbose` | 输出详细日志 |

## GD_Link_CLI.exe 查找顺序

1. 配置文件（`get_tool_path("gdlink-cli")`）
2. `GD_Link_CLI.exe`（PATH 中）
3. 常见安装路径：用户指定的已知路径
4. 提示用户手动输入路径

## GD-Link 与 J-Link 对比

| 特性 | GD-Link (本 skill) | J-Link (flash-jlink) |
|------|-------------------|----------------------|
| 目标芯片 | GD32 全系列，兼容 Cortex-M | 广泛（需许可） |
| RTT 日志 | ❌ 不支持 | ✅ 原生支持 |
| 烧录方式 | GD_Link_CLI 交互式命令行 | J-Link Commander 脚本 |
| 商业许可 | 免费 | 需要（教育版免费） |
| 跨平台 | 仅 Windows | 跨平台 |

## 返回码

- `0`：操作成功
- `1`：参数非法、依赖缺失、探针连接失败、烧录失败
````

- [ ] **Step 2: Commit**

```bash
git add skills/flash-gdlink/references/usage.md
git commit -m "feat: add flash-gdlink usage documentation"
```

---

### Task 4: 创建 flash-gdlink/scripts/gdlink_flasher.py

**Files:**
- Create: `skills/flash-gdlink/scripts/gdlink_flasher.py`

GD_Link_CLI.exe 是交互式 REPL 工具，需要通过 stdin 发送命令。与 J-Link 的脚本文件方式不同，GD_Link_CLI 的交互流程为：启动 → 自动连接 MCU → 等待用户输入命令。脚本通过 subprocess.Popen + stdin.write 驱动。

- [ ] **Step 1: 写入 gdlink_flasher.py 完整实现**

```python
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
import io
import os
import platform
import re
import shutil
import subprocess
import sys
import time
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
        # 常见安装路径
        for drive in ["D:\\", "C:\\"]:
            try:
                for root, dirs, _files in os.walk(drive):
                    # 限制搜索深度
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
        # GD_Link_CLI 在无参数时输出 "Press any key to continue" 后退出
        # 运行后马上发送 q 退出，从中提取版本信息
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
        # GDConfig.ini 可能无 section 头，手动添加
        content = ini_path.read_text(encoding="utf-8", errors="ignore")
        if not content.strip().startswith("["):
            content = "[DEFAULT]\n" + content
        parser.read_string(content)

        for section in parser.sections():
            for key, value in parser.items(section):
                config[key.lower()] = value
        # 也读 DEFAULT section
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
        # BIN 文件：load <path> <base_addr>
        commands.append(f"load {artifact_posix} {base_address}")
    else:
        # ELF/HEX：GD_Link_CLI 可以自动处理
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

    # 发送所有命令
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

    # 判断成功：输出中包含成功标记
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

    # 失败分析
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
            if key != "connectinterface" and key != "connectspeed":
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
```

- [ ] **Step 2: 用 Python 检查语法**

```bash
python -m py_compile skills/flash-gdlink/scripts/gdlink_flasher.py
```
Expected: 无错误输出

- [ ] **Step 3: Commit**

```bash
git add skills/flash-gdlink/scripts/gdlink_flasher.py
git commit -m "feat: add gdlink_flasher.py with GD_Link_CLI stdin piping"
```

---

### Task 5: 创建 debug-gdlink 目录结构和 SKILL.md

**Files:**
- Create: `skills/debug-gdlink/SKILL.md`

- [ ] **Step 1: 创建 debug-gdlink 目录并写入 SKILL.md**

```bash
mkdir -p skills/debug-gdlink/scripts skills/debug-gdlink/references skills/debug-gdlink/agents
```

- [ ] **Step 2: 写入 SKILL.md**

```markdown
---
name: debug-gdlink
description: 当需要通过 GD-Link 探针（pyOCD GDB Server）启动或附着 GDB 会话，完成固件下载、在线调试或崩溃现场检查时使用。
---

# GD-Link GDB 调试

## 适用场景

- 用户希望通过 GD-Link 探针调试 Cortex-M 类目标（GD32 及兼容 MCU）。
- 工作区中已有 `ELF` 和 GD-Link 探针。
- 烧录或串口监视流程表明，需要进一步查看断点、停核控制、寄存器或回溯信息。
- 需要在调试前确认 pyOCD GDB Server 和 arm-none-eabi-gdb 环境是否就绪。

## 必要输入

- 一份带符号的 `ELF`，或包含 `artifact_path` 的 `Project Profile`。
- `--device` 可选参数指定目标芯片型号（GD32 系列，pyOCD 可自动探测）。
- 可选调试模式：`download-and-halt`、`attach-only`、`crash-context`。
- 可选的 GDB 可执行文件路径。

## 自动探测

- 默认模式为 `download-and-halt`；只有用户显式要求附着调试或崩溃现场检查时才切换。
- GDB 由脚本自动探测，优先级为：显式用户输入、`Project Profile`、`arm-none-eabi-gdb`、`gdb-multiarch`。
- pyOCD 自动扫描 CMSIS-DAP 探针（GD-Link 即 CMSIS-DAP 设备），无需额外配置。
- 目标 MCU 可通过 pyOCD 自动探测；`--device` 缺失时不会阻塞。
- 做符号级调试必须有 `ELF`。若只有 `HEX` 或 `BIN`，应阻塞并要求提供匹配 `ELF`。

## 执行步骤

1. 先阅读 [references/usage.md](references/usage.md)，确认本次是环境探测，还是执行调试会话。
2. 若不确定环境是否就绪，先运行自带脚本 [scripts/gdlink_debugger.py](scripts/gdlink_debugger.py) 的 `--detect` 模式确认。
3. 根据用户意图选择调试模式：`download-and-halt`（默认）、`attach-only` 或 `crash-context`。
4. 使用 `--elf` 启动调试，可选 `--device` 和 `--port`。
5. 脚本自动启动 pyOCD GDB Server，等待就绪后执行 GDB 批处理。
6. 读取脚本输出的调试结果，重点关注寄存器状态、回溯帧和 Fault 寄存器。

## 失败分流

- 当缺少 pyOCD 或兼容 GDB 时，返回 `environment-missing`。
- 当没有可用的 `ELF` 时，返回 `artifact-missing`。
- 当 pyOCD GDB Server 无法连接目标板时，返回 `connection-failure`。
- 当设备名不被 pyOCD 识别或配置不一致时，返回 `project-config-error`。
- 当会话可以建立，但无法停核、加载或得到可信回溯时，返回 `target-response-abnormal`。
- 当存在多个探针且无法确定目标时，返回 `ambiguous-context`。

## 平台说明

- 已确认 Python 3 + pyOCD 0.44.1 + arm-none-eabi-gdb 环境。
- 默认 GDB 端口为 3333（pyOCD 默认），可通过 `--port` 修改。
- GD-Link 作为 CMSIS-DAP 探针被 pyOCD 自动识别。
- 不带 SWO 功能（GD-Link 不支持）。

## 输出约定

- 输出调试模式、pyOCD gdbserver 命令、GDB 可执行文件、`ELF` 路径和关键观察结论。
- 在 `Project Profile` 中保留 `artifact_path`、`artifact_kind`、`gdb_executable`、`gdlink_device`。
- 当复位后或继续运行后下一步是观察运行行为时，推荐 `serial-monitor`。

## 交接关系

- 当目标恢复运行后，需要继续观察运行期日志时，将成功会话交给 `serial-monitor`。
- 当用户需要 RTOS 线程感知调试时，将会话交给 `rtos-debug`。
```

- [ ] **Step 3: Commit**

```bash
git add skills/debug-gdlink/SKILL.md
git commit -m "feat: add debug-gdlink SKILL.md"
```

---

### Task 6: 创建 debug-gdlink/agents/openai.yaml

**Files:**
- Create: `skills/debug-gdlink/agents/openai.yaml`

- [ ] **Step 1: 写入 openai.yaml**

```yaml
interface:
  display_name: "GD-Link GDB 调试"
  short_description: "通过 GD-Link 探针（pyOCD GDB Server）进行固件在线调试、崩溃分析。"
  default_prompt: "使用 debug-gdlink skill，探测 GD-Link 调试环境，启动 GDB 会话，收集寄存器和回溯信息，并输出诊断结论。"
```

- [ ] **Step 2: Commit**

```bash
git add skills/debug-gdlink/agents/openai.yaml
git commit -m "feat: add debug-gdlink agents/openai.yaml"
```

---

### Task 7: 创建 debug-gdlink/references/usage.md

**Files:**
- Create: `skills/debug-gdlink/references/usage.md`

- [ ] **Step 1: 写入 usage.md**

````markdown
# GD-Link GDB 调试 Skill 用法

这个 skill 自带了一个可执行脚本 [scripts/gdlink_debugger.py](../scripts/gdlink_debugger.py)，适合在需要通过 GD-Link 探针进行 GDB 调试时直接调用。

## 能力概览

- 检测 pyOCD GDB Server 和 arm-none-eabi-gdb 是否可用
- 启动 pyOCD GDB Server 后台进程
- 三种调试模式：下载并停核、仅附着、崩溃现场检查
- 输出结构化的调试结果报告

## 基础用法

```bash
# 探测调试环境
python3 skills/debug-gdlink/scripts/gdlink_debugger.py --detect

# 下载并停核调试（默认模式）
python3 skills/debug-gdlink/scripts/gdlink_debugger.py \
  --elf build/app.elf --device GD32F303RET6

# 附着调试
python3 skills/debug-gdlink/scripts/gdlink_debugger.py \
  --elf build/app.elf --device GD32F303RET6 --mode attach-only

# 崩溃现场排查
python3 skills/debug-gdlink/scripts/gdlink_debugger.py \
  --elf build/app.elf --device GD32F303RET6 --mode crash-context
```

## 调试模式说明

### download-and-halt（默认）

将 ELF 下载到目标，复位后停在入口。适合常规开发调试。

### attach-only

不复位、不下载，直接附着到当前运行状态。适合观察运行中的程序。

### crash-context

停核后读取寄存器、回溯和 Cortex-M Fault 寄存器（CFSR/HFSR/MMFAR/BFAR）。适合 HardFault 排查。

## 参数说明

| 参数 | 说明 |
| --- | --- |
| `--detect` | 探测调试环境（pyOCD + GDB） |
| `--elf` | 带符号的 ELF 文件路径 |
| `--device` | 目标芯片型号（如 GD32F303RET6），可选，pyOCD 可自动探测 |
| `--mode` | 调试模式：`download-and-halt`、`attach-only`、`crash-context` |
| `--gdb` | GDB 可执行文件路径 |
| `--interface` | 调试接口：`SWD`（默认）或 `JTAG` |
| `--speed` | 通信速度 kHz（默认 10000） |
| `--port` | GDB 服务端口（默认 3333，pyOCD 标准） |
| `--save-config` | 探测成功后保存工具路径到配置 |
| `-v`, `--verbose` | 输出详细日志 |

## 与 debug-jlink 的区别

| 特性 | debug-gdlink | debug-jlink |
|------|-------------|-------------|
| GDB Server | pyOCD gdbserver | JLinkGDBServer |
| 默认端口 | 3333 | 2331 |
| 需要设备名 | 否（自动探测） | 是（`--device`） |
| SWO 支持 |  不支持 |  原生 |
| 探针识别 | CMSIS-DAP 自动 | SEGGER 专用 |
| 配置复杂度 | 低（即插即用） | 低（仅需设备名） |

## 返回码

- `0`：调试会话成功完成
- `1`：参数非法、依赖缺失、连接失败、调试失败
````

- [ ] **Step 2: Commit**

```bash
git add skills/debug-gdlink/references/usage.md
git commit -m "feat: add debug-gdlink usage documentation"
```

---

### Task 8: 创建 debug-gdlink/scripts/gdlink_debugger.py

**Files:**
- Create: `skills/debug-gdlink/scripts/gdlink_debugger.py`

使用 pyOCD gdbserver + arm-none-eabi-gdb。pyOCD 自动识别 CMSIS-DAP 探针（GD-Link）。结构与 jlink_debugger.py 对齐，但使用 pyocd gdbserver CLI 替代 JLinkGDBServer。

- [ ] **Step 1: 写入 gdlink_debugger.py 完整实现**

```python
#!/usr/bin/env python3
"""GD-Link (pyOCD) GDB 调试工具。

为 `debug-gdlink` skill 提供可重复调用的执行入口，支持：

- 探测 pyOCD GDB Server 和 GDB 环境
- 启动 pyOCD GDB Server 后台进程
- 三种调试模式：download-and-halt、attach-only、crash-context
- 输出结构化的调试结果报告
"""

from __future__ import annotations

import argparse
import shutil
import socket
import subprocess
import sys
import tempfile
import time
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
from tool_config import get_tool_path, set_tool_path

GDB_CANDIDATES = ["arm-none-eabi-gdb", "gdb-multiarch"]
DEBUG_MODES = ["download-and-halt", "attach-only", "crash-context"]
DEFAULT_GDB_PORT = 3333  # pyOCD 默认端口


@dataclass
class DebugResult:
    status: str  # success, failure, blocked
    summary: str
    mode: str | None = None
    gdbserver_cmd: str | None = None
    gdb_cmd: str | None = None
    gdb_executable: str | None = None
    elf_path: str | None = None
    observations: list[str] = field(default_factory=list)
    failure_category: str | None = None
    evidence: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 工具探测
# ---------------------------------------------------------------------------

def find_pyocd_gdbserver() -> str | None:
    """查找 pyocd gdbserver，优先级: 配置 -> PATH"""
    configured = get_tool_path("pyocd-gdbserver")
    if configured:
        return configured

    # pyocd gdbserver 作为 Python 模块启动
    # 检查 "pyocd" 是否在 PATH 中
    path = shutil.which("pyocd")
    if path:
        return "pyocd"

    # 尝试通过 python -m pyocd 检查
    path = shutil.which("python")
    if path:
        try:
            r = subprocess.run(
                [path, "-m", "pyocd", "gdbserver", "--help"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0:
                return "python"
        except Exception:
            pass

    return None


def find_gdb(explicit: str | None) -> tuple[str | None, str | None]:
    if explicit:
        path = shutil.which(explicit) or explicit
        try:
            r = subprocess.run(
                [path, "--version"], capture_output=True, text=True, timeout=5,
            )
            ver = (r.stdout or r.stderr).strip().split("\n")[0]
        except Exception:
            ver = None
        return path, ver

    configured = get_tool_path("arm-none-eabi-gdb")
    if configured:
        configured_path = shutil.which(configured) or configured
        if Path(configured_path).exists():
            try:
                r = subprocess.run(
                    [configured_path, "--version"], capture_output=True, text=True, timeout=5,
                )
                ver = (r.stdout or r.stderr).strip().split("\n")[0]
            except Exception:
                ver = None
            return configured_path, ver

    for candidate in GDB_CANDIDATES:
        path = shutil.which(candidate)
        if path:
            try:
                r = subprocess.run(
                    [path, "--version"], capture_output=True, text=True, timeout=5,
                )
                ver = (r.stdout or r.stderr).strip().split("\n")[0]
            except Exception:
                ver = None
            return path, ver
    return None, None


def detect_environment(explicit_gdb: str | None) -> dict[str, Any]:
    pyocd = find_pyocd_gdbserver()
    gdb_path, gdb_ver = find_gdb(explicit_gdb)
    return {
        "pyocd_gdbserver": {"available": pyocd is not None, "path": pyocd},
        "gdb": {"available": gdb_path is not None, "path": gdb_path, "version": gdb_ver},
    }


# ---------------------------------------------------------------------------
# pyOCD GDB Server 管理
# ---------------------------------------------------------------------------

def wait_for_port(port: int, timeout: float = 10) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("localhost", port), timeout=1):
                return True
        except (ConnectionRefusedError, OSError):
            time.sleep(0.2)
    return False


def start_gdbserver(
    pyocd: str,
    device: str | None,
    speed: int,
    port: int,
) -> tuple[subprocess.Popen | None, str]:
    """启动 pyOCD GDB Server 后台进程。

    pyOCD 通过 pyocd gdbserver 子命令启动。若 pyocd 为 'python' 则通过
    python -m pyocd gdbserver 启动；若为 'pyocd' 则直接调用。
    """
    if pyocd == "python":
        cmd = ["python", "-m", "pyocd", "gdbserver"]
    else:
        cmd = [pyocd, "gdbserver"]

    cmd.extend(["-p", str(port)])
    cmd.extend(["-f", str(speed)])

    if device:
        cmd.extend(["-t", device])

    cmd_str = " ".join(cmd)
    print(f" 启动 pyOCD GDB Server: {cmd_str}")

    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    except FileNotFoundError:
        print(f" 未找到 pyOCD: {pyocd}")
        return None, cmd_str

    if wait_for_port(port):
        print(f" pyOCD GDB Server 已就绪，GDB 端口: {port}")
        return proc, cmd_str

    ret = proc.poll()
    if ret is not None:
        stderr = proc.stderr.read().decode(errors="ignore") if proc.stderr else ""
        print(f" pyOCD GDB Server 启动失败 (exit {ret})")
        if stderr.strip():
            for line in stderr.strip().split("\n")[-10:]:
                print(f"  {line}")
    else:
        print(" pyOCD GDB Server 启动超时，GDB 端口未就绪")
        proc.terminate()

    return None, cmd_str


# ---------------------------------------------------------------------------
# GDB 脚本生成与执行
# ---------------------------------------------------------------------------

def generate_gdb_script(mode: str, elf_path: str, gdb_port: int) -> str:
    elf_posix = elf_path.replace("\\", "/")
    lines: list[str] = [
        f"file {elf_posix}",
        f"target extended-remote localhost:{gdb_port}",
    ]

    if mode == "download-and-halt":
        lines.extend([
            "monitor reset halt",
            "load",
            "monitor reset halt",
            "info registers",
            "backtrace",
            "quit",
        ])
    elif mode == "attach-only":
        lines.extend([
            "info registers",
            "backtrace",
            "info threads",
            "quit",
        ])
    elif mode == "crash-context":
        lines.extend([
            "monitor halt",
            "info registers",
            "backtrace full",
            "info threads",
            "print/x *((uint32_t*)0xE000ED28)",  # CFSR
            "print/x *((uint32_t*)0xE000ED2C)",  # HFSR
            "print/x *((uint32_t*)0xE000ED34)",  # MMFAR
            "print/x *((uint32_t*)0xE000ED38)",  # BFAR
            "quit",
        ])

    return "\n".join(lines) + "\n"


def run_gdb(
    gdb_path: str,
    script_content: str,
    verbose: bool,
) -> tuple[bool, list[str], list[str]]:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".gdb", delete=False, encoding="utf-8",
    ) as f:
        f.write(script_content)
        script_path = f.name

    cmd = [gdb_path, "--batch", "-x", script_path]
    cmd_str = " ".join(cmd)
    print(f" GDB 命令: {cmd_str}")

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        return False, [" GDB 执行超时（30 秒）"], []
    except FileNotFoundError:
        return False, [f" 未找到 GDB: {gdb_path}"], []
    finally:
        Path(script_path).unlink(missing_ok=True)

    output = (result.stdout or "").strip()
    evidence: list[str] = []
    observations: list[str] = []

    if verbose and output:
        evidence.extend(output.split("\n")[-30:])

    for line in output.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if any(reg in stripped.lower() for reg in ["sp ", "pc ", "lr ", "r0 ", "xpsr"]):
            observations.append(stripped)
        elif stripped.startswith("#"):
            observations.append(stripped)
        elif "$" in stripped and "0x" in stripped:
            observations.append(stripped)

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        if stderr:
            evidence.extend(stderr.split("\n")[-10:])
        return False, evidence, observations

    print(" GDB 会话完成")
    return True, evidence, observations


# ---------------------------------------------------------------------------
# 报告输出
# ---------------------------------------------------------------------------

def print_detect_report(env: dict[str, Any]) -> None:
    print("\n GD-Link 调试环境探测结果：")
    pyocd = env["pyocd_gdbserver"]
    status = " " if pyocd["available"] else " "
    path = f" @ {pyocd['path']}" if pyocd.get("path") else ""
    print(f"  {status} pyOCD GDB Server{path}")

    gdb = env["gdb"]
    status = " " if gdb["available"] else " "
    ver = f" ({gdb['version']})" if gdb.get("version") else ""
    path = f" @ {gdb['path']}" if gdb.get("path") else ""
    print(f"  {status} GDB{ver}{path}")


def print_debug_report(result: DebugResult) -> None:
    icon = {"success": " ", "failure": " ", "blocked": " "}.get(result.status, " ")
    print(f"\n 调试结果: {icon} {result.summary}")

    if result.mode:
        print(f"\n  调试模式:       {result.mode}")
    if result.gdbserver_cmd:
        print(f"  pyOCD Server:   {result.gdbserver_cmd}")
    if result.gdb_executable:
        print(f"  GDB:            {result.gdb_executable}")
    if result.elf_path:
        print(f"  ELF:            {result.elf_path}")

    if result.observations:
        print(f"\n 关键观察（共 {len(result.observations)} 条）:")
        for obs in result.observations[:20]:
            print(f"  {obs}")

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
        description="GD-Link (pyOCD) GDB 调试工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --detect
  %(prog)s --elf build/app.elf --device GD32F303RET6
  %(prog)s --elf build/app.elf --device GD32F303RET6 --mode attach-only
  %(prog)s --elf build/app.elf --device GD32F303RET6 --mode crash-context
        """,
    )
    parser.add_argument("--detect", action="store_true", help="探测调试环境（pyOCD + GDB）")
    parser.add_argument("--elf", help="带符号的 ELF 文件路径")
    parser.add_argument("--device", help="目标芯片型号（如 GD32F303RET6），可选，pyOCD 可自动探测")
    parser.add_argument(
        "--mode", choices=DEBUG_MODES, default="download-and-halt",
        help="调试模式（默认 download-and-halt）",
    )
    parser.add_argument("--gdb", help="GDB 可执行文件路径")
    parser.add_argument("--interface", choices=["SWD", "JTAG"], default="SWD", help="调试接口（默认 SWD）")
    parser.add_argument("--speed", type=int, default=10000, help="通信速度 kHz（默认 10000）")
    parser.add_argument("--port", type=int, default=DEFAULT_GDB_PORT, help="GDB 服务端口（默认 3333）")
    parser.add_argument("--save-config", action="store_true", help="探测成功后保存工具路径到配置")
    parser.add_argument("-v", "--verbose", action="store_true", help="详细输出")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # 探测模式
    if args.detect:
        env = detect_environment(args.gdb)
        print_detect_report(env)
        if args.save_config:
            if env["pyocd_gdbserver"]["available"]:
                cfg_path = set_tool_path("pyocd-gdbserver", env["pyocd_gdbserver"]["path"])
                print(f"   pyOCD 已保存到 {cfg_path}")
            if env["gdb"]["available"]:
                cfg_path = set_tool_path("arm-none-eabi-gdb", env["gdb"]["path"])
                print(f"   GDB 已保存到 {cfg_path}")
        ok = env["pyocd_gdbserver"]["available"] and env["gdb"]["available"]
        return 0 if ok else 1

    # 调试模式
    if not args.elf:
        print(" 请提供 --elf（带符号的 ELF 文件路径）。")
        return 1

    elf_path = str(Path(args.elf).resolve())
    if not Path(elf_path).exists():
        print(f" ELF 文件不存在: {elf_path}")
        return 1
    print(f" ELF: {elf_path}")

    # 检查 pyOCD GDB Server
    pyocd = find_pyocd_gdbserver()
    if not pyocd:
        print(" 未找到 pyOCD。")
        print("   安装: pip install pyocd")
        return 1

    # 检查 GDB
    gdb_path, _ = find_gdb(args.gdb)
    if not gdb_path:
        print(" 未找到兼容的 GDB（需要 arm-none-eabi-gdb 或 gdb-multiarch）。")
        return 1
    print(f" 使用 GDB: {gdb_path}")

    # 启动 pyOCD GDB Server
    proc, gdbserver_cmd = start_gdbserver(
        pyocd, args.device, args.speed, args.port,
    )
    if proc is None:
        result = DebugResult(
            status="failure",
            summary="pyOCD GDB Server 启动失败",
            mode=args.mode,
            gdbserver_cmd=gdbserver_cmd,
            gdb_executable=gdb_path,
            elf_path=elf_path,
            failure_category="connection-failure",
        )
        print_debug_report(result)
        return 1

    # 执行 GDB
    try:
        script = generate_gdb_script(args.mode, elf_path, args.port)
        ok, evidence, observations = run_gdb(gdb_path, script, args.verbose)

        failure_category = None
        if not ok:
            for line in evidence:
                ll = line.lower()
                if "connection refused" in ll or "remote communication error" in ll:
                    failure_category = "connection-failure"
                    break
                if "no symbol" in ll or "not in executable" in ll:
                    failure_category = "project-config-error"
                    break
            if not failure_category:
                failure_category = "target-response-abnormal"

        result = DebugResult(
            status="success" if ok else "failure",
            summary=f"{args.mode} 会话{'完成' if ok else '失败'}",
            mode=args.mode,
            gdbserver_cmd=gdbserver_cmd,
            gdb_cmd=f"{gdb_path} --batch -x <script>",
            gdb_executable=gdb_path,
            elf_path=elf_path,
            observations=observations,
            failure_category=failure_category,
            evidence=evidence,
        )
        print_debug_report(result)
        return 0 if ok else 1

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        print(" pyOCD GDB Server 已关闭")


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 用 Python 检查语法**

```bash
python -m py_compile skills/debug-gdlink/scripts/gdlink_debugger.py
```
Expected: 无错误输出

- [ ] **Step 3: Commit**

```bash
git add skills/debug-gdlink/scripts/gdlink_debugger.py
git commit -m "feat: add gdlink_debugger.py with pyOCD GDB Server support"
```

---

### Task 9: 最终验证 — 编译检查和结构完整性

**Files:**
- Verify: `skills/flash-gdlink/` 所有文件
- Verify: `skills/debug-gdlink/` 所有文件

- [ ] **Step 1: 验证目录结构**

```bash
ls -la skills/flash-gdlink/ skills/flash-gdlink/scripts/ skills/flash-gdlink/references/ skills/flash-gdlink/agents/
ls -la skills/debug-gdlink/ skills/debug-gdlink/scripts/ skills/debug-gdlink/references/ skills/debug-gdlink/agents/
```
Expected: 每个目录各含一个文件

- [ ] **Step 2: Python 语法检查**

```bash
python -m py_compile skills/flash-gdlink/scripts/gdlink_flasher.py
python -m py_compile skills/debug-gdlink/scripts/gdlink_debugger.py
```
Expected: 无错误输出，exit code 0

- [ ] **Step 3: YAML 格式检查**

```bash
python -c "import yaml; yaml.safe_load(open('skills/flash-gdlink/agents/openai.yaml')); print('OK: flash-gdlink')"
python -c "import yaml; yaml.safe_load(open('skills/debug-gdlink/agents/openai.yaml')); print('OK: debug-gdlink')"
```
Expected: `OK: flash-gdlink` 和 `OK: debug-gdlink`

- [ ] **Step 4: SKILL.md frontmatter 检查**

```bash
python -c "
import yaml
for name in ['flash-gdlink', 'debug-gdlink']:
    content = open(f'skills/{name}/SKILL.md').read()
    parts = content.split('---')
    fm = yaml.safe_load(parts[1])
    assert fm['name'] == name, f'{name}: name mismatch {fm[\"name\"]}'
    assert 'description' in fm, f'{name}: missing description'
    print(f'{name}: SKILL.md OK')
"
```
Expected: 两个 skill 的 SKILL.md frontmatter 验证通过

- [ ] **Step 5: 运行 --detect 模式测试**

```bash
python skills/flash-gdlink/scripts/gdlink_flasher.py --detect
```
Expected: 输出 GD-Link 环境探测结果

```bash
python skills/debug-gdlink/scripts/gdlink_debugger.py --detect
```
Expected: 输出 pyOCD + GDB 环境探测结果

- [ ] **Step 6: 最终 commit**

```bash
git add -A
git commit -m "feat: add flash-gdlink and debug-gdlink skills with GD-Link support"
```
