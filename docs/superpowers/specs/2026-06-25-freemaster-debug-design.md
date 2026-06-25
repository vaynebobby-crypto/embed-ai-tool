# FreeMASTER 调试 Skill 设计文档

- **日期**: 2026-06-25
- **状态**: 设计确认，待实现
- **关联**: [[2025-06-15-gdlink-flash-debug-design]]

---

## 1. 目标

为 `embed-ai-tool` 项目新增 `freemaster-debug` skill，使 LLM 能通过 FreeMASTER 工具对嵌入式目标进行实时变量监控、在线参数调优和数据记录。自动探测 FreeMASTER 安装、生成 `.pmpx` 项目文件并启动 GUI 调试会话。

---

## 2. 需求决策记录

| 维度 | 决定 |
|------|------|
| 核心场景 | 全功能调试台（变量监控 + 在线调优 + 数据记录） |
| 通信接口 | SWD/JTAG 调试口（BDM 直访内存，无需固件嵌入 FreeMASTER 驱动） |
| 调试探针 | J-Link（与现有 `debug-jlink` skill 联动） |
| FreeMASTER 安装 | 不确定版本/路径，需自动探测 |
| 项目文件格式 | `.pmpx`（FreeMASTER 3.x） |
| 目标平台 | Windows（FreeMASTER 3.x 仅 Windows 原生支持） |

---

## 3. 整体架构

```
skills/freemaster-debug/
├── SKILL.md                        # Skill 定义文件（8 个必需章节）
├── references/
│   └── usage.md                    # CLI 参数与配置说明
└── scripts/
    ├── freemaster_debugger.py      # 主控脚本
    ├── freemaster_detect.py        # FreeMASTER 安装自动探测
    └── freemaster_pmpx_gen.py      # .pmpx 项目文件生成器
```

### 数据流

```
用户/LLM 触发 skill
    │
    ▼
┌─────────────────────────┐
│ 1. 环境探测              │  freemaster_detect.py
│ - 查找 FreeMASTER.exe    │  → 返回路径 + 版本信息
│ - 确认 J-Link BDM 插件   │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│ 2. 上下文收集            │  复用 contracts.md Project Profile
│ - ELF 文件路径           │  或调用 debug-jlink 探测
│ - 目标 MCU 型号          │
│ - J-Link 设备名          │
│ - 变量列表(可选)         │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│ 3. 生成 .pmpx            │  freemaster_pmpx_gen.py
│ - BDM/J-Link 插件配置    │  通信参数
│ - ELF 符号映射           │  变量地址解析
│ - 默认 Recorder 配置     │  采样率/缓冲区
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│ 4. 启动调试会话           │  freemaster_debugger.py
│ - 打开 .pmpx 项目         │  FreeMASTER.exe <project.pmpx>
│ - 自动连接目标           │  或提示用户在 GUI 中操作
│ - 输出状态               │  success/partial_success/blocked/failure
└─────────────────────────┘
```

### 与 debug-jlink 的联动点

- 复用 Project Profile 的 `jlink_device`、`target_mcu`、`artifact_path`
- 可选：无 ELF 时触发 `debug-jlink` 的 `download-and-halt` 先烧录

### 平台限制

- Windows 原生（FreeMASTER 3.x 的约束）
- Linux/macOS → `platform-unsupported`，引导使用 `serial-monitor` 或 `debug-jlink`

---

## 4. 触发条件与输入约定

### 4.1 适用场景

| 场景 | 选择 |
|------|------|
| 用户想看某个全局变量的实时变化曲线 | `freemaster-debug` |
| 运行时改 PID 系数、阈值等参数 | `freemaster-debug` |
| 长时间记录传感器数据到文件 | `freemaster-debug` |
| 单步执行、设断点、查看调用栈 | → `debug-jlink` |
| 抓取串口 printf 日志 | → `serial-monitor` |
| 固件崩溃后检查寄存器/栈回溯 | → `debug-jlink` (crash-context) |

触发关键词：`监控变量`、`实时曲线`、`在线调参`、`FreeMASTER`、`虚拟示波器`、`scope`、`recorder`、`运行时改`

### 4.2 必要输入

