# GD-Link 烧录 Skill 用法

通过 Keil MDK5 的 UV4.exe 命令行实现构建 + GD-Link 烧录，支持安全的烧录配置预设管理。

## 能力概览

- 检测 Keil MDK5 环境
- 构建 Keil 项目（UV4 -r）
- 通过调试会话自动烧录（UV4 -d）
- **安全烧录配置管理**：读取、预览、切换调试器预设
- **配置隔离**：仅修改烧录相关 XML 字段，不破坏源文件/编译选项

## 烧录配置预设

| 预设名 | 调试器 | DriverSelection | 行为 | 适用场景 |
|--------|--------|-----------------|------|----------|
| `stlink-default` | ST-Link | 4101 | 标准烧录 | 日常 GD32 开发 |
| `jlink-no-reset` | J-Link | 8010 | 烧录后不复位 | 需要保持 MCU 当前状态 |
| `jlink-reset-run` | J-Link | 8010 | 烧录后复位运行 | FreeMASTER 调试、自动化测试 |
| `cmsis-dap` | CMSIS-DAP | 4098 | GD-Link 通用 | GD-Link 探针 |

## 基础用法

```bash
# 探测环境（含可用预设列表）
python skills/flash-gdlink/scripts/gdlink_flasher.py --detect

# 查看当前工程的烧录配置
python skills/flash-gdlink/scripts/gdlink_flasher.py \
  --project path/to/project.uvprojx --read-flash-config

# 预览预设变更（安全，不写入）
python skills/flash-gdlink/scripts/gdlink_flasher.py \
  --project path/to/project.uvprojx --set-flash-preset jlink-reset-run --dry-run

# 应用烧录预设
python skills/flash-gdlink/scripts/gdlink_flasher.py \
  --project path/to/project.uvprojx --set-flash-preset jlink-reset-run

# 只构建
python skills/flash-gdlink/scripts/gdlink_flasher.py \
  --project path/to/project.uvprojx --target "GD32F50X" --build-only

# 完整构建 + 烧录
python skills/flash-gdlink/scripts/gdlink_flasher.py \
  --project path/to/project.uvprojx --target "GD32F50X"

# 跳过构建，直接烧录（需已有产物）
python skills/flash-gdlink/scripts/gdlink_flasher.py \
  --project path/to/project.uvprojx --target "GD32F50X" --flash-only
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
| `--read-flash-config` | 读取并显示当前烧录配置 |
| `--set-flash-preset PRESET` | 安全应用烧录配置预设 |
| `--dry-run` | 预览 --set-flash-preset 的变更（不写入） |
| `--set-cmsis-dap` | [已废弃] 请用 `--set-flash-preset cmsis-dap` |
| `--detect` | 探测 Keil 安装环境 |
| `-v` / `--verbose` | 输出详细构建日志 |

## 典型工作流

### FreeMASTER 调试流程

```bash
# 1. 先构建（可选）
python skills/build-keil/scripts/keil_builder.py --project app.uvprojx --target GD32F50X

# 2. 切换到 J-Link 预设
python skills/flash-gdlink/scripts/gdlink_flasher.py \
  --project app.uvprojx --set-flash-preset jlink-reset-run

# 3. 烧录固件
python skills/flash-gdlink/scripts/gdlink_flasher.py \
  --project app.uvprojx --target GD32F50X --flash-only

# 4. 启动 FreeMASTER 监控
python skills/freemaster-debug/scripts/freemaster_debugger.py \
  --elf output/Project.axf --device GD32F503RE --vars var1,var2

# 5. 调试完毕后切回 ST-Link
python skills/flash-gdlink/scripts/gdlink_flasher.py \
  --project app.uvprojx --set-flash-preset stlink-default
```

### 模板工程初始化

从三个模板中选择合适的烧录配置创建新工程：

```bash
# 选择模板（以 J-Link Reset and Run 为例）
copy "Template\Keil_project\Project.uvprojx" "MyProject\MyProject.uvprojx"

# 验证配置
python skills/flash-gdlink/scripts/gdlink_flasher.py \
  --project MyProject\MyProject.uvprojx --read-flash-config

# 如需切换到其他预设
python skills/flash-gdlink/scripts/gdlink_flasher.py \
  --project MyProject\MyProject.uvprojx --set-flash-preset stlink-default
```

## 前置条件

1. **Keil MDK 5.30+** 已安装
2. **对应的 MCU DFP** 已安装（如 GigaDevice.GD32F50x_DFP）
3. 调试器探针已正确连接目标板
4. 在 Keil GUI 中验证调试器识别（Flash → Configure Flash Tools → Debug）

## 返回码

- `0`：构建 + 烧录成功，或配置操作成功
- `1`：构建失败、Keil 未找到、烧录异常、或配置错误
