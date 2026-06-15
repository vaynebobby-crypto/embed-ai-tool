---
name: flash-gdlink
description: 当需要使用 GigaDevice GD-Link 探针烧录固件到 GD32 或其他 Cortex-M 目标板时使用。
---

# GD-Link 烧录

## 适用场景

- 工作区已有可用固件产物，且目标板连接了 GD-Link 探针。
- 需要使用 GigaDevice 官方 GD_Link_CLI 进行烧录和校验。
- 需要扫描工作区中的 `GDConfig.ini` 配置文件或 `ToolSetting.ini` 设置。

## 必要输入

- 固件产物路径，或包含 `artifact_path` 的 `Project Profile`。
- `--device` 参数指定目标芯片型号（如 `GD32F303RET6`），GD_Link_CLI 要求指定。
- 可选的接口类型（SWD 或 JTAG，默认 SWD）。
- 若产物为 BIN，还需要 `--base-address` 烧录基地址。

## 自动探测

- 按 `ELF > HEX > BIN` 选择固件产物。
- 脚本自动查找 `GD_Link_CLI.exe`，按 Project Profile 配置、常见安装路径、用户提示的顺序搜索。
- 首次找到后自动写入 Project Profile，后续无需重复搜索。
- 读取同目录下 `GDConfig.ini` 获取 SWD/JTAG 接口和连接速度参数。
- 不会猜测设备名；当 `--device` 缺失时阻塞并返回 `ambiguous-context`。

## 执行步骤

1. 先阅读 [references/usage.md](references/usage.md)，确认本次是环境探测还是执行烧录。
2. 若不确定 GD-Link 环境状态，先运行自带脚本 [scripts/gdlink_flasher.py](scripts/gdlink_flasher.py) 的 `--detect` 模式。
3. 使用 `--artifact` + `--device` 执行烧录，可选 `--interface` 和 `--speed`。
4. 对 BIN 文件，必须同时提供 `--base-address`。
5. 读取脚本输出的烧录结果报告，重点关注校验状态和失败分类。

## 失败分流

- 当 `GD_Link_CLI.exe` 不可用时，返回 `environment-missing`。
- 当无法安全解析到产物，或 `BIN` 缺少烧录基地址时，返回 `artifact-missing`。
- 当 GD-Link 无法发现目标时，返回 `connection-failure`。
- 当 `GDConfig.ini` 配置无效或设备名不被 GD-Link 识别时，返回 `project-config-error`。
- 当烧录开始但校验或复位失败时，返回 `target-response-abnormal`。
- 当 `--device` 缺失且无法从工作区推断时，返回 `ambiguous-context`。

## 平台说明

- GD_Link_CLI.exe 为 Windows 原生可执行文件，不支持 Linux/macOS。
- 自带脚本通过 subprocess stdin 管道与交互式 CLI 通信。
- 首次使用时需要探测 GD_Link_CLI.exe 路径，写入 Project Profile 后复用。

## 输出约定

- 输出 GD_Link_CLI 命令、设备名、接口类型、产物路径和校验结果。
- 在 `Project Profile` 中保留或更新 `artifact_path`、`artifact_kind`、`gdlink_device`、`gdlink_cli_path`。
- 烧录成功后推荐 `serial-monitor` 或 `debug-gdlink`。

## 交接关系

- 当下一步要看运行日志时，将成功烧录结果交给 `serial-monitor`。
- 当用户需要 GDB 调试时，将结果交给 `debug-gdlink`。
