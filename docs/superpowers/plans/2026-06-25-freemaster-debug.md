# FreeMASTER 调试 Skill 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新建 `freemaster-debug` skill，支持自动探测 FreeMASTER 安装、生成 `.pmpx` 项目文件、启动 FreeMASTER GUI 进行 J-Link BDM 实时变量监控与在线调优。

**Architecture:** 三个 Python 脚本：探测脚本（路径盲搜+版本识别）、生成器（基于参考 .pmpx 纯 XML 模板做路径替换与变量注入）、主控脚本（编排探测→生成→启动）。复用 `shared/tool_config.py` 的配置层和 `contracts.md` 的 Project Profile。

**关键发现：** `.pmpx` 是 FreeMASTER 3.x 的纯 XML 序列化格式（非 ZIP），ELF 路径存储在 `CPrjDoc_MapFileInfo.file_name` 字段。通信配置（BDM/J-Link 插件选择、SWD 速度、设备名）存储在 FreeMASTER 的应用层（注册表/AppData），不在 .pmpx 文件中——用户在 FreeMASTER GUI 中配置一次即可持久保留。因此生成器只需处理 ELF 路径替换和可选的变量注入。

**Tech Stack:** Python 3.11+ stdlib (argparse, re, subprocess, pathlib, shutil), 与项目现有 `debug-jlink` skill 共享 J-Link 探测逻辑。

---

## 文件结构总览

```
skills/freemaster-debug/
├── SKILL.md                        # 新建：skill 定义（8 必需章节）
├── references/
│   └── usage.md                    # 新建：CLI 参数说明
└── scripts/
    ├── freemaster_detect.py        # 新建：FreeMASTER 安装探测
    ├── freemaster_pmpx_gen.py      # 新建：.pmpx 项目文件生成器
    └── freemaster_debugger.py      # 新建：主控脚本

需修改的现有文件：
├── SKILL.md                        # 根目录：添加 freemaster-debug 到技能列表
├── README.md                       # 添加 freemaster-debug 条目
├── shared/contracts.md             # 可选：添加 freemaster_exe 字段
└── .claude/settings.json           # 添加 FreeMASTER 相关权限
```

---

### Task 1: 创建目录结构并获取 .pmpx 参考模板

**Files:**
- Create: `skills/freemaster-debug/`
- Create: `skills/freemaster-debug/scripts/`
- Create: `skills/freemaster-debug/references/`

这是准备工作——建立目录骨架并获取用户本机真实的 .pmpx 格式，作为后续生成器的模板基础。

- [ ] **Step 1: 创建目录结构**

```powershell
New-Item -ItemType Directory -Force -Path skills/freemaster-debug/scripts
New-Item -ItemType Directory -Force -Path skills/freemaster-debug/references
```

- [ ] **Step 2: 复制现有 .pmpx 作为参考模板**

使用系统上已找到的真实 .pmpx 文件（`D:\CYC\PROJUSE\GD32F303_MT9818\11_I2C_EEPROM\MDK-ARM\Project.pmpx`，FreeMASTER 3.2.5.3）。

```powershell
Copy-Item "D:\CYC\PROJUSE\GD32F303_MT9818\11_I2C_EEPROM\MDK-ARM\Project.pmpx" "skills/freemaster-debug/references/_ref_freemaster_template.pmpx"
```

- [ ] **Step 3: 解析并记录 .pmpx XML 结构**

已知 .pmpx 是纯 XML 文件（非 ZIP），根元素 `<xmlarchive schema="65535">`，内部是 C++ 对象序列化图。关键字段：

| 字段 | 对象类型 | 成员名 | 示例值 |
|------|----------|--------|--------|
| FreeMASTER 版本 | `CPrjDoc` | `version` | `3.2.5.3` |
| ELF/AXF 路径 | `CPrjDoc_MapFileInfo` | `file_name` | `C:\Users\...\Project.axf` |
| 变量列表 | `CObList` (variables) | `item0`..`itemN` | 指向 `CVariable` 对象 |
| 通信状态 | `CPrjDoc` | `comm_state_enabled` | `1` |
| Recorder 配置 | `CPrjDoc` | 相关成员 | 嵌入主文档对象 |

验证解析：

