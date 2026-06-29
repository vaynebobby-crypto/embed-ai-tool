#!/usr/bin/env python3
""".pmpx 项目文件生成器。

为 `freemaster-debug` skill 提供 .pmpx 生成能力：

- 基于参考模板 XML，正则替换 ELF 文件路径
- 注入用户指定的变量定义（CVariable 对象图）
- 配置 Recorder 数据保存目录
- 可选的 Scope/Oscilloscope 变量预分配

.pmpx 格式说明：
  - 纯 XML 文本（非 ZIP），根元素 <xmlarchive>
  - ELF 路径存储在 CPrjDoc_MapFileInfo.file_name 成员中
  - 通信配置（BDM/J-Link/SWD）由 FreeMASTER 独立管理，不在 .pmpx 内
  - 变量存储在 CObList (variables) → CVariable 对象图 → watch_variables + variable_info
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path
from typing import Any

# stdout/stderr UTF-8 reconfigure (matching project convention)
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

_SCRIPT_DIR = Path(__file__).resolve().parent
_REFERENCES_DIR = _SCRIPT_DIR.parent / "references"
_DEFAULT_TEMPLATE = _REFERENCES_DIR / "_ref_freemaster_template.pmpx"

# 生成对象的起始 ID，避开模板中已有的 ObjId0000~ObjId0056
_GEN_OBJ_ID_BASE = 100

# 匹配 ELF/AXF/OUT 文件路径
# 格式: <member name="file_name" type="string">C:\path\to\file.axf</member>
_FILE_NAME_RE = re.compile(
    r'(<member name="file_name" type="string">)[^<]+\.(?:axf|elf|out)(</member>)'
)

# 匹配 data_capture_dir
_DATA_CAPTURE_DIR_RE = re.compile(
    r'(<member name="data_capture_dir" type="string">)[^<]*(</member>)'
)

# ── 单个 CVariable 对象 XML 模板 ──
_VARIABLE_XML_TEMPLATE = """\
\t\t<object name="{obj_id}" type="CVariable">
\t\t\t<member name="name" type="string">{var_name}</member>
\t\t\t<member name="unit" type="string">{unit}</member>
\t\t\t<member name="period" type="sint32">{period}</member>
\t\t\t<member name="address" type="string">{var_name}</member>
\t\t\t<member name="last_addr" type="uint32">0x0</member>
\t\t\t<member name="byte_size" type="sint32">{byte_size}</member>
\t\t\t<member name="description" type="string">{description}</member>
\t\t\t<member name="comment" type="string"/>
\t\t\t<member name="virtual" type="sint32">0</member>
\t\t\t<member name="virtual_default" type="string">0</member>
\t\t\t<member name="treat_as" type="sint32">{treat_as}</member>
\t\t\t<member name="type_fmt" type="string">{type_fmt}</member>
\t\t\t<member name="bit_shift" type="sint32">0</member>
\t\t\t<member name="bit_mask" type="string">no mask (-1)</member>
\t\t\t<member name="value_trf" type="CObject_ptr">NULL</member>
\t\t\t<member name="enum_enabled" type="sint32">0</member>
\t\t\t<member name="enum_num_always" type="sint32">0</member>
\t\t\t<member name="enum_default_val" type="string">unknown</member>
\t\t\t<member name="enum_num_with_default" type="sint32">1</member>
\t\t\t<member name="enum" type="string"/>
\t\t\t<member name="show_as" type="sint32">0</member>
\t\t\t<member name="show_val" type="sint32">1</member>
\t\t\t<member name="show_max" type="sint32">0</member>
\t\t\t<member name="show_min" type="sint32">0</member>
\t\t\t<member name="show_num_fixed_digs" type="sint32">2147483647</member>
\t\t\t<member name="show_num_lzero_fill" type="sint32">0</member>
\t\t\t<member name="show_num_afp_digs" type="sint32">2147483647</member>
\t\t\t<member name="show_num_exp" type="sint32">0</member>
\t\t\t<member name="show_ascii_zterm" type="sint32">0</member>
\t\t\t<member name="show_ascii_rev" type="sint32">0</member>
\t\t\t<member name="show_ascii_hex" type="sint32">1</member>
\t\t\t<member name="show_ascii_chwdt" type="sint32">1</member>
\t\t\t<member name="filt_enabled" type="sint32">0</member>
\t\t\t<member name="filt_reset_onmod" type="sint32">1</member>
\t\t\t<member name="filt_time" type="uint32">0x1388</member>
\t\t\t<member name="modif_mode" type="sint32">0</member>
\t\t\t<member name="modif_edit_mode" type="sint32">2</member>
\t\t\t<member name="modif_set_mode" type="sint32">0</member>
\t\t\t<member name="modif_auto_fin" type="sint32">1</member>
\t\t\t<member name="modif_auto_hide" type="sint32">1</member>
\t\t\t<member name="modif_predefs_modes" type="uint32">0x1</member>
\t\t\t<member name="modif_predefs_other" type="string"/>
\t\t\t<member name="modif_set_min" type="string"/>
\t\t\t<member name="modif_set_max" type="string"/>
\t\t\t<member name="modif_set_step" type="string"/>
\t\t\t<member name="modif_address" type="string"/>
\t\t\t<member name="modif_last_addr" type="uint32">0x0</member>
\t\t</object>"""

# VarInfo + CObArray 对象 XML 模板
_VARINFO_XML_TEMPLATE = """\
\t\t<object name="{varinfo_id}" type="CPrjItemBlock_VarInfo">
\t\t\t<member name="row_height" type="sint32">15</member>
\t\t\t<member name="row_cell_formats" type="CObArrayEx">{array_id}</member>
\t\t</object>
\t\t<object name="{array_id}" type="CObArray" length="0"/>"""


def _make_variable_entry(var_name: str, unit: str = "", period: int = 0,
                         byte_size: int = 4, treat_as: int = 0,
                         type_fmt: str = "Fixed point number",
                         description: str = "") -> dict:
    """构建单个变量的配置字典."""
    return {
        "var_name": var_name,
        "unit": unit,
        "period": period,
        "byte_size": byte_size,
        "treat_as": treat_as,
        "type_fmt": type_fmt,
        "description": description,
    }


def _generate_variable_objects(variables: list[dict], base_id: int) -> tuple[str, int]:
    """生成 CVariable + VarInfo + CObArray 对象的 XML 片段.

    Args:
        variables: 变量配置列表，每项含 var_name/unit/period/byte_size/treat_as/type_fmt/description
        base_id: 起始 ObjId 编号

    Returns:
        (xml_fragment, next_available_id)
    """
    parts: list[str] = []
    obj_id = base_id

    for var in variables:
        var_obj_id = f"ObjId{obj_id:04d}"
        varinfo_obj_id = f"ObjId{obj_id + 1:04d}"
        array_obj_id = f"ObjId{obj_id + 2:04d}"

        # CVariable 对象
        parts.append(_VARIABLE_XML_TEMPLATE.format(
            obj_id=var_obj_id, **var,
        ))

        # VarInfo + CObArray 对象
        parts.append(_VARINFO_XML_TEMPLATE.format(
            varinfo_id=varinfo_obj_id,
            array_id=array_obj_id,
        ))

        obj_id += 3

    return "\n".join(parts), obj_id


def _generate_variables_list_entries(variables: list[dict], base_id: int) -> str:
    """生成 variables CObList (ObjId0003) 的 item 条目."""
    entries: list[str] = []
    obj_id = base_id
    for i, _var in enumerate(variables):
        var_obj_id = f"ObjId{obj_id:04d}"
        entries.append(f'\t\t\t<member name="item{i}" type="CObject_ptr">{var_obj_id}</member>')
        obj_id += 3
    return "\n".join(entries)


def _generate_watch_variables_entries(variables: list[dict], base_id: int) -> str:
    """生成 watch_variables CObList (ObjId0014) 的 item 条目."""
    return _generate_variables_list_entries(variables, base_id)


def _generate_variable_info_entries(variables: list[dict], base_id: int) -> str:
    """生成 variable_info CMapObToObEx (ObjId0025) 的 key-value 条目."""
    entries: list[str] = []
    obj_id = base_id
    for i, _var in enumerate(variables):
        var_obj_id = f"ObjId{obj_id:04d}"
        varinfo_obj_id = f"ObjId{obj_id + 1:04d}"
        entries.append(f'\t\t\t<member name="key{i}" type="CObject_ptr">{var_obj_id}</member>')
        entries.append(f'\t\t\t<member name="value{i}" type="CObject_ptr">{varinfo_obj_id}</member>')
        obj_id += 3
    return "\n".join(entries)


# ── 模板中旧变量对象的识别 ──
# 匹配模板中已有的 CVariable 对象块（从 <object name="ObjIdXXXX" type="CVariable"> 到 </object>）
_OLD_CVARIABLE_RE = re.compile(
    r'\t\t<object name="ObjId\d{4}" type="CVariable">.*?</object>',
    re.DOTALL,
)
# 匹配旧 VarInfo + 其关联 CObArray
_OLD_VARINFO_RE = re.compile(
    r'\t\t<object name="ObjId\d{4}" type="CPrjItemBlock_VarInfo">.*?</object>\s*'
    r'\t\t<object name="ObjId\d{4}" type="CObArray" length="0"/>',
    re.DOTALL,
)

# 匹配 variables CObList (ObjId0003) 的内容区——item 条目
_OLD_VARIABLES_LIST_ITEMS_RE = re.compile(
    r'(<object name="ObjId0003" type="CObList">)\s*'
    r'(?:\t\t\t<member name="item\d+" type="CObject_ptr">ObjId\d{4}</member>\s*)+'
    r'(\t\t</object>)',
)

# 匹配 watch_variables CObList (ObjId0014) 的内容区
_OLD_WATCH_VARIABLES_ITEMS_RE = re.compile(
    r'(<object name="ObjId0014" type="CObList">)\s*'
    r'(?:\t\t\t<member name="item\d+" type="CObject_ptr">ObjId\d{4}</member>\s*)+'
    r'(\t\t</object>)',
)

# 匹配 variable_info CMapObToObEx (ObjId0025) 的内容区
_OLD_VARIABLE_INFO_ENTRIES_RE = re.compile(
    r'(<object name="ObjId0025" type="CMapObToObEx">)\s*'
    r'(?:\t\t\t<member name="key\d+" type="CObject_ptr">ObjId\d{4}</member>\s*'
    r'\t\t\t<member name="value\d+" type="CObject_ptr">ObjId\d{4}</member>\s*)+'
    r'(\t\t</object>)',
)


def _strip_old_variables(content: str) -> str:
    """从模板中移除所有旧变量对象及其关联对象."""
    # 1. 移除 CVariable 对象
    content = _OLD_CVARIABLE_RE.sub("", content)
    # 2. 移除 VarInfo + CObArray 对象对
    content = _OLD_VARINFO_RE.sub("", content)
    # 3. 清空 variables 列表内容
    content = _OLD_VARIABLES_LIST_ITEMS_RE.sub(r"\1\n\2", content)
    # 4. 清空 watch_variables 列表内容
    content = _OLD_WATCH_VARIABLES_ITEMS_RE.sub(r"\1\n\2", content)
    # 5. 清空 variable_info 映射内容
    content = _OLD_VARIABLE_INFO_ENTRIES_RE.sub(r"\1\n\2", content)
    return content


def _inject_variables_into_lists(content: str, variables: list[dict], base_id: int) -> str:
    """将生成的变量条目注入到三个列表对象中."""
    # 注入 variables 列表 (ObjId0003)
    list_entries = _generate_variables_list_entries(variables, base_id)
    content = content.replace(
        '<object name="ObjId0003" type="CObList">\n\t\t</object>',
        f'<object name="ObjId0003" type="CObList">\n{list_entries}\n\t\t</object>',
    )

    # 注入 watch_variables 列表 (ObjId0014)
    watch_entries = _generate_watch_variables_entries(variables, base_id)
    content = content.replace(
        '<object name="ObjId0014" type="CObList">\n\t\t</object>',
        f'<object name="ObjId0014" type="CObList">\n{watch_entries}\n\t\t</object>',
    )

    # 注入 variable_info 映射 (ObjId0025)
    info_entries = _generate_variable_info_entries(variables, base_id)
    content = content.replace(
        '<object name="ObjId0025" type="CMapObToObEx">\n\t\t</object>',
        f'<object name="ObjId0025" type="CMapObToObEx">\n{info_entries}\n\t\t</object>',
    )

    return content


# ── Scope/Oscilloscope 配置 ──
# FreeMASTER 3.x scope 作为 project item 的 child_items 和 watch_views 子对象存储
# watch_views 子对象位于 CPrjItemProject (ObjId0013) 中
_WATCH_VIEWS_EMPTY_RE = re.compile(
    r'(<sub name="watch_views" length=")0("/>)',
)

_CHILD_ITEMS_EMPTY_RE = re.compile(
    r'<object name="ObjId0016" type="CObList"/>',
)

# 用于展开自闭合 child_items 的方法
def _expand_child_items(content: str, scope_id: str) -> str:
    """将自闭合的 ObjId0016 展开为包含 scope 引用的完整 CObList."""
    replacement = (
        f'<object name="ObjId0016" type="CObList">\n'
        f'\t\t\t<member name="item0" type="CObject_ptr">{scope_id}</member>\n'
        f'\t\t</object>'
    )
    return _CHILD_ITEMS_EMPTY_RE.sub(replacement, content)

# Scope 对象的 XML 模板 (CPrjItemScope)
_SCOPE_OBJECT_XML = """\
\t\t<object name="{scope_id}" type="CPrjItemScope">
\t\t\t<member name="parent_item" type="CObject_ptr">ObjId0013</member>
\t\t\t<member name="tree_expand" type="sint32">1</member>
\t\t\t<member name="data_capture_mode" type="sint32">0</member>
\t\t\t<member name="data_capture_onaction" type="sint32">0</member>
\t\t\t<member name="data_capture_file_type" type="sint32">0</member>
\t\t\t<member name="data_capture_dir" type="string"></member>
\t\t\t<member name="data_absolute_time" type="sint32">0</member>
\t\t\t<member name="name" type="string">{scope_name}</member>
\t\t\t<member name="href" type="string"/>
\t\t\t<member name="watch_variables" type="CObListEx">{scope_vars_list_id}</member>
\t\t\t<member name="watch_functions" type="CObListEx">ObjId0005</member>
\t\t\t<member name="child_items" type="CObList">{scope_graphs_list_id}</member>
\t\t\t<member name="cell_format" type="CPrjItemBlock_CellFormat">ObjId0017</member>
\t\t\t<member name="column_info" type="CObArrayEx">ObjId0018</member>
\t\t\t<member name="variable_info" type="CMapObToObEx">{scope_varinfo_map_id}</member>
\t\t\t<member name="show_grid" type="sint32">1</member>
\t\t\t<member name="show_bar" type="sint32">1</member>
\t\t\t<member name="ena_row_sizing" type="sint32">1</member>
\t\t\t<member name="ena_col_sizing" type="sint32">1</member>
\t\t\t<member name="ena_col_swapping" type="sint32">1</member>
\t\t\t<member name="ena_inplace_params" type="sint32">1</member>
\t\t\t<member name="ena_inplace_values" type="sint32">1</member>
\t\t\t<member name="scope" type="CPrjItemScope_ScopeCfg">{scope_cfg_id}</member>
\t\t\t<sub name="watch_views" length="0"/>
\t\t</object>"""

# Scope 的变量列表
_SCOPE_VARS_LIST_XML = """\
\t\t<object name="{list_id}" type="CObList">
{entries}
\t\t</object>"""

# Scope 的 variable_info 映射
_SCOPE_VARINFO_MAP_XML = """\
\t\t<object name="{map_id}" type="CMapObToObEx">
{entries}
\t\t</object>"""

# Scope 图形配置
_SCOPE_CFG_XML = """\
\t\t<object name="{cfg_id}" type="CPrjItemScope_ScopeCfg">
\t\t\t<member name="x_axis" type="CPrjItemScope_XAxisCfg">{xaxis_id}</member>
\t\t\t<member name="y_axes" type="CObListEx">{yaxes_list_id}</member>
\t\t\t<member name="show_legend" type="sint32">1</member>
\t\t\t<member name="legend_position" type="sint32">0</member>
\t\t\t<member name="graph_backcolor" type="uint32">0xFFFFFF</member>
\t\t\t<member name="graph_forecolor" type="uint32">0x0</member>
\t\t\t<member name="graph_grid_horz" type="sint32">1</member>
\t\t\t<member name="graph_grid_vert" type="sint32">1</member>
\t\t\t<member name="graph_grid_horz_color" type="uint32">0xC0C0C0</member>
\t\t\t<member name="graph_grid_vert_color" type="uint32">0xC0C0C0</member>
\t\t</object>"""

# X 轴配置
_XAXIS_CFG_XML = """\
\t\t<object name="{xaxis_id}" type="CPrjItemScope_XAxisCfg">
\t\t\t<member name="title" type="string">Time</member>
\t\t\t<member name="unit" type="string">s</member>
\t\t\t<member name="mode" type="sint32">1</member>
\t\t\t<member name="time_per_div" type="real64">{time_per_div}</member>
\t\t\t<member name="time_total" type="real64">{time_total}</member>
\t\t</object>"""

# Y 轴配置模板
_YAXIS_CFG_XML = """\
\t\t<object name="{yaxis_id}" type="CPrjItemScope_YAxisCfg">
\t\t\t<member name="title" type="string">{title}</member>
\t\t\t<member name="unit" type="string">{unit}</member>
\t\t\t<member name="min" type="real64">0.00000000e+00</member>
\t\t\t<member name="max" type="real64">1.00000000e+02</member>
\t\t\t<member name="auto_range" type="sint32">1</member>
\t\t\t<member name="log_scale" type="sint32">0</member>
\t\t\t<member name="color" type="uint32">{color}</member>
\t\t\t<member name="graph_vars" type="CObListEx">{graph_vars_list_id}</member>
\t\t</object>"""

# Y 轴列表
_YAXES_LIST_XML = """\
\t\t<object name="{list_id}" type="CObList">
{entries}
\t\t</object>"""

# Graph var (Y 轴上的变量绑定)
_GRAPH_VAR_XML = """\
\t\t<object name="{gv_id}" type="CPrjItemScope_GraphVar">
\t\t\t<member name="variable" type="CObject_ptr">{var_ref_id}</member>
\t\t\t<member name="var_color" type="uint32">{color}</member>
\t\t\t<member name="var_width" type="sint32">1</member>
\t\t\t<member name="var_style" type="sint32">0</member>
\t\t\t<member name="var_points" type="sint32">0</member>
\t\t</object>"""

# 颜色轮转表（用于不同曲线区分）
_SCOPE_COLORS = [
    "0xFF0000",  # 红
    "0x0000FF",  # 蓝
    "0x008000",  # 绿
    "0xFF8000",  # 橙
    "0x800080",  # 紫
    "0x008080",  # 青
    "0x800000",  # 深红
    "0x000080",  # 深蓝
]


def _generate_scope_config(scope_vars: list[str], variables: list[dict],
                           var_base_id: int, scope_base_id: int,
                           time_per_div: float = 0.01,
                           time_total: float = 0.1) -> tuple[str, int]:
    """生成 Scope/Oscilloscope 配置的 XML 片段.

    Args:
        scope_vars: 要放入示波器的变量名列表
        variables: 所有变量配置列表（用于查找 scope 变量的 ObjId）
        var_base_id: 变量的起始 ObjId
        scope_base_id: Scope 相关对象的起始 ObjId
        time_per_div: 示波器每格时间 (s)
        time_total: 示波器总时间窗口 (s)

    Returns:
        (xml_fragment, next_scope_obj_id)
    """
    if not scope_vars:
        return "", scope_base_id

    # 构建变量名到其 var ObjId 的映射
    var_name_to_obj_id: dict[str, str] = {}
    vid = var_base_id
    for v in variables:
        var_name_to_obj_id[v["var_name"]] = f"ObjId{vid:04d}"
        vid += 3

    # 只保留在 variables 列表中存在的 scope 变量
    valid_scope_vars = [v for v in scope_vars if v in var_name_to_obj_id]
    if not valid_scope_vars:
        return "", scope_base_id

    obj_id = scope_base_id
    parts: list[str] = []

    # ── X 轴配置 ──
    xaxis_id = f"ObjId{obj_id:04d}"
    obj_id += 1
    parts.append(_XAXIS_CFG_XML.format(
        xaxis_id=xaxis_id,
        time_per_div=f"{time_per_div:.8e}",
        time_total=f"{time_total:.8e}",
    ))

    # ── Y 轴：将所有 scope 变量放在同一个 Y 轴上（多曲线叠加） ──
    # 每个变量生成一个 GraphVar
    graph_var_ids: list[str] = []
    graph_var_entries: list[str] = []
    gv_list_id = f"ObjId{obj_id:04d}"
    obj_id += 1

    for i, sv in enumerate(valid_scope_vars):
        gv_id = f"ObjId{obj_id:04d}"
        obj_id += 1
        graph_var_ids.append(gv_id)
        color = _SCOPE_COLORS[i % len(_SCOPE_COLORS)]
        var_ref = var_name_to_obj_id[sv]
        graph_var_entries.append(_GRAPH_VAR_XML.format(
            gv_id=gv_id,
            var_ref_id=var_ref,
            color=color,
        ))

    # GraphVar 对象
    for gv_entry in graph_var_entries:
        parts.append(gv_entry)

    # GraphVar 列表对象
    gv_items = "\n".join(
        f'\t\t\t<member name="item{i}" type="CObject_ptr">{gv_id}</member>'
        for i, gv_id in enumerate(graph_var_ids)
    )
    graph_vars_list_xml = f"""\
