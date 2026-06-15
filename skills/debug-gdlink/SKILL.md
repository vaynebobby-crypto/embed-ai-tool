---
name: debug-gdlink
description: 当需要通过 GD-Link 探针借助 Keil MDK5 调试会话进行固件下载、在线调试或崩溃现场检查时使用。
---

# GD-Link 调试 (Keil MDK5)

## 适用场景

- 用户希望通过 GD-Link 探针调试 Cortex-M 类目标（GD32 及兼容 MCU）。
- 工作区中有 Keil µVision 项目（.uvprojx）和 `.axf` 产物。
- GD-Link 在 Keil 中配置为 CMSIS-DAP 调试器。
- 烧录或串口监视流程表明，需要进一步查看断点、停核控制、寄存器或回溯信息。

## 必要输入

- `--project`：Keil .uvprojx 项目文件路径。
- `--target`：构建目标名称（默认 `GD32G553Q_EVAL`）。
- `--mode` 可选调试模式：`download-and-halt`、`attach-only`、`crash-context`。
- 可选的 `--elf` 路径（默认从项目配置自动检测）。

## 自动探测

- `--detect` 模式检测 Keil MDK5 安装路径和版本。
- `.axf` 产物从 .uvprojx 项目配置中自动定位。
- 优先查找 `D:\Program Files\ARM\MDK5\UV4\UV4.exe` 和常见安装路径。

## 执行步骤

1. 先阅读 [references/usage.md](references/usage.md)，确认本次是环境探测，还是执行调试会话。
2. 若不确定环境是否就绪，先运行 `--detect` 确认。
3. 根据用户意图选择调试模式：`download-and-halt`（默认）、`attach-only` 或 `crash-context`。
4. 脚本生成 debug init .ini 脚本，启动 Keil UV4 调试会话。
5. 用户可在 Keil GUI 中进行断点、单步、寄存器查看等交互式调试。
6. 关闭 Keil 后脚本退出。

## 失败分流

- Keil UV4.exe 未找到 → `environment-missing`
- 项目文件不存在或 `.axf` 为空 → `artifact-missing`
- GD-Link 未识别 → 提示在 Keil 中检查 CMSIS-DAP 配置
- 当会话可以建立，但无法停核、加载或得到可信回溯时 → `target-response-abnormal`

## 平台说明

- 仅 Windows（Keil MDK5 为 Windows 原生）。
- 需要 Keil MDK 5.30+ 及 GigaDevice GD32G5x3 DFP 1.1.0+。
- 脚本通过 subprocess 调用 `UV4.exe -d` 启动调试会话。
- 不带 SWO 功能（GD-Link 不支持）。

## 输出约定

- 输出调试模式、Keil UV4 路径、项目路径和 `.axf` 位置。
- 输出生成的 debug init .ini 内容，提示在 Keil 项目选项 Debug 标签中设置。
- 当复位后或继续运行后下一步是观察运行行为时，推荐 `serial-monitor`。

## 交接关系

- 烧录后需要调试时 → 从 `flash-gdlink` 直接调用。
- 当目标恢复运行后，需要继续观察运行期日志时 → `serial-monitor`。
- 当用户需要 RTOS 线程感知调试时 → `rtos-debug`。