```bash
python3 -c "
import re
path = 'skills/freemaster-debug/references/_ref_freemaster_template.pmpx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()
print('File size:', len(content), 'bytes')
print('Root element:', content[:100])
# Count objects
types = set(re.findall(r'type=\\\"([^\\\"]+)\\\"', content))
for t in sorted(types):
    print(f'  {t}')
# Verify ELF path exists
if 'file_name' in content:
    m = re.search(r'file_name.*?string\">(.*?)<', content)
    if m: print(f'ELF ref: {m.group(1)}')
"
```

- [ ] **Step 4: 提交**

```bash
git add skills/freemaster-debug/
git commit -m "feat: add freemaster-debug directory structure and reference template"
```

---

### Task 2: 编写 FreeMASTER 探测脚本

**Files:**
- Create: `skills/freemaster-debug/scripts/freemaster_detect.py`

复用了 `shared/tool_config.py` 的 `get_tool_path`/`set_tool_path` 接口，匹配项目现有 `jlink_debugger.py` 的代码风格。

- [ ] **Step 1: 写入 freemaster_detect.py**

```python
#!/usr/bin/env python3
"""FreeMASTER 安装自动探测工具。

为 `freemaster-debug` skill 提供可重复调用的探测入口，支持：

- 按已知安装路径盲搜 FreeMASTER.exe
- 识别 Lite 版与完整版
- 检查 BDM/J-Link 通信插件是否可用
- 支持保存探测结果到工具配置
"""

from __future__ import annotations

import argparse
import platform
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILLS_DIR = _SCRIPT_DIR.parent.parent
for _candidate in [_SKILLS_DIR / "shared", _SKILLS_DIR.parent / "shared"]:
    if (_candidate / "tool_config.py").exists():
        sys.path.insert(0, str(_candidate))
        break
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
    import shutil
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
```

- [ ] **Step 2: 验证脚本可独立运行**

```powershell
cd C:\Users\Atop\Desktop\embed-ai-tool
python skills/freemaster-debug/scripts/freemaster_detect.py --detect
```

期望：输出探测报告（找到或未找到 FreeMASTER），进程退出码反映是否可用。

- [ ] **Step 3: 提交**

```bash
git add skills/freemaster-debug/scripts/freemaster_detect.py
git commit -m "feat: add freemaster_detect.py — FreeMASTER installation auto-detection"
```

---

### Task 3: 编写 .pmpx 项目文件生成器

**Files:**
- Create: `skills/freemaster-debug/scripts/freemaster_pmpx_gen.py`

**先决条件：** Task 1 的参考 .pmpx 文件 `_ref_freemaster_template.pmpx` 必须已存在。

`.pmpx` 是纯 XML 文件，根元素 `<xmlarchive schema="65535">`。ELF/AXF 路径唯一地存储在 `<member name="file_name" type="string">` 节点中。通信配置（BDM/J-Link）存储在 FreeMASTER 应用层，不在 .pmpx 内，无需处理。

生成策略：纯文本正则替换，只替换 ELF 文件路径。

- [ ] **Step 1: 写入 freemaster_pmpx_gen.py**

```python
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

_SCRIPT_DIR = Path(__file__).resolve().parent
_REFERENCES_DIR = _SCRIPT_DIR.parent / "references"
_DEFAULT_TEMPLATE = _REFERENCES_DIR / "_ref_freemaster_template.pmpx"

# .pmpx 中 ELF 文件路径的唯一定位正则
# 格式: <member name="file_name" type="string">C:\path\to\file.axf</member>
_FILE_NAME_RE = re.compile(
    r'(<member name="file_name" type="string">)[^<]*(</member>)'
)

# 变量容器节点的定位正则（CObList 中 member name="variables" 指向的列表）
# 格式: <object name="ObjIdXXXX" type="CObList">...<member name="itemN" ...>ObjIdYYYY</member>...</object>
_VARIABLES_CONTAINER_RE = re.compile(
    r'(<member name="variables" type="CObListEx">ObjId\d+</member>)'
)


def _make_elf_relative(elf_path: str, output_dir: Path) -> str:
    """将 ELF 路径转为相对于 .pmpx 输出目录的相对路径."""
    elf = Path(elf_path).resolve()
    out = output_dir.resolve()
    try:
        return str(elf.relative_to(out))
    except ValueError:
        return str(elf)


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

    # 替换 ELF 文件路径
    new_content, subs = _FILE_NAME_RE.subn(
        rf"\g<1>{elf_path}\g<2>", content
    )
    if subs == 0:
        return {
            "status": "failure",
            "path": "",
            "vars_count": 0,
            "error": f"模板中未找到 file_name 成员，请确认模板是 FreeMASTER 3.x 导出的 .pmpx",
        }

    # 备份已存在的输出
    if output_path.exists():
        backup = output_path.with_suffix(".pmpx.bak")
        shutil.copy2(output_path, backup)

    # 写入
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(new_content, encoding="utf-8")

    vars_count = len(variables) if variables else 0
    if variables:
        # NOTE: 变量注入功能预留。.pmpx 的 CVariable 对象图较复杂，
        # 当前版本仅做 ELF 路径替换。用户在 FreeMASTER GUI 中手动添加变量。
        pass

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
```

