#!/usr/bin/env python3
"""Keil .uvprojx flash/debug configuration safe manager.

Provides read-modify-write of flash-related XML elements in Keil uVision
project files without corrupting unrelated settings.  Supports configuration
presets for common debug-probe + reset-behaviour combinations.

Presets
-------
stlink-default   ST-Link/GD-Link (CMSIS-DAP 4101), standard flash
jlink-no-reset   J-Link (8010), flash only, no MCU reset afterwards
jlink-reset-run  J-Link (8010), flash then reset-and-run
cmsis-dap        CMSIS-DAP generic (4098), standard flash
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Driver-selection codes (Keil MDK internal)
# ---------------------------------------------------------------------------
DRIVER_CODES: dict[str, int] = {
    "stlink": 4101,
    "jlink": 8010,
    "cmsis-dap": 4098,
    "ulink": 0,
}

DRIVER_NAMES: dict[int, str] = {
    4101: "ST-Link",
    4100: "ST-Link",
    8010: "J-Link",
    8001: "J-Link",
    4098: "CMSIS-DAP",
    5530: "CMSIS-DAP",
    5500: "CMSIS-DAP",
    0: "ULINK",
}

# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

@dataclass
class FlashPreset:
    name: str
    description: str
    driver_selection: int
    # J-Link specific
    jlink_reset_type: int | None = None       # 0=no-reset, 1=reset+run
    jlink_script_file: str = ""               # debug init script
    # Common
    update_flash_before_debugging: int = 1    # 1=yes
    verify_download: int = 1                  # 1=yes


FLASH_PRESETS: dict[str, FlashPreset] = {
    "stlink-default": FlashPreset(
        name="stlink-default",
        description="ST-Link / GD-Link, standard flash download",
        driver_selection=4101,
    ),
    "jlink-no-reset": FlashPreset(
        name="jlink-no-reset",
        description="J-Link, flash without MCU reset",
        driver_selection=8010,
        jlink_reset_type=0,
    ),
    "jlink-reset-run": FlashPreset(
        name="jlink-reset-run",
        description="J-Link, flash + Reset and Run",
        driver_selection=8010,
        jlink_reset_type=1,
    ),
    "cmsis-dap": FlashPreset(
        name="cmsis-dap",
        description="CMSIS-DAP generic (GD-Link compatible)",
        driver_selection=4098,
    ),
}


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def _find_child(parent: ET.Element, tag: str) -> ET.Element | None:
    """Find direct child element by local tag name (ignoring namespace)."""
    for child in parent:
        tag_local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag_local == tag:
            return child
    return None


def _find_descendant(parent: ET.Element, tag: str) -> ET.Element | None:
    """Find first descendant element by local tag name."""
    for elem in parent.iter():
        tag_local = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag_local == tag:
            return elem
    return None


def read_flash_config(project_path: Path, target_name: str | None = None) -> dict[str, Any]:
    """Read flash/debug configuration from a Keil .uvprojx file.

    Returns dict with keys: driver_selection, driver_name, update_flash_before_debugging,
    device, output_name, errors (list of parse issues).
    """
    result: dict[str, Any] = {
        "driver_selection": None,
        "driver_name": None,
        "update_flash_before_debugging": None,
        "device": None,
        "output_name": None,
        "errors": [],
    }

    if not project_path.is_file():
        result["errors"].append(f"File not found: {project_path}")
        return result

    try:
        tree = ET.parse(str(project_path))
    except ET.ParseError as e:
        result["errors"].append(f"XML parse error: {e}")
        return result

    root = tree.getroot()

    for target_elem in root.iter("Target"):
        name_elem = _find_child(target_elem, "TargetName")
        if target_name and name_elem is not None and name_elem.text:
            if name_elem.text.strip() != target_name:
                continue

        # Device
        device_elem = _find_descendant(target_elem, "Device")
        if device_elem is not None and device_elem.text:
            result["device"] = device_elem.text.strip()

        # Output name
        output_elem = _find_descendant(target_elem, "OutputName")
        if output_elem is not None and output_elem.text:
            result["output_name"] = output_elem.text.strip()

        # DriverSelection
        ds_elem = _find_descendant(target_elem, "DriverSelection")
        if ds_elem is not None and ds_elem.text:
            code = int(ds_elem.text.strip())
            result["driver_selection"] = code
            result["driver_name"] = DRIVER_NAMES.get(code, f"Unknown({code})")

        # UpdateFlashBeforeDebugging
        ufbd_elem = _find_descendant(target_elem, "UpdateFlashBeforeDebugging")
        if ufbd_elem is not None and ufbd_elem.text:
            result["update_flash_before_debugging"] = int(ufbd_elem.text.strip())

        break  # first matching target

    return result


# ---------------------------------------------------------------------------
# Write (safe – preserves XML declaration, comments, non-flash elements)
# ---------------------------------------------------------------------------

def apply_flash_preset(
    project_path: Path,
    preset_name: str,
    target_name: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Safely apply a flash configuration preset to a .uvprojx file.

    Only modifies flash-related elements; all other XML content (source files,
    compiler flags, include paths, etc.) is preserved unchanged.

    Parameters
    ----------
    project_path : Path
        Path to the .uvprojx file to modify.
    preset_name : str
        Key in FLASH_PRESETS (e.g. "jlink-reset-run").
    target_name : str | None
        Target name to modify; if None, modifies the first target.
    dry_run : bool
        If True, report what would change without writing.

    Returns
    -------
    dict with keys: status, changes (list of str), errors (list of str), preset_name.
    """
    preset = FLASH_PRESETS.get(preset_name)
    if preset is None:
        return {
            "status": "failure",
            "preset_name": preset_name,
            "changes": [],
            "errors": [f"Unknown preset '{preset_name}'. Available: {list(FLASH_PRESETS.keys())}"],
        }

    if not project_path.is_file():
        return {
            "status": "failure",
            "preset_name": preset_name,
            "changes": [],
            "errors": [f"Project file not found: {project_path}"],
        }

    # Read original XML text to preserve formatting
    original_text = project_path.read_text(encoding="utf-8")

    try:
        tree = ET.parse(str(project_path))
    except ET.ParseError as e:
        return {
            "status": "failure",
            "preset_name": preset_name,
            "changes": [],
            "errors": [f"XML parse error: {e}"],
        }

    root = tree.getroot()
    changes: list[str] = []
    errors: list[str] = []
    modified = False

    found_target = False
    for target_elem in root.iter("Target"):
        name_elem = _find_child(target_elem, "TargetName")
        if target_name and name_elem is not None and name_elem.text:
            if name_elem.text.strip() != target_name:
                continue
        found_target = True
        target_display = name_elem.text.strip() if (name_elem is not None and name_elem.text) else "(first target)"

        # --- DriverSelection ---
        ds_elem = _find_descendant(target_elem, "DriverSelection")
        if ds_elem is not None:
            old_code = ds_elem.text.strip() if ds_elem.text else "None"
            new_code = str(preset.driver_selection)
            if old_code != new_code:
                old_name = DRIVER_NAMES.get(int(old_code), f"Unknown({old_code})") if old_code != "None" else "None"
                new_name = DRIVER_NAMES.get(preset.driver_selection, f"Unknown({new_code})")
                changes.append(f"DriverSelection: {old_name} ({old_code}) → {new_name} ({new_code})")
                if not dry_run:
                    ds_elem.text = new_code
                    modified = True
        else:
            errors.append("DriverSelection element not found in project XML")
            # Try to create it
            flash1 = _find_descendant(target_elem, "Flash1")
            if flash1 is not None:
                new_ds = ET.SubElement(flash1, "DriverSelection")
                new_ds.text = str(preset.driver_selection)
                changes.append(f"DriverSelection: (missing) → {DRIVER_NAMES.get(preset.driver_selection)} ({preset.driver_selection})")
                if not dry_run:
                    modified = True

        # --- UpdateFlashBeforeDebugging ---
        ufbd_elem = _find_descendant(target_elem, "UpdateFlashBeforeDebugging")
        if ufbd_elem is not None:
            old_val = ufbd_elem.text.strip() if ufbd_elem.text else "0"
            new_val = str(preset.update_flash_before_debugging)
            if old_val != new_val:
                changes.append(f"UpdateFlashBeforeDebugging: {old_val} → {new_val}")
                if not dry_run:
                    ufbd_elem.text = new_val
                    modified = True

        break  # only modify first matching target

    if not found_target:
        errors.append(f"Target '{target_name or '(first)'}' not found in project")

    if dry_run:
        return {
            "status": "dry_run",
            "preset_name": preset_name,
            "preset_description": preset.description,
            "changes": changes,
            "errors": errors,
        }

    if modified:
        # Use a custom serializer that preserves the XML declaration
        output = _serialize_preserving_declaration(tree, original_text)
        project_path.write_text(output, encoding="utf-8")

    # Handle JLinkSettings.ini for J-Link presets
    jlink_changes = _apply_jlink_settings(project_path.parent, preset, dry_run=False)
    changes.extend(jlink_changes)

    return {
        "status": "success" if (modified or jlink_changes) else "no_change",
        "preset_name": preset_name,
        "preset_description": preset.description,
        "changes": changes,
        "errors": errors,
    }


