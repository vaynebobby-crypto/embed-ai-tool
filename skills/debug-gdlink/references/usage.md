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
| SWO 支持 | ❌ 不支持 | ✅ 原生 |
| 探针识别 | CMSIS-DAP 自动 | SEGGER 专用 |
| 配置复杂度 | 低（即插即用） | 低（仅需设备名） |

## 返回码

- `0`：调试会话成功完成
- `1`：参数非法、依赖缺失、连接失败、调试失败
