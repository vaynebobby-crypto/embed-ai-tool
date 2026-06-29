---
name: flash-gdlink
description: 当需要使用 GD-Link 探针通过 Keil MDK5 烧录固件到 GD32 或其他 Cortex-M 目标板时使用。也用于管理 Keil 工程的烧录/调试器配置预设（ST-Link / J-Link / CMSIS-DAP）。
---

# GD-Link / Keil 烧录配置管理

## 适用场景

- 工作区有 Keil µVision 项目（.uvprojx），目标板通过 GD-Link 连接。
- 需要在 ST-Link、J-Link、CMSIS-DAP 之间切换调试器而保留其他工程设置不变。
- 需要安全的烧录配置变更（不破坏源文件、编译选项、include 路径等）。
- GD-Link 在 Keil 中配置为 CMSIS-DAP 调试器。
- 需要构建 + 烧录一体化流程。

## 三大烧录配置预设

本 skill 管理三种最常见的 GD32 开发烧录配置，对应 `Template\Keil_project\` 下的三个模板：

| 预设名 | 调试器 | 行为 | 对应模板 |
|--------|--------|------|----------|
| `stlink-default` | ST-Link (4101) | 标准烧录 | `Project.uvprojx.bankup2` |
| `jlink-no-reset` | J-Link (8010) | 烧录后不复位 MCU | `Project.uvprojx.bankup` |
| `jlink-reset-run` | J-Link (8010) | 烧录后复位并运行 | `Project.uvprojx` |
| `cmsis-dap` | CMSIS-DAP (4098) | GD-Link 标准烧录 | — |

**重要**：烧录配置变更使用 `shared/keil_flash_config.py` 的安全 XML 操作，**仅修改 DriverSelection 等烧录相关字段**，不会影响工程的源文件列表、编译选项、include 路径等。

## 必要输入

- `--project`：Keil .uvprojx 项目文件路径。
- `--target`：构建目标名称（默认 `GD32G553Q_EVAL`）。
- 首次使用或切换调试器时用 `--set-flash-preset <预设名>` 安全配置。

## 自动探测

- `--detect` 模式检测 Keil MDK5 安装路径和版本。
- `--read-flash-config` 读取当前工程的烧录配置（调试器类型、芯片型号等）。
- 优先查找 `D:\Program Files\ARM\MDK5\UV4\UV4.exe` 和常见安装路径。
- 构建输出自动检查 "0 Error(s)" 判定成功。

## 执行步骤

### 场景 A：首次配置工程烧录预设

```bash
# 查看当前烧录配置
python skills/flash-gdlink/scripts/gdlink_flasher.py \
  --project <工程文件> --read-flash-config

# 预览变更（不写入）
python skills/flash-gdlink/scripts/gdlink_flasher.py \
  --project <工程文件> --set-flash-preset jlink-reset-run --dry-run

# 实际应用预设
python skills/flash-gdlink/scripts/gdlink_flasher.py \
  --project <工程文件> --set-flash-preset jlink-reset-run
```

### 场景 B：构建 + 烧录

```bash
# 完整构建 + 烧录
python skills/flash-gdlink/scripts/gdlink_flasher.py \
  --project <工程文件> --target "GD32F50X"

# 仅构建
python skills/flash-gdlink/scripts/gdlink_flasher.py \
  --project <工程文件> --target "GD32F50X" --build-only

# 跳过构建直接烧录
python skills/flash-gdlink/scripts/gdlink_flasher.py \
  --project <工程文件> --target "GD32F50X" --flash-only
```

### 场景 C：烧录配置切换（J-Link ↔ ST-Link）

```bash
# 切换到 J-Link + Reset and Run（用于 FreeMASTER 调试）
python skills/flash-gdlink/scripts/gdlink_flasher.py \
  --project <工程文件> --set-flash-preset jlink-reset-run

# ... 使用 FreeMASTER 调试 ...

# 切回 ST-Link（日常开发）
python skills/flash-gdlink/scripts/gdlink_flasher.py \
  --project <工程文件> --set-flash-preset stlink-default
```

## 失败分流

- Keil UV4.exe 未找到 → `environment-missing`
- 项目文件不存在 → `artifact-missing`
- 构建失败 → 输出编译错误日志
- GD-Link 未识别 → 提示在 Keil 中检查 CMSIS-DAP 配置
- 预设名无效 → 列出可用预设

## 平台说明

- 仅 Windows（Keil MDK5 为 Windows 原生）。
- 需要 Keil MDK 5.30+ 及对应的 MCU DFP。
- 脚本通过 subprocess 调用 UV4.exe 命令行。
- 烧录配置变更通过 XML DOM 安全操作，非字符串替换。

## 输出约定

- 输出 UV4 构建日志、目标芯片信息、烧录状态。
- `--set-flash-preset` 输出变更详情（修改了哪些字段，从什么值变为什么值）。
- 烧录完成后输出固件路径和校验建议。
- 烧录成功后推荐 `debug-gdlink` 进行调试或 `freemaster-debug` 进行在线变量监控。

## 交接关系

- 需要调试时 → `debug-gdlink`
- 需要 FreeMASTER 在线监控时 → `freemaster-debug`（需要先切换到 J-Link 预设）
- 需要串口监视时 → `serial-monitor`
- 上游构建 → `build-keil`