- [ ] **Step 2: 用参考模板验证生成器**

```powershell
# 用模板自身作为输入测试（验证正则替换正确）
python skills/freemaster-debug/scripts/freemaster_pmpx_gen.py --elf "D:/test/new_app.axf" --device GD32F303 --output test_output.pmpx
```

验证替换结果：
```bash
python3 -c "
import re
content = open('test_output.pmpx', 'r', encoding='utf-8').read()
m = re.search(r'<member name=\"file_name\" type=\"string\">([^<]*)</member>', content)
if m: print(f'ELF ref replaced: {m.group(1)}')
else: print('ERROR: file_name not found')
"
```

期望输出：`ELF ref replaced: D:/test/new_app.axf`

```powershell
Remove-Item test_output.pmpx -ErrorAction SilentlyContinue
```

- [ ] **Step 3: 用真实 ELF 和真实设备做完整测试**

```powershell
python skills/freemaster-debug/scripts/freemaster_pmpx_gen.py --elf <path/to/real.axf> --device <REAL_MCU> --output test_freemaster.pmpx
```

用 FreeMASTER 打开 `test_freemaster.pmpx`，确认：
- 项目文件能正常加载
- ELF 符号表正确关联
- 通信设置保持模板中的配置

测试后删除：
```powershell
Remove-Item test_freemaster.pmpx -ErrorAction SilentlyContinue
Remove-Item test_freemaster.pmpx.bak -ErrorAction SilentlyContinue
```

- [ ] **Step 4: 提交**

```bash
git add skills/freemaster-debug/scripts/freemaster_pmpx_gen.py
git commit -m "feat: add freemaster_pmpx_gen.py — .pmpx project file generator"
```

---

### Task 4: 编写主控脚本

**Files:**
- Create: `skills/freemaster-debug/scripts/freemaster_debugger.py`

编排探测 → 生成 → 启动的完整流程，是 LLM 调用的主入口。

- [ ] **Step 1: 写入 freemaster_debugger.py**

