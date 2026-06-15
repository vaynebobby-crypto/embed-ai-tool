# GD-Link 烧录 Skill 用法

这个 skill 自带了一个可执行脚本 [scripts/gdlink_flasher.py](../scripts/gdlink_flasher.py)，适合在需要探测 GD-Link 探针、执行烧录时直接调用。

## 能力概览

- 检测 GD_Link_CLI.exe 是否可用并获取版本信息
- 列出已连接的 GD-Link 设备
- 扫描工作区中的 `GDConfig.ini` 配置文件
- 通过 stdin 管道驱动 GD_Link_CLI 交互式命令行执行烧录
- 支持 ELF/HEX/BIN 烧录
- 输出结构化的烧录结果报告

## 基础用法

```bash
# 探测 GD-Link 环境
python3 skills/flash-gdlink/scripts/gdlink_flasher.py --detect

# 烧录 ELF
python3 skills/flash-gdlink/scripts/gdlink_flasher.py \
  --artifact /path/to/firmware.elf \
  --device GD32F303RET6

# 烧录 BIN（需要指定基地址）
python3 skills/flash-gdlink/scripts/gdlink_flasher.py \
  --artifact /path/to/firmware.bin \
  --device GD32F303RET6 \
  --base-address 0x08000000

# 烧录 HEX
python3 skills/flash-gdlink/scripts/gdlink_flasher.py \
  --artifact /path/to/firmware.hex \
  --device GD32F303RET6

# 使用 JTAG 接口
python3 skills/flash-gdlink/scripts/gdlink_flasher.py \
  --artifact build/app.elf \
  --device GD32F303RET6 \
  --interface JTAG
```

## 常见模式

### 1. 环境探测

```bash
python3 skills/flash-gdlink/scripts/gdlink_flasher.py --detect
```

输出 GD_Link_CLI 版本信息。

### 2. SWD 模式烧录（默认）

```bash
python3 skills/flash-gdlink/scripts/gdlink_flasher.py \
  --artifact build/debug/app.elf \
  --device GD32F303RET6
```

### 3. BIN 烧录（需指定基地址）

```bash
python3 skills/flash-gdlink/scripts/gdlink_flasher.py \
  --artifact build/fw.bin \
  --device GD32F303RET6 \
  --base-address 0x08000000
```

## 参数说明

| 参数 | 说明 |
| --- | --- |
| `--detect` | 探测 GD-Link 环境 |
| `--artifact` | 固件产物路径（ELF、HEX 或 BIN） |
| `--device` | 目标芯片型号（如 GD32F303RET6） |
| `--interface` | 调试接口：`SWD`（默认）或 `JTAG` |
| `--speed` | 连接速度 kHz（默认 10000） |
| `--base-address` | BIN 文件的烧录基地址（十六进制） |
| `--save-config` | 探测成功后保存 GD_Link_CLI 路径到配置 |
| `-v`, `--verbose` | 输出详细日志 |

## GD_Link_CLI.exe 查找顺序

1. 配置文件（`get_tool_path("gdlink-cli")`）
2. `GD_Link_CLI.exe`（PATH 中）
3. 常见安装路径：用户指定的已知路径
4. 提示用户手动输入路径

## GD-Link 与 J-Link 对比

| 特性 | GD-Link (本 skill) | J-Link (flash-jlink) |
|------|-------------------|----------------------|
| 目标芯片 | GD32 全系列，兼容 Cortex-M | 广泛（需许可） |
| RTT 日志 | ❌ 不支持 | ✅ 原生支持 |
| 烧录方式 | GD_Link_CLI 交互式命令行 | J-Link Commander 脚本 |
| 商业许可 | 免费 | 需要（教育版免费） |
| 跨平台 | 仅 Windows | 跨平台 |

## 返回码

- `0`：操作成功
- `1`：参数非法、依赖缺失、探针连接失败、烧录失败