| 输入项 | 必要性 | 自动探测 |
|--------|--------|----------|
| ELF/AXF 固件文件 | 必需 | Project Profile `artifact_path` |
| 目标 MCU 型号 | 必需 | Project Profile `target_mcu` |
| J-Link 设备名 | 必需 | Project Profile `jlink_device` |
| FreeMASTER 安装路径 | 必需 | 自动探测脚本 |
| 要监控的变量列表 | 可选 | 用户指定，否则生成空项目 |
| 通信接口类型 | 可选 | 默认 BDM/J-Link |

### 4.3 自动探测优先级

1. Project Profile 已有字段 → 直接使用
2. 调用 `build-*` 或 `debug-jlink` 探测补齐 → 写入 Profile
3. FreeMASTER 路径盲搜：
   - `C:\NXP\FreeMASTER*\FreeMASTER.exe`
   - `C:\Program Files\NXP\FreeMASTER*\FreeMASTER.exe`
   - MCUXpresso IDE 内置路径
4. 探测失败 → `blocked` + `ambiguous-context`，引导用户 `em_config` 配置

---

## 5. .pmpx 生成器

### 5.1 CLI 接口

```
freemaster_pmpx_gen.py
  --elf <path>           # ELF/AXF 文件，用于符号解析
  --mcu <name>           # 目标 MCU，如 GD32F450IK
  --jlink-device <name>  # J-Link 设备名，如 GD32F450IK
  --jlink-speed <kHz>    # J-Link SWD 时钟，默认 4000
  --vars <list>          # 可选：预置变量名列表，逗号分隔
  --output <path>        # .pmpx 输出路径，默认工作区根目录
  --sample-rate <hz>     # Recorder 采样率，默认 1000
```

### 5.2 生成逻辑

```
1. 读取 ELF 文件
   ├── 校验 ELF 存在且可读
   └── 提取 .text/.data/.bss 段地址范围 → 用于变量绑定

2. 生成 .pmpx XML
   ├── <COMM> 块：BDM/J-Link 插件配置
   │   ├── 接口类型: SWD
   │   ├── J-Link 速度: --jlink-speed
   │   ├── 目标设备: --jlink-device
   │   └── 复位策略: core reset on connect
   │
   ├── <ELF> 块：符号文件引用
   │   └── 相对路径指向 --elf（使项目可移植）
   │
   ├── <Vars> 块：变量列表
   │   ├── 若提供 --vars：逐个写入变量名引用
   │   └── 若未提供：生成空块 + 注释提示手动添加
   │
   ├── <Recorder> 块：默认记录器
   │   ├── 采样周期: 1/--sample-rate
   │   ├── 缓冲区大小: 默认 10000 点
   │   └── 触发模式: 手动
   │
   └── <Scopes> 块：空 scope，用户自行拖入变量

3. 写入 .pmpx 文件
   └── 若目标已存在 → 备份为 .pmpx.bak 后覆盖
```

### 5.3 输出状态

| 状态 | 条件 |
|------|------|
| `success` | .pmpx 生成完毕 + 路径返回 |
| `partial_success` | .pmpx 生成但无 ELF → vars 为空 |
| `failure` | ELF 无效 / 磁盘写入失败 / MCU 信息缺失 |

### 5.4 错误处理

| 情况 | 分类 |
|------|------|
| ELF 不存在 | `artifact-missing` → 提示先 build |
| ELF 无符号表 | `partial_success` → vars 为空 |
| MCU 信息缺失 | `ambiguous-context` → 引导用户补充 |
| 磁盘空间不足 | `environment-missing` |
| .pmpx XML 语法错误 | 内部校验后再写入，失败回滚 |

---

## 6. 主控脚本

### 6.1 执行模式

```
freemaster_debugger.py <mode> [options]

mode:
  start        生成 .pmpx 并启动 FreeMASTER GUI
  generate     仅生成 .pmpx 文件，不启动 GUI
  attach       尝试通过 COM/Automation 附着到运行中实例（TODO）
  record       自动化采集：启动→连接→录N秒→导出→关闭（TODO 扩展）
```

### 6.2 start 模式流程

