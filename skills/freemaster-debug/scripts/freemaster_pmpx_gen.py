#!/usr/bin/env python3
""".pmpx 项目文件生成器。

为 `freemaster-debug` skill 提供 .pmpx 生成能力：

- 基于参考模板 XML，正则替换 ELF 文件路径
- 可选注入变量定义
- 目标已存在时自动备份为 .bak

.pmpx 格式说明：
  - 纯 XML 文本（非 ZIP），根元素 <xmlarchive>
  - ELF 路径存储在 CPrjDoc_MapFileInfo.file_name 成员中
  - 通信配置（BDM/J-Link/SWD）由 FreeMASTER 独立管理，不在 .pmpx 内
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path
from typing import Any

# stdout/stderr UTF-8 reconfigure (matching project convention)
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
_REFERENCES_DIR = _SCRIPT_DIR.parent / "references"
_DEFAULT_TEMPLATE = _REFERENCES_DIR / "_ref_freemaster_template.pmpx"

# .pmpx 中 ELF 文件路径的唯一定位正则
# 格式: <member name="file_name" type="string">C:\path\to\file.axf</member>
_FILE_NAME_RE = re.compile(
    r'(<member name="file_name" type="string">)[^<]*(</member>)'
)


def generate_pmpx(
    output_path: Path,
    elf_path: str,
    device: str,
    template_path: Path | None = None,
    variables: list[str] | None = None,
    sample_rate_hz: int = 1000,
    jlink_speed_khz: int = 4000,
) -> dict[str, Any]:
    """生成 .pmpx 项目文件.

    Args:
        output_path: 输出 .pmpx 文件路径
        elf_path: 带符号的 ELF/AXF 文件绝对路径
        device: J-Link 目标设备名（当前版本仅用于输出命名，通信配置由 FreeMASTER 管理）
        template_path: 参考模板路径
        variables: 预置变量名列表（当前版本不支持 XML 注入，仅计数）
        sample_rate_hz: Recorder 采样率（当前版本由 FreeMASTER 管理）
        jlink_speed_khz: J-Link SWD 速度（当前版本由 FreeMASTER 管理）

    Returns:
        {"status": ..., "path": ..., "vars_count": ..., "error": ...}
    """
    ref = template_path or _DEFAULT_TEMPLATE
    if not ref.is_file():
        return {
            "status": "failure",
            "path": "",
            "vars_count": 0,
            "error": f"参考模板不存在: {ref}",
        }

    # 读取模板（纯 XML 文本）
    try:
        content = ref.read_text(encoding="utf-8")
    except Exception as e:
        return {
            "status": "failure",
            "path": "",
            "vars_count": 0,
            "error": f"无法读取模板 {ref}: {e}",
        }

    # 替换 ELF 文件路径（使用 lambda 避免路径中反斜杠被 re 转义）
    subs = 0

    def _replace_file_name(m: re.Match) -> str:
        nonlocal subs
        subs += 1
        return m.group(1) + elf_path + m.group(2)

    new_content = _FILE_NAME_RE.sub(_replace_file_name, content)
    if subs == 0:
        return {
            "status": "failure",
            "path": "",
            "vars_count": 0,
            "error": "模板中未找到 file_name 成员，请确认模板是 FreeMASTER 3.x 导出的 .pmpx",
        }

    # 备份已存在的输出
    if output_path.exists():
        backup = output_path.with_suffix(".pmpx.bak")
        shutil.copy2(output_path, backup)

    # 写入
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(new_content, encoding="utf-8")

    vars_count = len(variables) if variables else 0
    return {
        "status": "success",
        "path": str(output_path.resolve()),
        "vars_count": vars_count,
        "error": None,
    }


def print_result(result: dict[str, Any]) -> None:
    """打印生成结果."""
    if result["status"] == "success":
        print(f"✅ .pmpx 已生成: {result['path']}")
        print(f"   ELF 引用已替换")
        if result["vars_count"] > 0:
            print(f"   预置变量: {result['vars_count']} 个")
        else:
            print("   提示: 未指定变量，请在 FreeMASTER GUI 中手动添加")
        print("   提示: 通信配置（J-Link/SWD/设备）请在 FreeMASTER GUI 中设置")
    else:
        print(f"❌ 生成失败: {result['error']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=".pmpx 项目文件生成器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --elf build/app.axf --device GD32F450IK --output project.pmpx
  %(prog)s --elf build/app.axf --device GD32F450IK --vars adc_value,pid_output
  %(prog)s --elf build/app.elf --device STM32F407VG --template my_template.pmpx
        """,
    )
    parser.add_argument("--elf", required=True, help="带符号的 ELF/AXF 文件路径")
    parser.add_argument("--device", required=True, help="J-Link 目标设备名（如 GD32F450IK）")
    parser.add_argument("--output", default=None, help="输出 .pmpx 路径（默认 <device>.pmpx）")
    parser.add_argument("--vars", default="", help="预置变量名，逗号分隔（预留）")
    parser.add_argument("--sample-rate", type=int, default=1000, help="Recorder 采样率 Hz（默认 1000，预留）")
    parser.add_argument("--jlink-speed", type=int, default=4000, help="J-Link SWD 速度 kHz（默认 4000，预留）")
    parser.add_argument("--template", default=None, help="参考模板路径（默认 references/_ref_freemaster_template.pmpx）")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    elf_path = str(Path(args.elf).resolve())
    if not Path(elf_path).exists():
        print(f"❌ ELF 文件不存在: {elf_path}")
        return 1

    output = Path(args.output) if args.output else Path.cwd() / f"{args.device}.pmpx"
    template = Path(args.template) if args.template else None

    variables = [v.strip() for v in args.vars.split(",") if v.strip()] if args.vars else []

    result = generate_pmpx(
        output_path=output,
        elf_path=elf_path,
        device=args.device,
        template_path=template,
        variables=variables,
        sample_rate_hz=args.sample_rate,
        jlink_speed_khz=args.jlink_speed,
    )

    print_result(result)
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
