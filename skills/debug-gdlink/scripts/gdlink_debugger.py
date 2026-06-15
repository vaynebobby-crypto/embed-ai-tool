#!/usr/bin/env python3
"""GD-Link debugger via Keil MDK5.

Launches Keil uVision debug session with optional automation:
- download-and-halt: auto-flash, stop at main
- attach-only: attach without reset
- crash-context: capture HardFault registers
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


_KEIL_CANDIDATES = [
    Path(r"D:\Program Files\ARM\MDK5\UV4\UV4.exe"),
    Path(r"C:\Keil_v5\UV4\UV4.exe"),
    Path(r"C:\Program Files\ARM\MDK5\UV4\UV4.exe"),
]

DEBUG_INI_TEMPLATE = """// Auto-generated debug init script (mode: {mode})

"""

DOWNLOAD_HALT_TEMPLATE = DEBUG_INI_TEMPLATE + (
    "// Load and halt at main\n"
    "LOAD {axf_path} INCREMENTAL\n"
    "RESET\n"
    "g, main\n"
)

ATTACH_TEMPLATE = DEBUG_INI_TEMPLATE + (
    "// Attach without reset\n"
)

CRASH_TEMPLATE = DEBUG_INI_TEMPLATE + (
    "// Load, halt, check HardFault registers\n"
    "// After loading, open: Peripherals -> Core Peripherals -> Fault Reports\n"
    "LOAD {axf_path} INCREMENTAL\n"
    "RESET\n"
)


def find_keil_uv4() -> Path | None:
    for p in _KEIL_CANDIDATES:
        if p.exists():
            return p
    import shutil
    found = shutil.which("UV4.exe")
    return Path(found) if found else None


def create_debug_ini(mode: str, axf_path: str | None, out_path: Path) -> str:
    """Generate debug init script content and write to file."""
    if mode == "download-and-halt":
        content = DOWNLOAD_HALT_TEMPLATE.format(
            mode=mode,
            axf_path=axf_path or r".\Objects\Project.axf"
        )
    elif mode == "attach-only":
        content = ATTACH_TEMPLATE.format(mode=mode)
    elif mode == "crash-context":
        content = CRASH_TEMPLATE.format(
            mode=mode,
            axf_path=axf_path or r".\Objects\Project.axf"
        )
    else:
        content = DEBUG_INI_TEMPLATE.format(mode=mode)

    out_path.write_text(content, encoding="utf-8")
    return content


def find_axf(proj_path: Path) -> Path | None:
    """Find .axf output from .uvprojx project config."""
    try:
        tree = ET.parse(str(proj_path))
        out_dir = None
        out_name = None
        for elem in tree.iter():
            if elem.tag == "OutputDirectory":
                out_dir = elem.text
            elif elem.tag == "OutputName":
                out_name = elem.text
        if out_dir and out_name:
            axf_dir = (proj_path.parent / out_dir).resolve()
            for c in [axf_dir / f"{out_name}.axf", axf_dir / f"{out_name}.AXF"]:
                if c.exists():
                    return c
    except Exception:
        pass
    # Fallback
    for ext in (".axf", ".AXF"):
        found = list(proj_path.parent.rglob(f"*{ext}"))
        if found:
            return found[0]
    return None


def main():
    parser = argparse.ArgumentParser(description="GD-Link debugger via Keil MDK5")
    parser.add_argument("--project", "-p", help="Path to .uvprojx")
    parser.add_argument("--target", "-t", default="GD32G553Q_EVAL", help="Build target")
    parser.add_argument("--mode", "-m",
                        choices=["download-and-halt", "attach-only", "crash-context"],
                        default="download-and-halt")
    parser.add_argument("--elf", help="Path to .axf/.elf (auto-detect)")
    parser.add_argument("--detect", action="store_true", help="Check environment")
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    uv4 = find_keil_uv4()
    if not uv4:
        print("ERROR: Keil UV4.exe not found", file=sys.stderr)
        return 1

    # --detect
    if args.detect:
        print("GD-Link Debug Environment (Keil)")
        print("=" * 50)
        print(f"  Keil uVision : {uv4}")
        if args.project:
            proj = Path(args.project)
            if proj.exists():
                axf = find_axf(proj)
                print(f"  Project      : {proj}")
                print(f"  Firmware     : {axf if axf else 'not found (build first)'}")
        print("\n  Modes:")
        print("    download-and-halt : Flash + halt at main()")
        print("    attach-only       : Attach to running target")
        print("    crash-context     : Halt and inspect fault registers")
        return 0

    if not args.project:
        parser.error("--project is required (or use --detect)")

    proj = Path(args.project).resolve()
    if not proj.exists():
        print(f"ERROR: Project not found: {proj}", file=sys.stderr)
        return 1

    # Find axf
    axf_path = args.elf
    if not axf_path:
        axf = find_axf(proj)
        axf_path = str(axf) if axf else None

    if args.verbose:
        print(f"UV4    : {uv4}")
        print(f"Project: {proj}")
        print(f"Target : {args.target}")
        print(f"Mode   : {args.mode}")
        if axf_path:
            print(f"AXF    : {axf_path}")

    # Write debug init script
    ini_path = proj.parent / "_gdlink_debug.ini"
    create_debug_ini(args.mode, axf_path, ini_path)

    if args.verbose:
        print(f"\nDebug init : {ini_path}")
        print("NOTE: Set this file in Keil project options:")
        print("  Debug tab -> Initialization File")
        print("  Otherwise the init script will be ignored.\n")

    print(f"Starting Keil debug session [{args.mode}] ...")
    print("Close Keil when done.\n")

    cmd = [str(uv4), "-d", str(proj), "-t", args.target]
    proc = subprocess.Popen(cmd, cwd=str(proj.parent))

    try:
        ret = proc.wait()
        return ret
    except KeyboardInterrupt:
        print("\nClosing...")
        proc.terminate()
        return 0


if __name__ == "__main__":
    sys.exit(main())
