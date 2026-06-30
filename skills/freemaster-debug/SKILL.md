---
name: freemaster-debug
description: 当需要通过 FreeMASTER 工具实时监控嵌入式固件变量、进行运行时参数在线调优、长时间数据记录、或离线分析导出的录制数据时使用。
---

# FreeMASTER 实时调试

## 适用场景

- 用户想看某个全局变量的实时变化曲线（虚拟示波器/Scope）。
- 在固件运行时修改 PID 系数、阈值等参数，无需重新编译烧录。
- 长时间记录传感器数据或系统状态到文件（Recorder），用于离线分析。
- 通过 J-Link 探针的 BDM/SWD 接口直接访问 MCU 内存，无需固件嵌入 FreeMASTER 驱动。
- 与串口日志（`serial-monitor`）配合，同时观察运行时行为和高频变量变化。
- **离线分析已导出的录制数据**：解析 FreeMASTER Oscilloscope `.txt` 或 Recorder `.csv` 导出文件，检测状态跳变、计算采样率、导出数据子集。

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

## 录制产物理解

FreeMASTER 有两种数据导出方式，产物格式不同：

### Oscilloscope 导出（`.txt`）

从 Scope/Oscilloscope 视图通过 `File → Export Data` 导出，生成制表符分隔的 `.txt` 文件。
文件名通常为 `oscNNNNN.txt`。

```
# Oscilloscope Data
<空行可选>
# Seconds	Var1	Var2	Var3	...
1.885795	2	0	0	...
1.900089	2	0	0	...
```

结构特征：
- 第1行：`# Oscilloscope Data` 文件标识
- 第2行（或空行后的下一行）：`# Seconds\t<var1>\t<var2>\t...` 时间列 + 变量名表头
- 后续行：`<timestamp>\t<value1>\t<value2>\t...` 数据行
- 时间单位为秒（s），高精度浮点（6 位小数）
- 值可以是整数、浮点、十六进制（如 `0xca`）、字符串
- 典型的嵌入式场景录制包含大量状态标志位（0/1 值）和少量连续变量（频率、电压等）
- 采样间隔通常不均匀，取决于 FreeMASTER 与目标的通信延迟

### Recorder 导出（`.csv`）

从 Recorder 面板导出，生成逗号分隔的 `.csv` 文件。

```
Time [s],Var1,Var2,Var3,...
1.885795,2,0,0,...
1.900089,2,0,0,...
```

结构特征：
- 第1行：`Time [s],<var1>,<var2>,...` 表头
- 后续行：`<timestamp>,<value1>,<value2>,...` 数据行
- 采样间隔由 Recorder 配置决定（默认 1000 Hz）

### 典型录制分析场景

从实践中观察到的真实 FreeMASTER 录制（如 LLC 双向 DC/DC 变换器调试）：
- **时间跨度**：数十秒到数分钟（示例文件 77 秒，5445 个采样点）
- **采样率**：约 70 Hz（~14ms 间隔），远低于 Recorder 配置值，反映实际 BDM 通信瓶颈
- **变量构成**：约 2/3 为标志位（flag/enable/status），1/3 为连续量（频率、数组数据）
- **稳态占比**：约 1/3 变量在全程保持不变（未激活的功能模块）
- **跳变密度**：状态切换时刻（如充电→放电模式切换）触发数十个变量同时跳变
- **分析价值**：通过跳变时间线还原系统行为序列，验证状态机逻辑

## 自动探测