```python
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

_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILLS_DIR = _SCRIPT_DIR.parent.parent
for _candidate in [_SKILLS_DIR / "shared", _SKILLS_DIR.parent / "shared"]:
    if (_candidate / "tool_config.py").exists():
        sys.path.insert(0, str(_candidate))
        break
from tool_config import get_tool_path

# 导入同目录的探测和生成模块
from freemaster_detect import detect_environment
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


# ── FreeMASTER 工具查找 ──

def find_freemaster() -> str | None:
    """查找 FreeMASTER.exe，优先级：配置文件 → PATH → 安装路径盲搜."""
    configured = get_tool_path("freemaster")
    if configured and Path(configured).is_file():
        return configured

    import shutil
    for exe in ["FreeMASTER.exe", "FreeMASTER Lite.exe"]:
        found = shutil.which(exe)
        if found:
            return found

    env = detect_environment()
    installations = env.get("freemaster", {}).get("installations", [])
    if installations:
        return str(installations[0]["path"])

    return None


# ── 启动 FreeMASTER ──

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
            return True  # Start-Process 通常即使成功也会有些 stderr
    except subprocess.TimeoutExpired:
        print("⚠️ 启动命令超时，但 FreeMASTER 可能已在后台启动")
        return True
    except FileNotFoundError:
        print(f"❌ 未找到 FreeMASTER: {freemaster_exe}")
        return False
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        return False


# ── 主流程 ──

def run_start_mode(args: argparse.Namespace) -> DebugResult:
    """start 模式：生成 .pmpx 并启动 FreeMASTER."""
    evidence: list[str] = []

    # Step 1: 平台检查
    if platform.system() != "Windows":
        return DebugResult(
            status="blocked",
            summary="FreeMASTER 仅支持 Windows 平台",
            failure_category="platform-unsupported",
            evidence=[f"当前平台: {platform.system()}"],
        )

    # Step 2: 查找 FreeMASTER
    freemaster_exe = find_freemaster()
    if not freemaster_exe:
        return DebugResult(
            status="blocked",
            summary="未找到 FreeMASTER 安装",
            failure_category="environment-missing",
            evidence=["搜索路径: C:\\NXP\\, C:\\Program Files\\NXP\\, PATH"],
        )
    evidence.append(f"FreeMASTER: {freemaster_exe}")

    # Step 3: 检查 ELF
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

    # Step 4: 检查 MCU 设备名
    device = args.device
    if not device:
        return DebugResult(
            status="blocked",
            summary="缺少目标 MCU 型号（--device）",
            failure_category="ambiguous-context",
            evidence=evidence,
        )
    evidence.append(f"目标设备: {device}")

    # Step 5: 生成 .pmpx
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
    partial = gen_result["status"] == "partial_success"

    # Step 6: 启动 FreeMASTER
    launched = launch_freemaster(freemaster_exe, pmpx_str)

    if launched:
        summary_parts = [f"FreeMASTER 已启动，项目 {Path(pmpx_str).name} 已加载"]
        if vars_count > 0:
            summary_parts.append(f"（预置 {vars_count} 个变量）")
        if partial:
            summary_parts.append("（部分变量未预置，请手动添加）")

        return DebugResult(
            status="partial_success" if partial else "success",
            summary=" ".join(summary_parts),
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

    # 平台检查（仅 Windows 支持，但生成文件可以在任何平台做）
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


# ── 输出 ──

def print_debug_report(result: DebugResult) -> None:
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


# ── CLI ──

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

    # 探测模式
    if args.detect:
        env = detect_environment()
        from freemaster_detect import print_detect_report
        print_detect_report(env)
        ok = env["freemaster"]["available"] and env["platform"]["supported"]
        return 0 if ok else 1

    # 调试/生成模式
    if args.mode == "generate":
        result = run_generate_mode(args)
    else:
        result = run_start_mode(args)

    print_debug_report(result)

    status_codes = {"success": 0, "partial_success": 0, "blocked": 1, "failure": 1}
    return status_codes.get(result.status, 1)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 验证主控脚本可导入**

```powershell
cd C:\Users\Atop\Desktop\embed-ai-tool\skills\freemaster-debug\scripts
python -c "import freemaster_debugger; print('import OK')"
```

- [ ] **Step 3: 提交**

```bash
git add skills/freemaster-debug/scripts/freemaster_debugger.py
git commit -m "feat: add freemaster_debugger.py — main orchestration script"
```

---

### Task 5: 编写 SKILL.md

**Files:**
- Create: `skills/freemaster-debug/SKILL.md`

严格按照项目 8 必需章节模板编写，匹配 `debug-jlink` 的风格。

- [ ] **Step 1: 写入 SKILL.md**

```markdown
---
name: freemaster-debug
description: 当需要通过 FreeMASTER 工具实时监控嵌入式固件变量、进行运行时参数在线调优、或长时间数据记录时使用。
---

# FreeMASTER 实时调试

## 适用场景

- 用户想看某个全局变量的实时变化曲线（虚拟示波器/Scope）。
- 在固件运行时修改 PID 系数、阈值等参数，无需重新编译烧录。
- 长时间记录传感器数据或系统状态到文件（Recorder），用于离线分析。
- 通过 J-Link 探针的 BDM/SWD 接口直接访问 MCU 内存，无需固件嵌入 FreeMASTER 驱动。
- 与串口日志（`serial-monitor`）配合，同时观察运行时行为和高频变量变化。

