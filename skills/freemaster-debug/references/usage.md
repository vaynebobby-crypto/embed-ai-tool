# FreeMASTER 调试工具 CLI 参考

## 概述

`freemaster_debugger.py` 是 FreeMASTER 调试的主入口脚本。它编排环境探测、.pmpx 生成和 GUI 启动。

## 快速开始

```powershell
# 1. 探测 FreeMASTER 环境
python skills/freemaster-debug/scripts/freemaster_debugger.py --detect

# 2. 生成 .pmpx 并启动 FreeMASTER（需要 ELF + MCU 型号）
python skills/freemaster-debug/scripts/freemaster_debugger.py --elf build/app.elf --device GD32F450IK

# 3. 带预置变量启动（变量自动注入 Variable Grid）
python skills/freemaster-debug/scripts/freemaster_debugger.py --elf build/app.elf --device GD32F450IK --vars adc_value,pid_output

# 4. 配置 Scope/Oscilloscope（示波器预配置曲线）
python skills/freemaster-debug/scripts/freemaster_debugger.py --elf build/app.elf --device GD32F450IK --vars adc_value,pid_output,temperature --scope-vars adc_value,pid_output --scope-time-per-div 0.01 --scope-time-total 0.1

# 5. 指定 Recorder 数据保存目录
python skills/freemaster-debug/scripts/freemaster_debugger.py --elf build/app.elf --device GD32F450IK --vars adc_value --recorder-dir D:\Data\logs

# 6. 仅生成 .pmpx，不启动 GUI
python skills/freemaster-debug/scripts/freemaster_debugger.py --elf build/app.elf --device GD32F450IK --mode generate
```

## 主控脚本参数

| 参数 | 必须 | 默认值 | 说明 |
|------|------|--------|------|
| `--detect` | 否 | — | 仅探测 FreeMASTER 环境，输出安装路径和版本 |
| `--elf` | 是* | — | 带符号的 ELF 固件文件路径 |
| `--device` | 是* | — | J-Link 目标设备名（如 `GD32F450IK`、`STM32F407VG`） |
| `--mode` | 否 | `start` | `start`（生成+启动）或 `generate`（仅生成） |
| `--vars` | 否 | — | 预置变量名，逗号分隔（如 `adc_value,pid_output`），自动注入 .pmpx 的 Variable Grid |
| `--scope-vars` | 否 | — | Scope/Oscilloscope 变量名，逗号分隔。自动包含在 `--vars` 中，并在 .pmpx 中预配置示波器曲线 |
| `--scope-time-per-div` | 否 | `0.01` | 示波器每格时间，单位 s（默认 0.01 = 10ms/div） |
| `--scope-time-total` | 否 | `0.1` | 示波器时间窗口，单位 s（默认 0.1 = 100ms） |
| `--sample-rate` | 否 | `1000` | Recorder 采样率，单位 Hz |
| `--jlink-speed` | 否 | `4000` | J-Link SWD 通信速度，单位 kHz |
| `--recorder-dir` | 否 | — | Recorder 数据保存目录（写入 .pmpx 的 `data_capture_dir`） |
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
| `--vars` | 否 | 变量名，逗号分隔（注入 CVariable 对象到 .pmpx） |
| `--scope-vars` | 否 | Scope 变量名，逗号分隔（预配置示波器曲线，自动包含在 --vars 中） |
| `--scope-time-per-div` | 否 | 示波器每格时间 s（默认 0.01 = 10ms/div） |
| `--scope-time-total` | 否 | 示波器时间窗口 s（默认 0.1 = 100ms） |
| `--sample-rate` | 否 | 采样率 Hz（默认 1000） |
| `--jlink-speed` | 否 | J-Link 速度 kHz（默认 4000） |
| `--recorder-dir` | 否 | Recorder 数据保存目录（写入 data_capture_dir） |
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