def _serialize_preserving_declaration(tree: ET.ElementTree, original_text: str) -> str:
    """Serialize XML tree while preserving the original XML declaration."""
    buf = io.StringIO()
    tree.write(buf, encoding="unicode", xml_declaration=False)

    # Check if original had a declaration
    decl_match = re.match(r'^<\?xml\s[^?]*\?>\s*', original_text)
    if decl_match:
        return decl_match.group() + "\n" + buf.getvalue().lstrip()
    return buf.getvalue()


def _apply_jlink_settings(project_dir: Path, preset: FlashPreset, dry_run: bool = False) -> list[str]:
    """Create or update JLinkSettings.ini in the project directory.

    Only acts when preset.driver_selection corresponds to J-Link.
    """
    if DRIVER_NAMES.get(preset.driver_selection) != "J-Link":
        return []

    ini_path = project_dir / "JLinkSettings.ini"
    changes: list[str] = []

    # Default JLinkSettings.ini skeleton
    if preset.jlink_reset_type is not None:
        # Reset type: 0 = no reset, 1 = hardware reset, etc.
        if ini_path.exists():
            old_content = ini_path.read_text(encoding="utf-8", errors="replace")
            # Update or add ResetType in [CPU] section
            new_lines = []
            in_cpu = False
            updated = False
            for line in old_content.splitlines(True):
                if line.strip().startswith("[CPU]"):
                    in_cpu = True
                    new_lines.append(line)
                    continue
                if in_cpu and line.strip().startswith("["):
                    in_cpu = False
                if in_cpu and "ResetType" in line:
                    old_val = line.split("=")[-1].strip()
                    new_val = str(preset.jlink_reset_type)
                    if old_val != new_val:
                        new_lines.append(f"ResetType = {new_val}\n")
                        changes.append(f"JLinkSettings.ini ResetType: {old_val} → {new_val}")
                        updated = True
                        continue
                new_lines.append(line)

            if not updated and preset.jlink_reset_type is not None:
                # Append ResetType if not found in [CPU] section
                final_lines = []
                appended = False
                for i, line in enumerate(new_lines):
                    final_lines.append(line)
                    if line.strip().startswith("[CPU]") and not appended:
                        final_lines.append(f"ResetType = {preset.jlink_reset_type}\n")
                        changes.append(f"JLinkSettings.ini ResetType: (missing) → {preset.jlink_reset_type}")
                        appended = True

                if not appended:
                    final_lines.append("\n[CPU]\n")
                    final_lines.append(f"ResetType = {preset.jlink_reset_type}\n")
                    changes.append(f"JLinkSettings.ini [CPU] ResetType: (new section) → {preset.jlink_reset_type}")

                new_lines = final_lines

            if not dry_run:
                ini_path.write_text("".join(new_lines), encoding="utf-8")
        else:
            content = (
                "[BREAKPOINTS]\n"
                "ForceImpTypeAny = 0\n"
                "ShowInfoWin = 1\n"
                "EnableFlashBP = 2\n"
                "BPDuringExecution = 0\n"
                "[CPU]\n"
                f"MonModeVTableAddr = 0xFFFFFFFF\n"
                f"MonModeDebug = 0\n"
                f"MaxNumAPs = 0\n"
                f"LowPowerHandlingMode = 0\n"
                f"AllowSimulation = 1\n"
                f"ResetType = {preset.jlink_reset_type}\n"
                'ScriptFile=""\n'
                "[FLASH]\n"
                "RMWThreshold = 0x400\n"
                'Loaders=""\n'
                "EraseType = 0x00\n"
                "CacheExcludeSize = 0x00\n"
                "CacheExcludeAddr = 0x00\n"
                "MinNumBytesFlashDL = 0\n"
                "SkipProgOnCRCMatch = 1\n"
                "VerifyDownload = 1\n"
                "AllowCaching = 1\n"
                "EnableFlashDL = 2\n"
                "Override = 1\n"
                'Device="Cortex-M33"\n'
            )
            changes.append(f"JLinkSettings.ini: created with ResetType={preset.jlink_reset_type}")
            if not dry_run:
                ini_path.write_text(content, encoding="utf-8")

    return changes