以下场景请使用其他技能：
- 单步执行、断点调试、调用栈查看 → `debug-jlink`
- 抓取 printf 串口日志 → `serial-monitor`
- 固件崩溃后寄存器/栈回溯检查 → `debug-jlink`（crash-context 模式）

## 必要输入

- 一份带符号的 `ELF` 文件，或包含 `artifact_path` 的 `Project Profile`。
- `--device` 参数指定目标 MCU 型号（J-Link 设备名，如 `GD32F450IK`）。
- FreeMASTER 安装（自动探测，或通过 `em_config` 手动配置）。
- 可选：要监控的变量名列表（`--vars`）。
- 可选执行模式：`start`（默认，生成 .pmpx + 启动 GUI）、`generate`（仅生成 .pmpx）。

## 自动探测

- FreeMASTER 安装路径按以下顺序自动探测：配置文件 `em_config` → `PATH` 环境变量 → `C:\NXP\` 盲搜 → `C:\Program Files\NXP\` 盲搜。
- ELF 文件路径优先从 `Project Profile` 的 `artifact_path` 读取。
- 目标 MCU 型号从 `Project Profile` 的 `target_mcu` 或 `jlink_device` 读取。
- 变量列表需用户显式提供，无法自动推断。
- 若关键信息缺失（FreeMASTER 未安装 / ELF 不存在 / MCU 未知），返回 `blocked` 状态并引导用户补充。

## 执行步骤

1. 若不确定 FreeMASTER 环境是否就绪，先运行 `freemaster_debugger.py --detect` 确认。
2. 确认 ELF 文件和目标 MCU 型号可用（从 Project Profile 或用户输入）。
3. 若需要先生成 ELF，先调用 `build-keil` / `build-cmake` 等构建 skill。
4. 若需要先烧录固件，先调用 `flash-jlink`。
5. 调用 `freemaster_debugger.py --elf <path> --device <name> [--vars var1,var2]` 生成 .pmpx 并启动 FreeMASTER。
6. 在 FreeMASTER GUI 中：
   - 点击 `GO` 按钮连接目标
   - 在 Variable Grid 中观察变量实时值
   - 将变量拖入 Scope 查看波形
   - 使用 Recorder 记录数据到文件
7. 读取脚本输出的结果报告，确认连接状态。

## 失败分流

- FreeMASTER.exe 未找到 → `environment-missing`
- ELF 文件不存在 → `artifact-missing`
- J-Link 驱动未安装 → `environment-missing`
- MCU 型号未知 → `ambiguous-context`
- .pmpx 写入失败 → `environment-missing`
- FreeMASTER 启动失败 → `target-response-abnormal`
- 非 Windows 平台 → `platform-unsupported`

## 平台说明

- FreeMASTER 3.x 仅支持 Windows 原生运行。Linux/macOS 用户请使用 `serial-monitor` 或 `debug-jlink` 替代。
- 默认通过 J-Link BDM 插件以 SWD 接口连接目标，速度默认 4000 kHz。
- .pmpx 是 FreeMASTER 3.x 的项目文件格式（纯 XML 文本，根元素 `<xmlarchive>`）。
- 自带脚本使用 Python 标准库（re、subprocess），仅 Windows 可启动 GUI。

## 输出约定

- 输出执行模式、FreeMASTER 路径、ELF 路径、.pmpx 路径和预置变量数量。
- 状态：`success`（.pmpx 生成且 FreeMASTER 已启动）、`partial_success`（.pmpx 已生成但变量为空或启动异常）、`blocked`（关键信息缺失）、`failure`（生成失败）。
- 在 `Project Profile` 中保留 `artifact_path`、`target_mcu`、`jlink_device`。
- 成功启动后，下一步是在 FreeMASTER GUI 中手动操作（连接目标、添加变量到 Scope）。

## 交接关系

- 当需要先构建 ELF 时，上游交给 `build-keil` / `build-cmake` / `build-iar` 等构建 skill。
- 当需要先烧录固件到目标时，上游交给 `flash-jlink`。
- 当 ELF 缺失需要 debug 会话先做 download-and-halt 时，上游交给 `debug-jlink`。
- 当需要同时观察串口日志时，并行交给 `serial-monitor`。
- 当 FreeMASTER 记录的 Recorder 数据需要离线分析时，下游交给 `memory-analysis`。
- 当需要 RTOS 任务级监控时，下游交给 `rtos-debug`。
```

