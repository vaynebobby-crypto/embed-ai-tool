---
name: stm32-hal-development
description: STM32 HAL 库开发指导与最佳实践，适用于 CubeMX 生成的 HAL 项目。
---

# STM32 HAL 开发

## 适用场景

- 基于 STM32CubeMX 生成的 HAL 库项目。
- 需要外设配置、BSP 驱动结构、中断安全代码编写指导。
- 需要 HAL API 快速参考和故障排查。

## 必要输入

- CubeMX 生成的 HAL 工程（含 `.ioc` 文件）。
- 目标 STM32 芯片型号。

## 自动探测

- 自动识别 CubeMX 工程结构（`.ioc` + `Src/` + `Inc/`）。
- 检测 `USER CODE` 区域边界，确保自定义代码放入正确位置。
- 根据目标芯片系列匹配对应的 HAL 驱动版本和 CMSIS 包。

## 执行步骤

1. 先阅读 [references/core-guidelines.md](references/core-guidelines.md) 了解整体规范。
2. 在 CubeMX 中配置外设，重新生成代码。
3. 在 `USER CODE` 区域内添加应用层或 BSP 逻辑。
4. 按需查阅补充参考：
   - [references/peripheral-driver-guide.md](references/peripheral-driver-guide.md) — 传感器和总线驱动
   - [references/hal-quick-reference.md](references/hal-quick-reference.md) — HAL API 速查
   - [references/troubleshooting-guide.md](references/troubleshooting-guide.md) — 故障分析
   - [references/usage-examples.md](references/usage-examples.md) — 实现模式
5. 新建 BSP 模块时复用 [assets/bsp-template.c](assets/bsp-template.c) 和 [assets/bsp-template.h](assets/bsp-template.h)。

## 失败分流

- `regeneration-overwrite`：自定义代码未放在 `USER CODE` 区域内，被 CubeMX 重新生成覆盖。
- `hal-config-error`：HAL 配置与芯片型号不匹配。
- `interrupt-conflict`：中断优先级或抢占配置不当导致异常。
- `peripheral-init-failure`：外设初始化失败，检查时钟和引脚配置。

## 平台说明

- 跨平台（Windows / Linux / macOS）。
- CubeMX 原生支持 Windows / Linux / macOS。
- Keil MDK 编译仅 Windows；CMake / GCC 编译跨平台。

## 输出约定

- 提供符合 HAL 规范的可编译代码片段。
- 标注哪些代码应放入 `USER CODE` 区域。
- 指出需要 CubeMX 重新生成时的不兼容变更。

## 交接关系

- 从 `peripheral-driver` 接收外设驱动适配需求。
- 产出 HAL 代码后交给 `build-keil` / `build-cmake` / `build-platformio` 编译。
- 调试问题交给 `debug-gdb-openocd` / `debug-jlink` / `rtos-debug`。
