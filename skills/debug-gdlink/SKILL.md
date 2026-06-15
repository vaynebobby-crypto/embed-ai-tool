---
name: debug-gdlink
description: 当需要通过 GD-Link 探针（pyOCD GDB Server）启动或附着 GDB 会话，完成固件下载、在线调试或崩溃现场检查时使用。
---

# GD-Link GDB 调试

## 适用场景

- 用户希望通过 GD-Link 探针调试 Cortex-M 类目标（GD32 及兼容 MCU）。
- 工作区中已有 `ELF` 和 GD-Link 探针。
- 烧录或串口监视流程表明，需要进一步查看断点、停核控制、寄存器或回溯信息。
- 需要在调试前确认 pyOCD GDB Server 和 arm-none-eabi-gdb 环境是否就绪。

## 必要输入

- 一份带符号的 `ELF`，或包含 `artifact_path` 的 `Project Profile`。
- `--device` 可选参数指定目标芯片型号（GD32 系列，pyOCD 可自动探测）。
- 可选调试模式：`download-and-halt`、`attach-only`、`crash-context`。
- 可选的 GDB 可执行文件路径。

## 自动探测

- 默认模式为 `download-and-halt`；只有用户显式要求附着调试或崩溃现场检查时才切换。
- GDB 由脚本自动探测，优先级为：显式用户输入、`Project Profile`、`arm-none-eabi-gdb`、`gdb-multiarch`。
- pyOCD 自动扫描 CMSIS-DAP 探针（GD-Link 即 CMSIS-DAP 设备），无需额外配置。
- 目标 MCU 可通过 pyOCD 自动探测；`--device` 缺失时不会阻塞。
- 做符号级调试必须有 `ELF`。若只有 `HEX` 或 `BIN`，应阻塞并要求提供匹配 `ELF`。

## 执行步骤

1. 先阅读 [references/usage.md](references/usage.md)，确认本次是环境探测，还是执行调试会话。
2. 若不确定环境是否就绪，先运行自带脚本 [scripts/gdlink_debugger.py](scripts/gdlink_debugger.py) 的 `--detect` 模式确认。
3. 根据用户意图选择调试模式：`download-and-halt`（默认）、`attach-only` 或 `crash-context`。
4. 使用 `--elf` 启动调试，可选 `--device` 和 `--port`。
5. 脚本自动启动 pyOCD GDB Server，等待就绪后执行 GDB 批处理。
6. 读取脚本输出的调试结果，重点关注寄存器状态、回溯帧和 Fault 寄存器。

## 失败分流

- 当缺少 pyOCD 或兼容 GDB 时，返回 `environment-missing`。
- 当没有可用的 `ELF` 时，返回 `artifact-missing`。
- 当 pyOCD GDB Server 无法连接目标板时，返回 `connection-failure`。
- 当设备名不被 pyOCD 识别或配置不一致时，返回 `project-config-error`。
- 当会话可以建立，但无法停核、加载或得到可信回溯时，返回 `target-response-abnormal`。
- 当存在多个探针且无法确定目标时，返回 `ambiguous-context`。

## 平台说明

- 已确认 Python 3 + pyOCD 0.44.1 + arm-none-eabi-gdb 环境。
- 默认 GDB 端口为 3333（pyOCD 默认），可通过 `--port` 修改。
- GD-Link 作为 CMSIS-DAP 探针被 pyOCD 自动识别。
- 不带 SWO 功能（GD-Link 不支持）。

## 输出约定

- 输出调试模式、pyOCD gdbserver 命令、GDB 可执行文件、`ELF` 路径和关键观察结论。
- 在 `Project Profile` 中保留 `artifact_path`、`artifact_kind`、`gdb_executable`、`gdlink_device`。
- 当复位后或继续运行后下一步是观察运行行为时，推荐 `serial-monitor`。

## 交接关系

- 当目标恢复运行后，需要继续观察运行期日志时，将成功会话交给 `serial-monitor`。
- 当用户需要 RTOS 线程感知调试时，将会话交给 `rtos-debug`。