- FreeMASTER 安装路径按以下顺序自动探测：配置文件 `em_config` → `PATH` 环境变量 → `C:\NXP\` 盲搜 → `C:\Program Files\NXP\` 盲搜。
- ELF 文件路径优先从 `Project Profile` 的 `artifact_path` 读取。
- 目标 MCU 型号从 `Project Profile` 的 `target_mcu` 或 `jlink_device` 读取。
- 变量列表需用户显式提供，无法自动推断。
- 若关键信息缺失（FreeMASTER 未安装 / ELF 不存在 / MCU 未知），返回 `blocked` 状态并引导用户补充。

## 执行步骤

### 在线调试（生成 .pmpx + 启动 FreeMASTER）

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
   - 使用 `Tools → Recorder → Start` 记录数据到指定目录（若指定 `--recorder-dir`）
   - 使用 `File → Export Data` 从 Scope 视图导出当前波形数据为 `.txt`
8. 读取脚本输出的结果报告，确认连接状态。

### 离线分析录制数据

1. 用户提供已导出的 FreeMASTER 录制文件（`.txt` 或 `.csv`）。
2. 运行分析脚本：
   ```powershell
   # 基础分析报告
   python freemaster_export_analyzer.py D:\Data\osc00005.txt

   # 详细模式（显示每次跳变的值）
   python freemaster_export_analyzer.py D:\Data\osc00005.txt --verbose

   # JSON 输出（供下游脚本消费）
   python freemaster_export_analyzer.py D:\Data\osc00005.txt --json

   # 导出特定变量的数据子集
   python freemaster_export_analyzer.py D:\Data\osc00005.txt \
     --export subset.csv --vars System_Function,sys_state,Charge_effective_fsw

   # 导出特定时间段
   python freemaster_export_analyzer.py D:\Data\osc00005.txt \
     --export transient.csv --vars sys_state,Relay1_Status --t0 4.7 --t1 12.5
   ```
3. 分析报告输出：
   - 文件元数据（类型、变量数、采样点数、时间范围、采样率）
   - 变量分类（恒定变量 vs 变化变量）
   - 每个变化变量的跳变时间线（时间点 + 旧值 → 新值）
   - 总跳变次数统计
4. 根据分析结果：
   - 关注状态跳变密集的时间段 → 对应系统模式切换事件
   - 恒定变量确认对应功能模块未激活
   - 跳变序列还原系统状态机行为
   - 异常跳变（如预期之外的值变化）标记为可疑事件

## 失败分流

- FreeMASTER.exe 未找到 → `environment-missing`
- ELF 文件不存在 → `artifact-missing`
- J-Link 驱动未安装 → `environment-missing`
- MCU 型号未知 → `ambiguous-context`
- .pmpx 写入失败 → `environment-missing`
- FreeMASTER 启动失败 → `target-response-abnormal`
- 非 Windows 平台 → `platform-unsupported`
- 录制文件解析失败 → `artifact-missing`（文件不存在/格式无法识别/内容不足）

## 平台说明

- FreeMASTER 3.x 仅支持 Windows 原生运行。Linux/macOS 用户请使用 `serial-monitor` 或 `debug-jlink` 替代。
- 默认通过 J-Link BDM 插件以 SWD 接口连接目标，速度默认 4000 kHz。
- .pmpx 是 FreeMASTER 3.x 的项目文件格式（纯 XML 文本，根元素 `<xmlarchive>`）。
- 自带脚本使用 Python 标准库（re、subprocess、csv、json），仅 Windows 可启动 GUI。
- **导出文件分析脚本**（`freemaster_export_analyzer.py`）跨平台可用，仅依赖 Python 标准库。

## 输出约定

### 在线调试输出

- 输出执行模式、FreeMASTER 路径、ELF 路径、.pmpx 路径、预置变量数量和 Scope 变量数量。
- 状态：`success`（.pmpx 生成且 FreeMASTER 已启动）、`partial_success`（.pmpx 已生成但变量为空或启动异常）、`blocked`（关键信息缺失）、`failure`（生成失败）。
- 在 `Project Profile` 中保留 `artifact_path`、`target_mcu`、`jlink_device`。
- 成功启动后，Variable Grid 已预置变量，Scope 已预配置曲线（若指定），用户可直接连接目标开始监控。

### 录制分析输出

- 输出文件元数据（路径、类型、变量数、采样点数、时间范围、采样率）。
- 变量状态分类（恒定变量数 + 变化变量数 + 总跳变次数）。
- 每个变化变量的跳变时间线（时间点 + 值变化）。
- `--json` 模式输出机器可读的结构化 JSON。
- `--export` 模式输出指定变量/时间范围的 CSV 子集。

## 交接关系

- 当需要先构建 ELF 时，上游交给 `build-keil` / `build-cmake` / `build-iar` 等构建 skill。
- 当需要先烧录固件到目标时，上游交给 `flash-jlink`。
- 当 ELF 缺失需要 debug 会话先做 download-and-halt 时，上游交给 `debug-jlink`。
- 当需要同时观察串口日志时，并行交给 `serial-monitor`。
- 当 FreeMASTER 记录的 Recorder 数据需要离线分析时，下游交给 `memory-analysis`。
- 当 FreeMASTER Oscilloscope 导出数据需要跳变检测和状态机还原时，使用本 skill 内置的 `freemaster_export_analyzer.py`。
- 当需要 RTOS 任务级监控时，下游交给 `rtos-debug`。
- 当录制数据经过分析发现异常跳变需要根因追踪时，下游交给 `embedded-bug-hunt`。
