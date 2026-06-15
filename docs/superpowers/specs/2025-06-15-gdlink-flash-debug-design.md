# GD-Link Flash & Debug Skills Design

**Date**: 2025-06-15
**Status**: Approved

## 概述

新增两个技能，对标现有 `flash-jlink` / `debug-jlink`，为 GD-Link 探针提供烧录和调试能力。

## flash-gdlink

### 工具链
- 核心: `GD_Link_CLI.exe`（GigaDevice 官方 CLI，交互式 REPL）
- 配置: `GDConfig.ini`（同目录下，含 SWD/JTAG、速度等）

### 自动探测
1. 查 Project Profile 中 `gdlink_cli_path`
2. 无记录则搜索: D:\ → C:\ 下的 `GD_Link_CLI.exe`
3. 找不到则询问用户指定路径
4. 找到后写入 Project Profile
5. 读取同目录 `GDConfig.ini` 获取连接参数

### 执行步骤
1. 探测 `GD_Link_CLI.exe` 路径
2. 确认 `--device`（GD32 型号）和 `--artifact`（固件）
3. 生成命令序列，通过 stdin 管道送入交互式 CLI
4. 执行: erase → load <file> <base_addr> → r
5. 报告烧录结果

### 失败分流
- `environment-missing`: CLI 未找到
- `artifact-missing`: 固件不存在
- `connection-failure`: GD-Link 未连接/未识别 MCU
- `target-response-abnormal`: 校验失败

### 交接
- 烧录成功后 → serial-monitor
- RTT 日志 → 不支持（GD-Link 无 RTT）
- 调试 → debug-gdlink

## debug-gdlink

### 工具链
- GDB Server: `pyocd gdbserver`（已安装 v0.44.1），GD-Link 作为 CMSIS-DAP 自动识别
- GDB 客户端: `arm-none-eabi-gdb`（已安装）

### 自动探测
1. 确认 pyOCD 可用
2. 确认 arm-none-eabi-gdb 可用
3. pyOCD 自动扫描 CMSIS-DAP 探针
4. 目标 MCU 由 pyOCD 自动探测或从 Project Profile 读取

### 三种调试模式
| 模式 | 行为 |
|------|------|
| `download-and-halt` | 烧录 ELF → 复位 → 暂停等待交互 |
| `attach-only` | 不烧录，附着运行中目标 |
| `crash-context` | 暂停 → 读寄存器/回溯/Fault 寄存器 |

### 执行步骤
1. 探测 pyOCD + GDB
2. 启动 `pyocd gdbserver -t <target> -p 3333`
3. 等待 GDB 端口就绪
4. 按模式生成 GDB 脚本
5. 执行 `arm-none-eabi-gdb` 批处理
6. 收集并报告

### 失败分流
同 flash-gdlink，增加 `environment-missing` 覆盖 pyOCD/GDB 缺失。

### 交接
- 恢复执行后 → serial-monitor
- RTOS 线程调试 → rtos-debug

## 文件结构
每个 skill 遵循仓库规范:
```
skills/flash-gdlink/
  SKILL.md
  scripts/gdlink_flasher.py
  references/usage.md
  agents/openai.yaml

skills/debug-gdlink/
  SKILL.md
  scripts/gdlink_debugger.py
  references/usage.md
  agents/openai.yaml
```

## 关键设计决策
- GD_Link_CLI 是交互式工具，脚本通过 stdin 管道发送命令序列
- 调试使用 pyOCD 而非 OpenOCD（pyOCD 已安装，原生支持 CMSIS-DAP）
- 路径持久化到 Project Profile，首次查找后免重复搜索
- pyOCD gdbserver 端口默认 3333
