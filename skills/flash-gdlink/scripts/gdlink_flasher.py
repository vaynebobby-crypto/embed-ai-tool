#!/usr/bin/env python3
"""GD-Link flasher via Keil MDK5 (UV4.exe).

Supports:
- Build-only mode (UV4 -r)
- Flash mode (UV4 debug with auto-download)
- CMSIS-DAP driver first-time setup
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path


# Keil driver selection codes
DRIVER_CMSIS_DAP = 4098
DRIVER_JLINK = 4099

# Known Keil paths
_KEIL_CANDIDATES = [
    Path(r"D:\Program Files\ARM\MDK5\UV4\UV4.exe"),
    Path(r"C:\Keil_v5\UV4\UV4.exe"),
    Path(r"C:\Program Files\ARM\MDK5\UV4\UV4.exe"),
]


def find_keil_uv4() -> Path | None:
    """Locate UV4.exe."""
    for p in _KEIL_CANDIDATES:
        if p.exists():
            return p
    found = shutil_which("UV4.exe")
    return Path(found) if found else None


def shutil_which(name: str) -> str | None:
    import shutil
    return shutil.which(name)


def set_driver_selection(proj_path: Path, driver: int) -> bool:
    """Set <DriverSelection> in .uvprojx XML."""
    try:
        tree = ET.parse(str(proj_path))
        for elem in tree.iter():
            if elem.tag == "DriverSelection":
                elem.text = str(driver)
                tree.write(str(proj_path), encoding="UTF-8", xml_declaration=True)
                return True
        return False
    except Exception:
        return False


def build_project(uv4: Path, proj: Path, target: str) -> tuple[bool, str]:
    """Run UV4 -r (rebuild). Returns (success, build_log_text)."""
    log_path = proj.with_suffix(".build.log")

    # UV4 -r: rebuild all, -j0: single thread, -o: log file
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

    # Success: "0 Error(s)" in log + exit code 0
    success = (
        "0 Error(s)" in log_text
        and proc.returncode == 0
    )
    return success, log_text


def flash_project(uv4: Path, proj: Path, target: str) -> bool:
    """Flash via UV4 debug session (auto-download)."""
    print("Starting Keil uVision in debug mode...")
    print("The firmware will be downloaded automatically.")
    print("Press Ctrl+F5 or Flash->Download if auto-download doesn't start.")
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

    # Wait for user to close Keil
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

    # Check GD_Link_CLI as fallback
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "shared"))
    try:
        from tool_config import get_tool_path
        gdlink = get_tool_path("gdlink-cli")
        if gdlink:
            print(f"  GD_Link_CLI  : {gdlink}")
    except Exception:
        pass

    print("\n  To use this skill:")
    print("  1. Open project in Keil")
    print("  2. Flash -> Configure Flash Tools -> Debug")
    print("  3. Select 'CMSIS-DAP Debugger'")
    print("  4. Settings -> verify GD-Link appears in Serial No")
    print("  5. Port: SW, Max Clock: 10MHz")


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
    ctypes.windll.version.VerQueryValueW(buf, r"\\StringFileInfo\\040904b0\\ProductVersion", ctypes.byref(p), ctypes.byref(l))
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
    parser.add_argument("--set-cmsis-dap", action="store_true",
                        help="Configure project to use CMSIS-DAP driver")
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    # --detect mode
    if args.detect:
        print_detect_report()
        return 0

    # Require --project
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

    # --set-cmsis-dap
    if args.set_cmsis_dap:
        ok = set_driver_selection(proj, DRIVER_CMSIS_DAP)
        print(f"DriverSelection -> CMSIS-DAP ({DRIVER_CMSIS_DAP}) {'OK' if ok else 'FAILED'}")
        if ok:
            print("Open the project in Keil to verify GD-Link is detected.")
        return 0 if ok else 1

    # --build-only / build step
    if not args.flash_only:
        print(f"Building '{args.target}' ...")
        ok, log = build_project(uv4, proj, args.target)

        if args.verbose:
            for line in log.splitlines()[-30:]:
                print(f"  {line}")

        if not ok:
            print("\nBUILD FAILED", file=sys.stderr)
            # Show error lines
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