```
Step 1: 环境就绪检查
  ├── freemaster_detect.py → 确认 freemaster_exe 可用
  ├── 检查 J-Link 驱动（复用 debug-jlink 探测）
  └── 检查 ELF 文件存在

Step 2: 收集缺失上下文
  ├── 缺 MCU → 询问或从 ELF 架构信息推断
  ├── 缺 jlink_device → 用 target_mcu 作为默认值
  └── 全部未知 → ambiguous-context, blocked

Step 3: 生成 .pmpx
  └── 调用 freemaster_pmpx_gen.py
      ├── success → 继续
      ├── partial_success → 提示用户 + 继续
      └── failure → 终止

Step 4: 启动 FreeMASTER
  └── PowerShell Start-Process:
      FreeMASTER.exe "<project.pmpx>"
      ├── 成功启动 → success
      ├── 启动超时 → partial_success（.pmpx 已生成）
      └── 启动失败 → failure (environment-missing)

Step 5: 输出结果
  └── 按 contracts.md 约定格式输出
```

### 6.3 generate 模式

Step 1-3 同上，跳过启动步骤，直接返回 .pmpx 路径。

### 6.4 attach / record 模式

本次标记为 `TODO`，后续扩展。

---

## 7. 输出约定

### success

```
status: success
summary: FreeMASTER 已启动，项目 <name>.pmpx 已加载
evidence:
  - pmpx_path: <生成的 .pmpx 绝对路径>
  - elf_path: <使用的 ELF 路径>
  - freemaster_exe: <FreeMASTER.exe 路径>
  - vars_count: <预置变量数量>
next_action: 在 FreeMASTER GUI 中将变量拖入 Scope/Oscilloscope 开始监控
```

### partial_success

```
status: partial_success
summary: .pmpx 已生成但未预置变量，或 FreeMASTER 启动异常
evidence:
  - pmpx_path: <路径>
  - warning: <警告原因>
next_action: 手动启动 FreeMASTER 并打开 .pmpx，在 Variable Grid 中添加变量
```

### blocked

```
status: blocked
summary: 缺少必要信息（FreeMASTER 未安装 / ELF 缺失 / MCU 未知）
failure_category: environment-missing | artifact-missing | ambiguous-context
next_action: 运行 em_config 配置 FreeMASTER 路径 / 先 build 生成 ELF
```

---

## 8. 失败分流

| 失败 | 分类 |
|------|------|
| FreeMASTER.exe 未找到 | `environment-missing` |
| ELF 文件不存在 | `artifact-missing` |
| J-Link 驱动未安装 | `environment-missing` |
| MCU 型号未知 | `ambiguous-context` |
| .pmpx 写入失败 | `environment-missing` |
| FreeMASTER 启动崩溃 | `target-response-abnormal` |
| 平台非 Windows | `platform-unsupported` |

---

## 9. 交接关系

| 方向 | Skill | 场景 |
|------|-------|------|
| 上游 → | `build-keil` / `build-cmake` / ... | 需要先生成 ELF |
| 上游 → | `flash-jlink` | 先烧录固件到目标 |
| 上游 → | `debug-jlink` | ELF 缺失时先做 download-and-halt |
| 下游 ← | `serial-monitor` | 同时抓取串口日志做关联分析 |
| 下游 ← | `rtos-debug` | FreeMASTER 可监控 RTOS 任务统计变量 |
| 下游 ← | `memory-analysis` | 采集到的 Recorder 数据做离线分析 |

---

## 10. 需要修改的现有文件

| 文件 | 修改内容 |
|------|----------|
| `SKILL.md`（总控） | 调试分类候选表添加 `freemaster-debug` |
| `README.md` | 技能列表添加 `freemaster-debug` 条目 |
| `shared/contracts.md` | 可选：新增 `freemaster_exe` 字段到 Project Profile |
| `.claude/settings.json` | 添加 FreeMASTER 相关的权限条目 |

---

## 11. 格式验证方案

FreeMASTER 3.x `.pmpx` 的精确 XML schema 将在实现阶段通过以下方式确认：

1. 在用户本机用 FreeMASTER GUI 手动创建最小项目并保存为 `.pmpx`
2. 读取生成的 .pmpx 文件，提取有效的 XML 模板结构
3. 基于真实模板编写 `freemaster_pmpx_gen.py` 的生成逻辑

这确保生成的文件 100% 与用户安装的 FreeMASTER 版本兼容。
