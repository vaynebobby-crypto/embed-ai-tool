#!/usr/bin/env python3
"""FreeMASTER 导出数据分析工具。

为 `freemaster-debug` skill 提供录制产物的离线分析能力：

- 解析 FreeMASTER Oscilloscope 导出的 .txt 文件（TSV 格式）
- 解析 FreeMASTER Recorder 导出的 .csv 文件
- 提取变量名、时间范围、采样率等元数据
- 检测变量值的状态跳变点（瞬态事件）
- 输出结构化摘要报告
- 支持按时间范围/变量名导出子集

FreeMASTER 导出文件格式：

  Oscilloscope (.txt) — 从 Scope 视图中 File → Export Data 导出
    第1行: "# Oscilloscope Data"
    第2行: "# Seconds\t<var1>\t<var2>\t..."
    第3行起: <timestamp>\t<value1>\t<value2>\t...
    分隔符: 制表符 (\\t)

  Recorder (.csv) — 从 Recorder 面板导出
    第1行: "Time [s],<var1>,<var2>,..."
    第2行起: <timestamp>,<value1>,<value2>,...
    分隔符: 逗号 (,)
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_VALID_CHANGE_THRESHOLD = 1e-9


@dataclass
class ExportMeta:
    """FreeMASTER 导出文件的元数据."""
    file_path: str
    file_type: str  # "oscilloscope" or "recorder"
    variable_names: list[str] = field(default_factory=list)
    variable_count: int = 0
    sample_count: int = 0
    time_start: float = 0.0
    time_end: float = 0.0
    duration: float = 0.0
    avg_sample_interval: float = 0.0
    estimated_sample_rate_hz: float = 0.0


@dataclass
class VarTransition:
    """变量状态跳变记录."""
    var_name: str
    var_index: int
    time_before: float
    time_after: float
    old_value: str
    new_value: str
    row_before: int
    row_after: int


@dataclass
class ExportAnalysis:
    """导出文件分析结果."""
    meta: ExportMeta
    transitions: list[VarTransition] = field(default_factory=list)
    steady_state_vars: list[str] = field(default_factory=list)
    varying_vars: list[str] = field(default_factory=list)
    # 按变量名分组的跳变列表
    transitions_by_var: dict[str, list[VarTransition]] = field(default_factory=dict)


def _detect_file_type(file_path: Path, first_line: str) -> str:
    """检测导出文件类型."""
    if first_line.startswith("# Oscilloscope Data"):
        return "oscilloscope"
    if first_line.startswith("Time [s]") or first_line.startswith("time,"):
        return "recorder"
    # 回退：按文件扩展名
    ext = file_path.suffix.lower()
    if ext == ".txt":
        return "oscilloscope"
    if ext == ".csv":
        return "recorder"
    return "unknown"


def _parse_oscilloscope(file_path: Path) -> tuple[ExportMeta, list[list[str]]]:
    """解析 Oscilloscope 导出的 .txt 文件."""
    meta = ExportMeta(
        file_path=str(file_path.resolve()),
        file_type="oscilloscope",
    )

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        raw_lines = f.readlines()

    # 跳过空行，以第1条非空首行为 "# Oscilloscope Data"，下一条非空 "#" 行为表头
    lines = [ln.rstrip("\n").rstrip("\r") for ln in raw_lines]
    non_empty: list[str] = [ln for ln in lines if ln.strip()]

    if len(non_empty) < 3:
        raise ValueError(f"文件内容不足: 至少需要 3 个非空行（标题 + 表头 + 数据），实际 {len(non_empty)} 行")

    # 第1非空行: "# Oscilloscope Data"
    if not non_empty[0].startswith("# Oscilloscope"):
        raise ValueError(f"首行不是 Oscilloscope 数据文件: {non_empty[0][:60]}")

    # 第2非空行: "# Seconds\tvar1\tvar2\t..."
    header_line = non_empty[1].strip()
    if header_line.startswith("#"):
        header_line = header_line[1:].strip()
    headers = [h.strip() for h in header_line.split("\t")]
    if not headers or headers[0].lower() not in ("seconds", "time"):
        raise ValueError(f"表头行首列应为 time/seconds，实际: {header_line[:80]}")
    meta.variable_names = headers[1:]
    meta.variable_count = len(meta.variable_names)

    # 数据行：从第3个非空行开始
    data_rows: list[list[str]] = []
    for line in non_empty[2:]:
        stripped = line.strip()
        if not stripped:
            continue
        fields = stripped.split("\t")
        if len(fields) < 2:
            continue
        data_rows.append(fields)

    if not data_rows:
        raise ValueError("未找到数据行")

    meta.sample_count = len(data_rows)
    meta.time_start = float(data_rows[0][0])
    meta.time_end = float(data_rows[-1][0])
    meta.duration = meta.time_end - meta.time_start
    if meta.sample_count >= 2:
        meta.avg_sample_interval = meta.duration / (meta.sample_count - 1)
        if meta.avg_sample_interval > 0:
            meta.estimated_sample_rate_hz = 1.0 / meta.avg_sample_interval

    return meta, data_rows


def _parse_recorder(file_path: Path) -> tuple[ExportMeta, list[list[str]]]:
    """解析 Recorder 导出的 .csv 文件."""
    meta = ExportMeta(
        file_path=str(file_path.resolve()),
        file_type="recorder",
    )

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        rows = list(reader)

    if len(rows) < 2:
        raise ValueError(f"CSV 内容不足: 至少需要 2 行（表头 + 数据）")

    header = [h.strip() for h in rows[0]]
    if not header or header[0].lower() not in ("time [s]", "time", "seconds"):
        raise ValueError(f"第一列应为时间列，实际: {header[0] if header else '(空)'}")
    meta.variable_names = header[1:]
    meta.variable_count = len(meta.variable_names)

    data_rows = rows[1:]
    if not data_rows:
        raise ValueError("未找到数据行")

    meta.sample_count = len(data_rows)
    meta.time_start = float(data_rows[0][0])
    meta.time_end = float(data_rows[-1][0])
    meta.duration = meta.time_end - meta.time_start
    if meta.sample_count >= 2:
        meta.avg_sample_interval = meta.duration / (meta.sample_count - 1)
        if meta.avg_sample_interval > 0:
            meta.estimated_sample_rate_hz = 1.0 / meta.avg_sample_interval

    return meta, data_rows


def parse_export_file(file_path: Path) -> tuple[ExportMeta, list[list[str]]]:
    """解析 FreeMASTER 导出文件，返回 (元数据, 数据行列表)."""
    if not file_path.is_file():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        first_line = f.readline().strip()

    file_type = _detect_file_type(file_path, first_line)

    if file_type == "oscilloscope":
        return _parse_oscilloscope(file_path)
    elif file_type == "recorder":
        return _parse_recorder(file_path)
    else:
        raise ValueError(f"无法识别的导出格式: 首行 = '{first_line[:80]}'")


def _value_changed(old_val: str, new_val: str) -> bool:
    """判断两个字符串值是否发生了有意义的变化."""
    if old_val == new_val:
        return False
    # 尝试数值比较
    try:
        old_f = float(old_val)
        new_f = float(new_val)
        return abs(new_f - old_f) > _VALID_CHANGE_THRESHOLD
    except ValueError:
        # 非数值字符串，直接比较
        return old_val != new_val


def detect_transitions(meta: ExportMeta, data_rows: list[list[str]]) -> list[VarTransition]:
    """检测所有变量值的状态跳变点.

    对每列（变量）逐行对比，记录值发生变化的时刻。
    只检测数值/字符串变化（不检测浮点微小波动，阈值 1e-9）。
    """
    transitions: list[VarTransition] = []
    var_count = meta.variable_count

    for var_idx in range(var_count):
        var_name = meta.variable_names[var_idx] if var_idx < len(meta.variable_names) else f"var_{var_idx}"
        col_idx = var_idx + 1  # +1 跳过时间列

        prev_val = None
        prev_time = None
        prev_row = 0

        for row_idx, row in enumerate(data_rows):
            if col_idx >= len(row):
                continue
            cur_val = row[col_idx].strip()
            cur_time = float(row[0]) if row[0].strip() else 0.0

            if prev_val is not None and _value_changed(prev_val, cur_val):
                transitions.append(VarTransition(
                    var_name=var_name,
                    var_index=var_idx,
                    time_before=prev_time or 0.0,
                    time_after=cur_time,
                    old_value=prev_val,
                    new_value=cur_val,
                    row_before=prev_row,
                    row_after=row_idx + 1,
                ))

            prev_val = cur_val
            prev_time = cur_time
            prev_row = row_idx + 1

    return transitions


def analyze_export(file_path: str | Path) -> ExportAnalysis:
    """分析 FreeMASTER 导出文件的完整流程."""
    fp = Path(file_path)
    meta, data_rows = parse_export_file(fp)
    transitions = detect_transitions(meta, data_rows)

    # 分类变量
    varying_set: set[str] = set()
    for t in transitions:
        varying_set.add(t.var_name)

    steady_vars = [v for v in meta.variable_names if v not in varying_set]
    varying_vars = sorted(varying_set, key=lambda v: meta.variable_names.index(v) if v in meta.variable_names else 999)

    # 按变量分组跳变
    by_var: dict[str, list[VarTransition]] = {}
    for t in transitions:
        by_var.setdefault(t.var_name, []).append(t)

    return ExportAnalysis(
        meta=meta,
        transitions=transitions,
        steady_state_vars=steady_vars,
        varying_vars=varying_vars,
        transitions_by_var=by_var,
    )


def print_analysis_report(analysis: ExportAnalysis, verbose: bool = False) -> None:
    """打印结构化的分析报告."""
    meta = analysis.meta
    print(f"\n{'='*60}")
    print(f"  FreeMASTER 导出数据分析报告")
    print(f"{'='*60}")

    print(f"\n📁 文件信息:")
    print(f"  路径:       {meta.file_path}")
    print(f"  类型:       {meta.file_type}")
    print(f"  变量数:     {meta.variable_count}")
    print(f"  采样点数:   {meta.sample_count}")
    print(f"  时间范围:   {meta.time_start:.3f}s ~ {meta.time_end:.3f}s")
    print(f"  总时长:     {meta.duration:.3f}s")
    print(f"  平均间隔:   {meta.avg_sample_interval*1000:.2f}ms")
    print(f"  估算采样率: {meta.estimated_sample_rate_hz:.1f}Hz")

    print(f"\n📊 变量状态分类:")
    print(f"  恒定变量:   {len(analysis.steady_state_vars)} 个")
    print(f"  变化变量:   {len(analysis.varying_vars)} 个")
    print(f"  总跳变次数: {len(analysis.transitions)}")

    if analysis.steady_state_vars:
        print(f"\n🔒 恒定变量 (全程无变化):")
        for v in analysis.steady_state_vars:
            # 找到该变量的恒定值
            idx = meta.variable_names.index(v)
            val = "N/A"
            for row in data_rows_cache:
                if idx + 1 < len(row):
                    val = row[idx + 1]
                    break
            print(f"  {v} = {val}")

    if analysis.varying_vars:
        print(f"\n📈 变化变量 (有状态跳变):")
        for v in analysis.varying_vars:
            ts = analysis.transitions_by_var.get(v, [])
            print(f"  {v}: {len(ts)} 次跳变")
            if verbose or len(ts) <= 5:
                for t in ts:
                    print(f"    @{t.time_after:.6f}s: {t.old_value} → {t.new_value}")
            else:
                # 只显示前3和后2
                for t in ts[:3]:
                    print(f"    @{t.time_after:.6f}s: {t.old_value} → {t.new_value}")
                print(f"    ... ({len(ts) - 5} 次省略) ...")
                for t in ts[-2:]:
                    print(f"    @{t.time_after:.6f}s: {t.old_value} → {t.new_value}")

    print()


# 缓存最近一次解析的数据行，供 print_analysis_report 使用
data_rows_cache: list[list[str]] = []


def _analyze_and_cache(file_path: str | Path) -> ExportAnalysis:
    """带缓存的解析，供 print_analysis_report 使用."""
    global data_rows_cache
    fp = Path(file_path)
    meta, data_rows = parse_export_file(fp)
    data_rows_cache = data_rows
    transitions = detect_transitions(meta, data_rows)

    varying_set: set[str] = set()
    for t in transitions:
        varying_set.add(t.var_name)

    steady_vars = [v for v in meta.variable_names if v not in varying_set]
    varying_vars = sorted(varying_set, key=lambda v: meta.variable_names.index(v) if v in meta.variable_names else 999)

    by_var: dict[str, list[VarTransition]] = {}
    for t in transitions:
        by_var.setdefault(t.var_name, []).append(t)

    return ExportAnalysis(
        meta=meta,
        transitions=transitions,
        steady_state_vars=steady_vars,
        varying_vars=varying_vars,
        transitions_by_var=by_var,
    )


def export_subset(analysis: ExportAnalysis, output_path: Path,
                  var_names: list[str] | None = None,
                  time_start: float | None = None,
                  time_end: float | None = None) -> int:
    """导出指定变量和时间范围的数据子集到 CSV.

    Returns:
        导出的数据行数.
    """
    global data_rows_cache
    meta = analysis.meta
    rows = data_rows_cache

    if not rows:
        print("⚠️ 无数据可导出（请先运行分析）")
        return 0

    # 确定变量列索引
    if var_names:
        col_indices = []
        col_names = []
        for vn in var_names:
            if vn in meta.variable_names:
                col_indices.append(meta.variable_names.index(vn) + 1)
                col_names.append(vn)
            else:
                print(f"⚠️ 跳过未知变量: {vn}")
    else:
        col_indices = list(range(1, meta.variable_count + 1))
        col_names = list(meta.variable_names)

    if not col_indices:
        print("⚠️ 无有效变量可导出")
        return 0

    # 过滤时间范围
    filtered_rows = rows
    if time_start is not None:
        filtered_rows = [r for r in filtered_rows if float(r[0]) >= time_start]
    if time_end is not None:
        filtered_rows = [r for r in filtered_rows if float(r[0]) <= time_end]

    # 写入 CSV
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Time [s]"] + col_names)
        for row in filtered_rows:
            time_val = row[0]
            vals = [row[ci] if ci < len(row) else "" for ci in col_indices]
            writer.writerow([time_val] + vals)

    print(f"✅ 已导出 {len(filtered_rows)} 行到 {output_path}")
    return len(filtered_rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="FreeMASTER 导出数据分析工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s D:\\Data\\osc00005.txt
  %(prog)s D:\\Data\\osc00005.txt --verbose
  %(prog)s D:\\Data\\recorder.csv --json
  %(prog)s D:\\Data\\osc00005.txt --export subset.csv --vars System_Function,sys_state
  %(prog)s D:\\Data\\osc00005.txt --export subset.csv --vars adc_value --t0 10 --t1 20
        """,
    )
    parser.add_argument("file", help="FreeMASTER 导出的 .txt 或 .csv 文件路径")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="显示所有跳变的详细值变化")
    parser.add_argument("--json", action="store_true",
                        help="以 JSON 格式输出分析结果")
    parser.add_argument("--export", default=None, metavar="OUTPUT.csv",
                        help="将数据子集导出到指定 CSV 文件")
    parser.add_argument("--vars", default=None,
                        help="要导出的变量名，逗号分隔（默认全部）")
    parser.add_argument("--t0", type=float, default=None,
                        help="导出起始时间 (s)")
    parser.add_argument("--t1", type=float, default=None,
                        help="导出结束时间 (s)")
    return parser