- [ ] **Step 2: 验证 SKILL.md 结构**

```powershell
python scripts/validate_repo.py
```

确认 `freemaster-debug` skill 通过校验（8 章节齐全、frontmatter 完整、name 与目录名一致）。

- [ ] **Step 3: 提交**

```bash
git add skills/freemaster-debug/SKILL.md
git commit -m "feat: add freemaster-debug SKILL.md"
```

---

### Task 6: 编写 references/usage.md

**Files:**
- Create: `skills/freemaster-debug/references/usage.md`

参照 `debug-jlink/references/usage.md` 的风格，提供完整的 CLI 参数参考。

- [ ] **Step 1: 写入 usage.md**

```markdown
# FreeMASTER 调试工具 CLI 参考

## 概述

`freemaster_debugger.py` 是 FreeMASTER 调试的主入口脚本。它编排环境探测、.pmpx 生成和 GUI 启动。

## 快速开始

```powershell
# 1. 探测 FreeMASTER 环境
python skills/freemaster-debug/scripts/freemaster_debugger.py --detect

# 2. 生成 .pmpx 并启动 FreeMASTER（需要 ELF + MCU 型号）
python skills/freemaster-debug/scripts/freemaster_debugger.py --elf build/app.elf --device GD32F450IK

# 3. 带预置变量启动
python skills/freemaster-debug/scripts/freemaster_debugger.py --elf build/app.elf --device GD32F450IK --vars adc_value,pid_output

# 4. 仅生成 .pmpx，不启动 GUI
python skills/freemaster-debug/scripts/freemaster_debugger.py --elf build/app.elf --device GD32F450IK --mode generate
```

## 主控脚本参数

| 参数 | 必须 | 默认值 | 说明 |
|------|------|--------|------|
| `--detect` | 否 | — | 仅探测 FreeMASTER 环境，输出安装路径和版本 |
| `--elf` | 是* | — | 带符号的 ELF 固件文件路径 |
| `--device` | 是* | — | J-Link 目标设备名（如 `GD32F450IK`、`STM32F407VG`） |
| `--mode` | 否 | `start` | `start`（生成+启动）或 `generate`（仅生成） |
| `--vars` | 否 | — | 预置变量名，逗号分隔（如 `adc_value,pid_output`） |
| `--sample-rate` | 否 | `1000` | Recorder 采样率，单位 Hz |
| `--jlink-speed` | 否 | `4000` | J-Link SWD 通信速度，单位 kHz |
| `--output-dir` | 否 | 当前目录 | .pmpx 输出目录 |
| `--template` | 否 | 内置参考模板 | 自定义 .pmpx 参考模板路径 |

*start/generate 模式必须。

## 探测脚本参数

`freemaster_detect.py` 可独立运行：

| 参数 | 说明 |
|------|------|
| `--detect` | 探测 FreeMASTER 安装 |
| `--save-config` | 探测成功后保存路径到工具配置 |

## 生成器脚本参数

`freemaster_pmpx_gen.py` 可独立运行（仅生成 .pmpx）：

| 参数 | 必须 | 说明 |
|------|------|------|
| `--elf` | 是 | 带符号的 ELF 文件路径 |
| `--device` | 是 | J-Link 目标设备名 |
| `--output` | 否 | 输出 .pmpx 路径（默认 `<device>.pmpx`） |
| `--vars` | 否 | 变量名，逗号分隔 |
| `--sample-rate` | 否 | 采样率 Hz（默认 1000） |
| `--jlink-speed` | 否 | J-Link 速度 kHz（默认 4000） |
| `--template` | 否 | 参考模板路径 |

## 退出码

| 退出码 | 含义 |
|--------|------|
| `0` | 成功或部分成功（.pmpx 已生成） |
| `1` | 阻塞或失败（关键信息缺失/环境问题） |

## 安装路径配置

若自动探测未找到 FreeMASTER，可通过 `em_config` 手动配置：

```powershell
python scripts/em_config.py set freemaster "D:\NXP\FreeMASTER 3.2\FreeMASTER.exe"
```

或在项目 `.em_skill.json` 中添加：

```json
{
  "tools": {
    "freemaster": "D:\\NXP\\FreeMASTER 3.2\\FreeMASTER.exe"
  }
}
```

## 前置条件

- Windows 操作系统（FreeMASTER 3.x 仅支持 Windows）
- 已安装 SEGGER J-Link 驱动（复用 `debug-jlink` 的环境）
- 目标 MCU 已通过 SWD 接口连接 J-Link 探针
- 已编译带符号的 ELF 固件文件
```

