#!/usr/bin/env python3
"""GD-Link flash tool via Keil MDK5 (UV4.exe).

Supports:
- Build (UV4 -r)
- Flash via debug session (UV4 -d)
- Safe flash configuration presets (keil_flash_config)
- CMSIS-DAP / J-Link / ST-Link driver management
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILLS_DIR = _SCRIPT_DIR.parent.parent
_SHARED_DIR = _SKILLS_DIR.parent / "shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

from keil_flash_config import (
    FLASH_PRESETS,
    DRIVER_NAMES,
    read_flash_config,
    apply_flash_preset,
)

# Known Keil paths
_KEIL_CANDIDATES = [
    Path(r"D:\Program Files\ARM\MDK5\UV4\UV4.exe"),
    Path(r"C:\Keil_v5\UV4\UV4.exe"),
    Path(r"C:\Program Files\ARM\MDK5\UV4\UV4.exe"),
]


def find_keil_uv4() -> Path | None:
    """Locate UV4.exe from known paths or PATH."""
    for p in _KEIL_CANDIDATES:
        if p.exists():
            return p
    import shutil
    found = shutil.which("UV4.exe")
    return Path(found) if found else None


def build_project(uv4: Path, proj: Path, target: str) -> tuple[bool, str]:
    """Run UV4 -r (rebuild). Returns (success, build_log_text)."""
    log_path = proj.with_suffix(".build.log")

    cmd = [
        str(uv4),
        "-r", str(proj),
        "-t", target,
        "-j0",
        "-o", str(log_path),
    ]

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(proj.parent),
    )

    log_text = ""
    if log_path.exists():
        log_text = log_path.read_text(encoding="utf-8", errors="replace")

    success = (
        "0 Error(s)" in log_text
        and proc.returncode == 0
    )
    return success, log_text


def flash_project(uv4: Path, proj: Path, target: str) -> bool:
    """Flash via UV4 debug session (auto-download)."""
    print("Starting Keil uVision in debug mode...")
    print("The firmware will be downloaded automatically.")
    print("Close Keil when flashing is done.\n")

    cmd = [
        str(uv4),
        "-d", str(proj),
        "-t", target,
    ]

    proc = subprocess.Popen(
        cmd,
        cwd=str(proj.parent),
    )

    try:
        ret = proc.wait()
        return ret == 0
    except KeyboardInterrupt:
        proc.terminate()
        return False


def print_detect_report() -> None:
    """Print Keil/GD-Link environment report."""
    uv4 = find_keil_uv4()

    print("\nKeil/GD-Link Environment Report")
    print("=" * 50)

    if uv4:
        ver = get_file_version(str(uv4))
        print(f"  Keil uVision : {uv4}")
        if ver:
            print(f"  Version      : {ver}")
    else:
        print("  Keil uVision : NOT FOUND")

    print("\n  Available flash presets:")
    for name, preset in FLASH_PRESETS.items():
        driver = DRIVER_NAMES.get(preset.driver_selection, str(preset.driver_selection))
        print(f"    {name:20s} {driver:12s} {preset.description}")

    print("\n  To use this skill:")
    print("  1. Open project in Keil")
    print("  2. Flash -> Configure Flash Tools -> Debug")
    print("  3. Select the appropriate debugger (CMSIS-DAP for GD-Link)")
    print("  4. Or use --set-flash-preset to auto-configure")


def get_file_version(path: str) -> str | None:
    """Get Windows file version string."""
    import ctypes
    from ctypes import wintypes

    size = wintypes.DWORD()
    info_size = ctypes.windll.version.GetFileVersionInfoSizeW(path, ctypes.byref(size))
    if not info_size:
        return None

    buf = ctypes.create_string_buffer(info_size)
    ctypes.windll.version.GetFileVersionInfoW(path, 0, info_size, buf)

    p = ctypes.c_void_p()
    l = wintypes.UINT()
    ctypes.windll.version.VerQueryValueW(buf, r"\\StringFileInfo\\040904b0\\ProductVersion",
                                         ctypes.byref(p), ctypes.byref(l))
    if p and l.value:
        return ctypes.wstring_at(p.value)
    return None


def main():
    parser = argparse.ArgumentParser(
        description="GD-Link flasher via Keil MDK5 UV4"
    )
    parser.add_argument("--project", "-p", help="Path to .uvprojx project file")
    parser.add_argument("--target", "-t", default="GD32G553Q_EVAL", help="Build target name")
    parser.add_argument("--detect", action="store_true", help="Detect Keil / GD-Link environment")
    parser.add_argument("--build-only", action="store_true", help="Only build, skip flash")
    parser.add_argument("--flash-only", action="store_true", help="Only flash, skip build")
    parser.add_argument("--read-flash-config", action="store_true",
                        help="Read and display current flash configuration")
    parser.add_argument("--set-flash-preset", metavar="PRESET",
                        help=f"Apply flash config preset: {', '.join(FLASH_PRESETS.keys())}")
    parser.add_argument("--set-cmsis-dap", action="store_true",
                        help="[Deprecated] Use --set-flash-preset cmsis-dap instead")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what --set-flash-preset would change without writing")
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    # --detect mode
    if args.detect:
        print_detect_report()
        return 0

    # --read-flash-config (can work standalone or with --project)
    if args.read_flash_config:
        if not args.project:
            parser.error("--project is required with --read-flash-config")
            return 1
        proj = Path(args.project).resolve()
        if not proj.exists():
            print(f"ERROR: Project not found: {proj}", file=sys.stderr)
            return 1
        config = read_flash_config(proj, args.target)
        print(f"\nFlash configuration: {proj}")
        print(f"  Target:                  {args.target}")
        print(f"  Device:                  {config['device'] or 'N/A'}")
        print(f"  Output:                  {config['output_name'] or 'N/A'}")
        print(f"  Debug Probe:             {config['driver_name'] or 'N/A'} "
              f"(code={config['driver_selection']})")
        print(f"  Flash Before Debug:      {config['update_flash_before_debugging']}")
        if config["errors"]:
            for e in config["errors"]:
                print(f"  ⚠ {e}")
        return 0

    # --set-flash-preset (safe config mutation)
    if args.set_flash_preset or args.set_cmsis_dap:
        if not args.project:
            parser.error("--project is required with --set-flash-preset")
            return 1
        proj = Path(args.project).resolve()
        if not proj.exists():
            print(f"ERROR: Project not found: {proj}", file=sys.stderr)
            return 1

        preset_name = args.set_flash_preset if args.set_flash_preset else "cmsis-dap"

        result = apply_flash_preset(proj, preset_name, args.target, dry_run=args.dry_run)

        prefix = "[DRY RUN] " if args.dry_run else ""
        preset = FLASH_PRESETS.get(preset_name)
        if preset:
            print(f"\n{prefix}Flash preset: {preset_name} — {preset.description}")
        else:
            print(f"\n{prefix}Flash preset: {preset_name}")

        print(f"  Project: {proj}")
        print(f"  Status:  {result['status']}")

        if result["changes"]:
            print(f"\n  Changes:")
            for c in result["changes"]:
                print(f"    + {c}")
        else:
            print("  (no changes needed)")

        if result["errors"]:
            print(f"\n  Errors:")
            for e in result["errors"]:
                print(f"    ⚠ {e}")

        if result["status"] == "success":
            print("\n  Tip: Open project in Keil to verify debugger settings.")
            print("  Flash -> Configure Flash Tools -> Debug")

        return 0 if result["status"] in ("success", "no_change", "dry_run") else 1

    # Require --project for build/flash modes
    if not args.project:
        parser.error("--project is required (or use --detect)")
        return 1

    proj = Path(args.project).resolve()
    if not proj.exists():
        print(f"ERROR: Project not found: {proj}", file=sys.stderr)
        return 1

    uv4 = find_keil_uv4()
    if not uv4:
        print("ERROR: Keil UV4.exe not found. Install Keil MDK5.", file=sys.stderr)
        return 1

    if args.verbose:
        print(f"UV4 : {uv4}")
        print(f"Project: {proj}")
        print(f"Target : {args.target}")

    # Show current flash config
    config = read_flash_config(proj, args.target)
    print(f"Debug Probe: {config['driver_name'] or 'N/A'} "
          f"(code={config['driver_selection']})")

    # --build-only / build step
    if not args.flash_only:
        print(f"\nBuilding '{args.target}' ...")
        ok, log = build_project(uv4, proj, args.target)

        if args.verbose:
            for line in log.splitlines()[-30:]:
                print(f"  {line}")

        if not ok:
            print("\nBUILD FAILED", file=sys.stderr)
            for line in log.splitlines():
                if "Error" in line:
                    print(f"  {line}", file=sys.stderr)
            return 1

        print("Build OK")

        if args.build_only:
            return 0

    # Flash step
    ok = flash_project(uv4, proj, args.target)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