def _print_json(analysis: ExportAnalysis) -> None:
    """以 JSON 格式输出分析结果."""
    import json

    meta = analysis.meta
    result = {
        "file": meta.file_path,
        "type": meta.file_type,
        "variable_count": meta.variable_count,
        "variable_names": meta.variable_names,
        "sample_count": meta.sample_count,
        "time_start": meta.time_start,
        "time_end": meta.time_end,
        "duration": meta.duration,
        "avg_sample_interval_ms": round(meta.avg_sample_interval * 1000, 3),
        "estimated_sample_rate_hz": round(meta.estimated_sample_rate_hz, 1),
        "steady_state_vars": analysis.steady_state_vars,
        "varying_vars": analysis.varying_vars,
        "transition_count": len(analysis.transitions),
        "transitions": [
            {
                "var": t.var_name,
                "time": round(t.time_after, 6),
                "old": t.old_value,
                "new": t.new_value,
            }
            for t in analysis.transitions
        ],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.is_file():
        print(f"❌ 文件不存在: {args.file}")
        return 1

    try:
        analysis = _analyze_and_cache(file_path)
    except ValueError as e:
        print(f"❌ 解析失败: {e}")
        return 1
    except FileNotFoundError as e:
        print(f"❌ {e}")
        return 1

    if args.json:
        _print_json(analysis)
    else:
        print_analysis_report(analysis, verbose=args.verbose)

    if args.export:
        var_list = None
        if args.vars:
            var_list = [v.strip() for v in args.vars.split(",") if v.strip()]
        export_subset(
            analysis=analysis,
            output_path=Path(args.export),
            var_names=var_list,
            time_start=args.t0,
            time_end=args.t1,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