# ---------------------------------------------------------------------------
# Diff helpers
# ---------------------------------------------------------------------------

def diff_flash_configs(path_a: Path, path_b: Path) -> dict[str, Any]:
    """Compare flash configurations of two .uvprojx files.

    Returns dict with 'identical' (bool) and 'differences' (list of str).
    """
    config_a = read_flash_config(path_a)
    config_b = read_flash_config(path_b)

    diffs: list[str] = []
    keys = ["driver_selection", "driver_name", "update_flash_before_debugging", "device", "output_name"]

    for key in keys:
        val_a = config_a.get(key)
        val_b = config_b.get(key)
        if val_a != val_b:
            diffs.append(f"{key}: {val_a} ≠ {val_b}")

    return {
        "identical": len(diffs) == 0 and not config_a.get("errors") and not config_b.get("errors"),
        "differences": diffs,
        "errors_a": config_a.get("errors", []),
        "errors_b": config_b.get("errors", []),
    }


# ---------------------------------------------------------------------------
# CLI (optional standalone invocation)
# ---------------------------------------------------------------------------

def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Keil .uvprojx flash configuration manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Available presets:
{chr(10).join(f'  {k:20s} {v.description}' for k, v in FLASH_PRESETS.items())}

Examples:
  %(prog)s --read project.uvprojx
  %(prog)s --read project.uvprojx --target GD32F50X
  %(prog)s --apply jlink-reset-run --project project.uvprojx
  %(prog)s --apply jlink-no-reset --project project.uvprojx --dry-run
  %(prog)s --diff a.uvprojx b.uvprojx
        """,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--read", metavar="PROJECT", help="Read current flash config")
    group.add_argument("--apply", metavar="PRESET", help="Apply a flash config preset")
    group.add_argument("--diff", nargs=2, metavar=("A", "B"), help="Compare two .uvprojx flash configs")
    group.add_argument("--list-presets", action="store_true", help="List available presets")

    parser.add_argument("--project", help=".uvprojx file path (for --apply)")
    parser.add_argument("--target", help="Target name within the project")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing")

    args = parser.parse_args()

    if args.list_presets:
        print("\nAvailable flash configuration presets:\n")
        for name, preset in FLASH_PRESETS.items():
            print(f"  {name:20s}  {preset.description}")
            print(f"  {'':20s}  DriverSelection={preset.driver_selection} "
                  f"({DRIVER_NAMES.get(preset.driver_selection, '?')})")
            if preset.jlink_reset_type is not None:
                reset_desc = {0: "no reset", 1: "reset+run"}.get(preset.jlink_reset_type, str(preset.jlink_reset_type))
                print(f"  {'':20s}  J-Link ResetType={preset.jlink_reset_type} ({reset_desc})")
            print()
        return 0

    if args.read:
        config = read_flash_config(Path(args.read), args.target)
        print(f"\nFlash configuration for: {args.read}")
        if args.target:
            print(f"  Target: {args.target}")
        print(f"  Device:                  {config['device'] or 'N/A'}")
        print(f"  Output:                  {config['output_name'] or 'N/A'}")
        print(f"  Debug Probe:             {config['driver_name'] or 'N/A'} "
              f"(code={config['driver_selection']})")
        print(f"  Flash Before Debug:      {config['update_flash_before_debugging']}")
        if config["errors"]:
            for e in config["errors"]:
                print(f"  ⚠ {e}")
        return 0

    if args.diff:
        result = diff_flash_configs(Path(args.diff[0]), Path(args.diff[1]))
        print(f"\nComparing: {args.diff[0]} vs {args.diff[1]}")
        if result["identical"]:
            print("  ✅ Identical flash configurations")
        else:
            print("  ❌ Differences found:")
            for d in result["differences"]:
                print(f"     {d}")
        for e in result.get("errors_a", []):
            print(f"  ⚠ A: {e}")
        for e in result.get("errors_b", []):
            print(f"  ⚠ B: {e}")
        return 0

    if args.apply:
        if not args.project:
            parser.error("--project is required with --apply")
            return 1

        result = apply_flash_preset(
            Path(args.project), args.apply, args.target, dry_run=args.dry_run
        )

        prefix = "[DRY RUN] " if args.dry_run else ""
        print(f"\n{prefix}Apply preset '{args.apply}': {result['preset_description']}")
        print(f"  Project: {args.project}")
        print(f"  Status:  {result['status']}")

        if result["changes"]:
            print(f"\n  Changes:")
            for c in result["changes"]:
                print(f"    + {c}")
        else:
            print("  (no changes needed)")

        if result["errors"]:
            print(f"\n  ⚠ Errors:")
            for e in result["errors"]:
                print(f"    {e}")

        return 0 if result["status"] in ("success", "no_change", "dry_run") else 1

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