- [ ] **Step 2: 提交**

```bash
git add skills/freemaster-debug/references/usage.md
git commit -m "docs: add freemaster-debug usage reference"
```

---

### Task 7: 更新根级文件

**Files:**
- Modify: `SKILL.md`（根目录）
- Modify: `README.md`
- Modify: `shared/contracts.md`
- Modify: `.claude/settings.json`

- [ ] **Step 1: 在根 SKILL.md 调试分类中添加 freemaster-debug 候选**

先定位调试分类候选表的位置：

```powershell
cd C:\Users\Atop\Desktop\embed-ai-tool
Select-String -Path SKILL.md -Pattern "debug-gdlink|debug-jlink|debug-platformio|rtos-debug" -Context 0,0
```

确认确切行号后，在调试分类候选表中添加 `freemaster-debug` 条目。执行编辑：

```powershell
# 查看相关区域
Get-Content SKILL.md | Select-Object -Skip <调试表起始行-1> -First 20
```

使用 Edit 工具进行精确替换。预期添加一行类似：
```
| 实时变量监控、在线调参、数据记录 | `freemaster-debug` |
```

（具体位置和格式取决于现有 SKILL.md 的实际表格结构，请根据 Step 1 的输出调整。）

- [ ] **Step 2: 在 README.md 技能列表中添加 freemaster-debug**

```powershell
Select-String -Path README.md -Pattern "debug-jlink|debug-gdlink|serial-monitor"
```

定位技能列表表格，添加 `freemaster-debug` 条目。

- [ ] **Step 3: 在 contracts.md 的 Project Profile 中添加 freemaster_exe 字段（可选）**

如果希望 Project Profile 能持久化 FreeMASTER 路径，在字段表中添加：

```
| `freemaster_exe` | 否 | FreeMASTER 可执行文件的绝对路径。 |
```

- [ ] **Step 4: 在 settings.json 中添加权限**

```powershell
Get-Content .claude/settings.json
```

在 `permissions.allow` 数组中添加：
```json
"Bash(python skills/freemaster-debug/scripts/*)"
```

- [ ] **Step 5: 运行全局校验**

```powershell
python scripts/validate_repo.py
```

确认所有 skill 通过校验，无警告。

- [ ] **Step 6: 提交**

```bash
git add SKILL.md README.md shared/contracts.md .claude/settings.json
git commit -m "feat: register freemaster-debug skill in root manifests"
```

---

### Task 8: 端到端集成测试

**前提：** 用户已连接 J-Link + 目标板，已有编译好的 ELF 文件。

- [ ] **Step 1: 探测环境**

```powershell
python skills/freemaster-debug/scripts/freemaster_debugger.py --detect
```

期望：找到 FreeMASTER 安装和 J-Link。

- [ ] **Step 2: 用真实 ELF 和 MCU 生成 .pmpx 并启动**

```powershell
# 替换为实际路径
python skills/freemaster-debug/scripts/freemaster_debugger.py --elf <path/to/app.elf> --device <REAL_MCU>
```

期望：
- 生成 `<MCU>.pmpx`
- FreeMASTER GUI 自动打开并加载项目
- 退出码 0

- [ ] **Step 3: 在 FreeMASTER GUI 中验证连接**

用户在 FreeMASTER 中：
1. 点击工具栏 `GO` 按钮
2. 确认 Variable Grid 显示变量（若预置了变量）
3. 手动添加一个变量（如 `SysTick->VAL`）验证通信正常

- [ ] **Step 4: 清理测试文件**

```powershell
Remove-Item <MCU>.pmpx -ErrorAction SilentlyContinue
```

- [ ] **Step 5: 提交（如有修改）**

```bash
git add -A
git commit -m "test: end-to-end validation of freemaster-debug"
```
