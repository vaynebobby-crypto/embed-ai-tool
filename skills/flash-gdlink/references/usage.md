# GD-Link 烧录 Skill 用法

通过 Keil MDK5 的 UV4.exe 命令行实现构建 + GD-Link 烧录。

## 能力概览

- 检测 Keil MDK5 环境
- 构建 Keil 项目（UV4 -r）
- 通过 CMSIS-DAP 驱动自动烧录（UV4 -d）
- 首次使用自动配置 CMSIS-DAP 驱动

## 基础用法

```bash
# 探测环境
python3 skills/flash-gdlink/scripts/gdlink_flasher.py --detect

# 首次使用：配置项目使用 CMSIS-DAP 驱动
python3 skills/flash-gdlink/scripts/gdlink_flasher.py \
  --project path/to/project.uvprojx --set-cmsis-dap

# 只构建
python3 skills/flash-gdlink/scripts/gdlink_flasher.py \
  --project path/to/project.uvprojx --target "GD32G553Q_EVAL" --build-only

# 完整构建 + 烧录
python3 skills/flash-gdlink/scripts/gdlink_flasher.py \
  --project path/to/project.uvprojx --target "GD32G553Q_EVAL"

# 跳过构建，直接烧录
python3 skills/flash-gdlink/scripts/gdlink_flasher.py \
  --project path/to/project.uvprojx --target "GD32G553Q_EVAL" --flash-only
```

## 烧录流程

1. **构建**：`UV4.exe -r project.uvprojx -t target -j0 -o build.log`
2. 检查构建日志中 "0 Error(s)" 判定成功
3. **烧录**：`UV4.exe -d project.uvprojx -t target` 启动调试会话
4. Keil 自动下载固件（`UpdateFlashBeforeDebugging=1`）
5. 关闭 Keil 完成烧录

## 参数说明

| 参数 | 说明 |
| --- | --- |
| `--project` / `-p` | Keil .uvprojx 项目文件路径 |
| `--target` / `-t` | 构建目标名称（默认 GD32G553Q_EVAL） |
| `--build-only` | 仅构建，不启动烧录 |
| `--flash-only` | 跳过构建，直接烧录（需已有产物） |
| `--set-cmsis-dap` | 将项目调试驱动切换为 CMSIS-DAP |
| `--detect` | 探测 Keil 安装环境 |
| `-v` / `--verbose` | 输出详细构建日志 |

## 前置条件

1. **Keil MDK 5.30+** 已安装
2. **GigaDevice GD32G5x3 DFP 1.1.0+** 已安装
3. GD-Link 在 Keil 中识别为 CMSIS-DAP（Flash → Configure Flash Tools → Debug 验证）
4. 项目 `DriverSelection` 设置为 4098 (CMSIS-DAP)
5. 项目 `UpdateFlashBeforeDebugging` 设置为 1

## 返回码

- `0`：构建 + 烧录成功
- `1`：构建失败、Keil 未找到、或烧录异常
