# GD-Link 调试 Skill 用法

通过 Keil MDK5 的 UV4.exe 启动调试会话进行 GD-Link 在线调试。

## 能力概览

- 检测 Keil MDK5 环境
- 自动定位 `.axf` 符号文件
- 三种调试模式：下载并停核、仅附着、崩溃现场检查
- 生成 debug init .ini 自动化脚本

## 基础用法

```bash
# 探测调试环境
python3 skills/debug-gdlink/scripts/gdlink_debugger.py --detect

# 下载并停核调试（默认模式）
python3 skills/debug-gdlink/scripts/gdlink_debugger.py \
  --project path/to/project.uvprojx --target "GD32G553Q_EVAL"

# 附着调试（不下载不复位）
python3 skills/debug-gdlink/scripts/gdlink_debugger.py \
  --project path/to/project.uvprojx --target "GD32G553Q_EVAL" --mode attach-only

# 崩溃现场排查
python3 skills/debug-gdlink/scripts/gdlink_debugger.py \
  --project path/to/project.uvprojx --target "GD32G553Q_EVAL" --mode crash-context
```

## 调试模式说明

### download-and-halt（默认）

通过 debug init .ini 执行 `LOAD + RESET + g, main`，将固件下载到目标，复位后停在 `main()`。适
合常规开发调试。

### attach-only

不复位、不下载，直接附着到当前运行状态。适合观察运行中的程序。

### crash-context

通过 debug init .ini 执行 `LOAD + RESET`，加载后停核。用户可在 Keil 的 Peripherals → Core
Peripherals → Fault Reports 中查看 HardFault 寄存器（CFSR/HFSR/MMFAR/BFAR）。

## Debug Init 脚本

脚本会在项目目录生成 `_gdlink_debug.ini` 文件，需要在 Keil 中手动设置为初始化脚本：

1. 打开项目 → Flash → Configure Flash Tools → Debug
2. 在 "Initialization File" 中加载 `_gdlink_debug.ini`

`download-and-halt` 模式生成的 .ini 内容示例：

```ini
// Auto-generated debug init script (mode: download-and-halt)
LOAD .\Objects\Project.axf INCREMENTAL
RESET
g, main
```

## 参数说明

| 参数 | 说明 |
| --- | --- |
| `--project` / `-p` | Keil .uvprojx 项目文件路径 |
| `--target` / `-t` | 构建目标名称（默认 GD32G553Q_EVAL） |
| `--mode` / `-m` | 调试模式：`download-and-halt`、`attach-only`、`crash-context` |
| `--elf` | .axf 文件路径（默认自动检测） |
| `--detect` | 探测调试环境（Keil + 项目） |
| `-v` / `--verbose` | 输出详细日志 |

## 与 debug-jlink 的区别

| 特性 | debug-gdlink | debug-jlink |
|------|-------------|-------------|
| 调试后端 | Keil UV4 + CMSIS-DAP | JLinkGDBServer + GDB |
| 默认工具 | UV4.exe | JLinkGDBServerCL.exe |
| GD-Link 支持 | ✅ Keil 原生驱动 | ❌（J-Link 协议不兼容） |
| SWO 支持 | ❌ 不支持 | ✅ 原生 |
| 自动化方式 | Keil debug init .ini | GDB 批处理命令 |
| 平台 | 仅 Windows | 跨平台 |

## 前置条件

1. **Keil MDK 5.30+** 已安装
2. **GigaDevice GD32G5x3 DFP 1.1.0+** 已安装
3. GD-Link 在 Keil 中识别为 CMSIS-DAP
4. 项目已构建，`.axf` 产物存在

## 返回码

- `0`：调试会话正常结束
- `1`：参数非法、依赖缺失、连接失败、调试失败
