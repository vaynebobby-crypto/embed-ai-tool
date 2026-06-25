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
