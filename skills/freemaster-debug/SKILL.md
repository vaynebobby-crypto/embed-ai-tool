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
- 可选：要监控的变量名列表（`--vars`），自动注入到 .pmpx Variable Grid。
- 可选：要预配置到 Scope/Oscilloscope 的变量名列表（`--scope-vars`），自动包含在 `--vars` 中。
- 可选：Recorder 数据保存目录（`--recorder-dir`），自动写入 .pmpx。
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
5. 根据任务需求确定变量列表和示波器变量，调用生成器：
   - 基础用法：`freemaster_debugger.py --elf <path> --device <name> --vars var1,var2`
   - 配置示波器：添加 `--scope-vars var1,var2 --scope-time-per-div 0.01 --scope-time-total 0.1`
   - 配置保存地址：添加 `--recorder-dir D:\Data\logs`
6. 脚本自动生成 .pmpx（含变量注入、Scope 预配置、Recorder 保存路径）并启动 FreeMASTER。
7. 在 FreeMASTER GUI 中：
   - 点击 `GO` 按钮连接目标
   - Variable Grid 中已预置指定变量，实时值自动更新
   - Scope 中已预配置示波器曲线（若指定 `--scope-vars`）
   - 使用 Recorder 记录数据到指定目录（若指定 `--recorder-dir`）
8. 读取脚本输出的结果报告，确认连接状态。

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

- 输出执行模式、FreeMASTER 路径、ELF 路径、.pmpx 路径、预置变量数量和 Scope 变量数量。
- 状态：`success`（.pmpx 生成且 FreeMASTER 已启动）、`partial_success`（.pmpx 已生成但变量为空或启动异常）、`blocked`（关键信息缺失）、`failure`（生成失败）。
- 在 `Project Profile` 中保留 `artifact_path`、`target_mcu`、`jlink_device`。
- 成功启动后，Variable Grid 已预置变量，Scope 已预配置曲线（若指定），用户可直接连接目标开始监控。

## 交接关系

- 当需要先构建 ELF 时，上游交给 `build-keil` / `build-cmake` / `build-iar` 等构建 skill。
- 当需要先烧录固件到目标时，上游交给 `flash-jlink`。
- 当 ELF 缺失需要 debug 会话先做 download-and-halt 时，上游交给 `debug-jlink`。
- 当需要同时观察串口日志时，并行交给 `serial-monitor`。
- 当 FreeMASTER 记录的 Recorder 数据需要离线分析时，下游交给 `memory-analysis`。
- 当需要 RTOS 任务级监控时，下游交给 `rtos-debug`。