\t\t<object name="{gv_list_id}" type="CObList">
{gv_items}
\t\t</object>"""
    parts.append(graph_vars_list_xml)

    # ── Y 轴对象（单个，包含所有变量） ──
    yaxis_id = f"ObjId{obj_id:04d}"
    obj_id += 1
    parts.append(_YAXIS_CFG_XML.format(
        yaxis_id=yaxis_id,
        title=",".join(valid_scope_vars),
        unit="",
        color="0x000000",
        graph_vars_list_id=gv_list_id,
    ))

    # ── Y 轴列表 ──
    yaxes_list_id = f"ObjId{obj_id:04d}"
    obj_id += 1
    parts.append(_YAXES_LIST_XML.format(
        list_id=yaxes_list_id,
        entries=f'\t\t\t<member name="item0" type="CObject_ptr">{yaxis_id}</member>',
    ))

    # ── Scope 配置对象 ──
    scope_cfg_id = f"ObjId{obj_id:04d}"
    obj_id += 1
    parts.append(_SCOPE_CFG_XML.format(
        cfg_id=scope_cfg_id,
        xaxis_id=xaxis_id,
        yaxes_list_id=yaxes_list_id,
    ))

    # ── Scope 的变量列表（引用 scope 中的变量 ObjId） ──
    scope_vars_list_id = f"ObjId{obj_id:04d}"
    obj_id += 1
    scope_var_entries = "\n".join(
        f'\t\t\t<member name="item{i}" type="CObject_ptr">{var_name_to_obj_id[sv]}</member>'
        for i, sv in enumerate(valid_scope_vars)
    )
    parts.append(_SCOPE_VARS_LIST_XML.format(
        list_id=scope_vars_list_id,
        entries=scope_var_entries,
    ))

    # ── Scope 的 variable_info 映射 ──
    scope_varinfo_map_id = f"ObjId{obj_id:04d}"
    obj_id += 1
    scope_varinfo_entries_list: list[str] = []
    vid2 = var_base_id
    for i, sv in enumerate(valid_scope_vars):
        var_ref = var_name_to_obj_id[sv]
        # VarInfo ID 是 var_obj_id + 1
        var_obj_num = int(var_ref.replace("ObjId", ""))
        varinfo_ref = f"ObjId{var_obj_num + 1:04d}"
        scope_varinfo_entries_list.append(
            f'\t\t\t<member name="key{i}" type="CObject_ptr">{var_ref}</member>'
        )
        scope_varinfo_entries_list.append(
            f'\t\t\t<member name="value{i}" type="CObject_ptr">{varinfo_ref}</member>'
        )
    parts.append(_SCOPE_VARINFO_MAP_XML.format(
        map_id=scope_varinfo_map_id,
        entries="\n".join(scope_varinfo_entries_list),
    ))

    # ── Scope 主对象 ──
    scope_graphs_list_id = f"ObjId{obj_id:04d}"
    obj_id += 1
    scope_id = f"ObjId{obj_id:04d}"
    obj_id += 1

    parts.append(_SCOPE_OBJECT_XML.format(
        scope_id=scope_id,
        scope_name="Scope",
        scope_vars_list_id=scope_vars_list_id,
        scope_graphs_list_id=scope_graphs_list_id,
        scope_varinfo_map_id=scope_varinfo_map_id,
        scope_cfg_id=scope_cfg_id,
    ))

    return "\n".join(parts), obj_id


def _inject_scope_into_template(content: str, scope_xml: str) -> str:
    """将 Scope 配置注入模板的 objects 区域和 watch_views/child_items."""
    if not scope_xml.strip():
        return content

    # 注入 scope 对象到 </objects> 之前
    content = content.replace("\t</objects>", scope_xml + "\n\t</objects>")

    # 找到 scope 主对象的 ObjId
    scope_id_match = re.search(r'<object name="(ObjId\d{4})" type="CPrjItemScope">', scope_xml)
    if scope_id_match:
        scope_id = scope_id_match.group(1)

        # 更新 watch_views（从自闭合标签变为包含 item0 的完整标签）
        def _replace_watch_views(m: re.Match) -> str:
            return (m.group(1) + "1\">\n"
                    + '\t\t\t\t<item0 type="CObject_ptr">' + scope_id + '</item0>\n'
                    + '\t\t\t</sub>')

        content = _WATCH_VIEWS_EMPTY_RE.sub(_replace_watch_views, content)

        # 更新 child_items（ObjId0016 — 从自闭合展开）
        content = _expand_child_items(content, scope_id)

    return content


def generate_pmpx(
    output_path: Path,
    elf_path: str,
    device: str,
    template_path: Path | None = None,
    variables: list[str] | None = None,
    scope_vars: list[str] | None = None,
    sample_rate_hz: int = 1000,
    jlink_speed_khz: int = 4000,
    recorder_dir: str | None = None,
    scope_time_per_div: float = 0.01,
    scope_time_total: float = 0.1,
) -> dict[str, Any]:
    """生成 .pmpx 项目文件.

    Args:
        output_path: 输出 .pmpx 文件路径
        elf_path: 带符号的 ELF/AXF 文件绝对路径
        device: J-Link 目标设备名
        template_path: 参考模板路径
        variables: 预置变量名列表
        scope_vars: 要放入 Scope/Oscilloscope 的变量名列表
        sample_rate_hz: Recorder 采样率 (Hz)
        jlink_speed_khz: J-Link SWD 速度 (kHz)
        recorder_dir: Recorder 数据保存目录
        scope_time_per_div: 示波器每格时间 (s), 默认 10ms
        scope_time_total: 示波器总时间窗口 (s), 默认 100ms

    Returns:
        {"status": ..., "path": ..., "vars_count": ..., "scope_vars_count": ..., "error": ...}
    """
    ref = template_path or _DEFAULT_TEMPLATE
    if not ref.is_file():
        return {
            "status": "failure",
            "path": "",
            "vars_count": 0,
            "scope_vars_count": 0,
            "error": f"参考模板不存在: {ref}",
        }

    # 读取模板
    try:
        content = ref.read_text(encoding="utf-8")
    except Exception as e:
        return {
            "status": "failure",
            "path": "",
            "vars_count": 0,
            "scope_vars_count": 0,
            "error": f"无法读取模板 {ref}: {e}",
        }

    # 1. 替换 ELF 文件路径
    subs = 0

    def _replace_file_name(m: re.Match) -> str:
        nonlocal subs
        subs += 1
        return m.group(1) + elf_path + m.group(2)

    content = _FILE_NAME_RE.sub(_replace_file_name, content)
    if subs == 0:
        return {
            "status": "failure",
            "path": "",
            "vars_count": 0,
            "scope_vars_count": 0,
            "error": "模板中未找到 file_name 成员，请确认模板是 FreeMASTER 3.x 导出的 .pmpx",
        }

    # 2. 替换 Recorder 数据保存目录
    if recorder_dir:
        def _replace_capture_dir(m: re.Match) -> str:
            return m.group(1) + recorder_dir + m.group(2)
        content = _DATA_CAPTURE_DIR_RE.sub(_replace_capture_dir, content)

    # 3. 变量注入
    variables = variables or []
    scope_vars = scope_vars or []

    # 构建变量配置字典
    var_configs = [_make_variable_entry(var_name=v) for v in variables]
    # scope_vars 中可能在 variables 之外额外指定，补充进去
    for sv in scope_vars:
        if sv not in variables:
            var_configs.append(_make_variable_entry(var_name=sv))
            variables.append(sv)

    base_id = _GEN_OBJ_ID_BASE

    if var_configs:
        # 剥离旧变量对象
        content = _strip_old_variables(content)

        # 生成新变量对象 XML
        var_objects_xml, next_var_id = _generate_variable_objects(var_configs, base_id)

        # 注入到 objects 区域（</objects> 之前）
        content = content.replace("\t</objects>", var_objects_xml + "\n\t</objects>")

        # 注入到三个列表对象
        content = _inject_variables_into_lists(content, var_configs, base_id)
    else:
        next_var_id = base_id

    vars_count = len(variables)
    scope_vars_count = len(scope_vars)

    # 4. Scope/Oscilloscope 配置
    if scope_vars:
        scope_xml, next_scope_id = _generate_scope_config(
            scope_vars=scope_vars,
            variables=var_configs,
            var_base_id=base_id,
            scope_base_id=next_var_id + 100,  # scope 对象从变量对象之后 100 开始
            time_per_div=scope_time_per_div,
            time_total=scope_time_total,
        )
        content = _inject_scope_into_template(content, scope_xml)

    # 5. 备份已存在的输出
    if output_path.exists():
        backup = output_path.with_suffix(".pmpx.bak")
        shutil.copy2(output_path, backup)

    # 6. 写入
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")

    return {
        "status": "success",
        "path": str(output_path.resolve()),
        "vars_count": vars_count,
        "scope_vars_count": scope_vars_count,
        "error": None,
    }


def print_result(result: dict[str, Any]) -> None:
    """打印生成结果."""
    if result["status"] == "success":
        print(f"✅ .pmpx 已生成: {result['path']}")
        print(f"   ELF 引用已替换")
        if result["vars_count"] > 0:
            print(f"   预置变量: {result['vars_count']} 个")
            if result.get("scope_vars_count", 0) > 0:
                print(f"   Scope 变量: {result['scope_vars_count']} 个")
        else:
            print("   提示: 未指定变量，请在 FreeMASTER GUI 中手动添加")
        print("   提示: 通信配置（J-Link/SWD/设备）请在 FreeMASTER GUI 中设置")
    else:
        print(f"❌ 生成失败: {result['error']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=".pmpx 项目文件生成器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --elf build/app.axf --device GD32F450IK --output project.pmpx
  %(prog)s --elf build/app.axf --device GD32F450IK --vars adc_value,pid_output
  %(prog)s --elf build/app.axf --device GD32F450IK --vars adc_value,pid_output --scope-vars adc_value
  %(prog)s --elf build/app.elf --device STM32F407VG --recorder-dir D:\\Data\\logs
  %(prog)s --elf build/app.elf --device STM32F407VG --template my_template.pmpx
        """,
    )
    parser.add_argument("--elf", required=True, help="带符号的 ELF/AXF 文件路径")
    parser.add_argument("--device", required=True, help="J-Link 目标设备名（如 GD32F450IK）")
    parser.add_argument("--output", default=None, help="输出 .pmpx 路径（默认 <device>.pmpx）")
    parser.add_argument("--vars", default="", help="预置变量名，逗号分隔（注入到 Variable Grid）")
    parser.add_argument("--scope-vars", default="",
                        help="Scope/Oscilloscope 变量名，逗号分隔（自动包含在 --vars 中）")
    parser.add_argument("--scope-time-per-div", type=float, default=0.01,
                        help="示波器每格时间，单位 s（默认 0.01 = 10ms/div）")
    parser.add_argument("--scope-time-total", type=float, default=0.1,
                        help="示波器时间窗口，单位 s（默认 0.1 = 100ms）")
    parser.add_argument("--sample-rate", type=int, default=1000,
                        help="Recorder 采样率 Hz（默认 1000）")
    parser.add_argument("--jlink-speed", type=int, default=4000,
                        help="J-Link SWD 速度 kHz（默认 4000）")
    parser.add_argument("--recorder-dir", default=None,
                        help="Recorder 数据保存目录（默认使用模板中的路径）")
    parser.add_argument("--template", default=None,
                        help="参考模板路径（默认 references/_ref_freemaster_template.pmpx）")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    elf_path = str(Path(args.elf).resolve())
    if not Path(elf_path).exists():
        print(f"❌ ELF 文件不存在: {elf_path}")
        return 1

    output = Path(args.output) if args.output else Path.cwd() / f"{args.device}.pmpx"
    template = Path(args.template) if args.template else None

    variables = [v.strip() for v in args.vars.split(",") if v.strip()] if args.vars else []
    scope_vars = [v.strip() for v in args.scope_vars.split(",") if v.strip()] if args.scope_vars else []

    result = generate_pmpx(
        output_path=output,
        elf_path=elf_path,
        device=args.device,
        template_path=template,
        variables=variables,
        scope_vars=scope_vars,
        sample_rate_hz=args.sample_rate,
        jlink_speed_khz=args.jlink_speed,
        recorder_dir=args.recorder_dir,
        scope_time_per_div=args.scope_time_per_div,
        scope_time_total=args.scope_time_total,
    )

    print_result(result)
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
