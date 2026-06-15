---
name: flash-gdlink
description: 当需要使用 GD-Link 探针通过 Keil MDK5 烧录固件到 GD32 或其他 Cortex-M 目标板时使用。
---

# GD-Link 烧录 (Keil MDK5)

## 适用场景

- 工作区有 Keil µVision 项目（.uvprojx），目标板通过 GD-Link 连接。
- GD-Link 在 Keil 中配置为 CMSIS-DAP 调试器。
- 需要构建 + 烧录一体化流程。

## 必要输入

- `--project`：Keil .uvprojx 项目文件路径。
- `--target`：构建目标名称（默认 `GD32G553Q_EVAL`）。
- 首次使用需用 `--set-cmsis-dap` 将项目驱动从 J-Link 切换到 CMSIS-DAP。

## 自动探测

- `--detect` 模式检测 Keil MDK5 安装路径和版本。
- 优先查找 `D:\Program Files\ARM\MDK5\UV4\UV4.exe` 和常见安装路径。
- 构建输出自动检查 "0 Error(s)" 判定成功。
- AXF/HEX 产物自动从 .uvprojx 项目配置中定位。

## 执行步骤

1. 若首次使用，运行 `--set-cmsis-dap` 配置项目驱动。
2. 在 Keil GUI 中确认 GD-Link 被识别（Flash → Configure Flash Tools → Debug → CMSIS-DAP → Settings）。
3. 使用 `--project` + `--target` 执行构建和烧录。
4. 可选 `--build-only` 只构建不烧录，`--flash-only` 跳过构建直接烧录。
5. 脚本启动 Keil 调试会话（UMUpdateFlashBeforeDebugging=1），Keil 自动下载固件。
6. 关闭 Keil 后脚本退出。

## 失败分流

- Keil UV4.exe 未找到 → `environment-missing`
- 项目文件不存在 → `artifact-missing`
- 构建失败 → 输出编译错误日志
- GD-Link 未识别 → 提示在 Keil 中检查 CMSIS-DAP 配置

## 平台说明

- 仅 Windows（Keil MDK5 为 Windows 原生）。
- 需要 Keil MDK 5.30+ 及 GigaDevice GD32G5x3 DFP 1.1.0+。
- 脚本通过 subprocess 调用 UV4.exe 命令行。

## 输出约定

- 输出 UV4 构建日志、目标芯片信息、烧录状态。
- 烧录完成后输出固件路径和校验建议。
- 烧录成功后推荐 `debug-gdlink` 进行调试。

## 交接关系

- 需要调试时 → `debug-gdlink`
- 需要串口监视时 → `serial-monitor`
