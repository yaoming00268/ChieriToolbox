"""
osu!mania 皮肤调校工作台 - 渲染计算辅助
"""

from typing import Dict, List, Tuple


def get_mania_layout(section: Dict[str, str], keys_num: int) -> Tuple[List[float], float, bool, float]:
    """
    计算 Mania 舞台各列宽度、判定线高度与初始偏移
    返回: (col_widths, hit_position, upside_down, col_start)
    """
    col_width_str = section.get("ColumnWidth", "")
    col_widths = []

    if col_width_str:
        for val in col_width_str.split(","):
            val = val.strip()
            if val:
                try:
                    col_widths.append(float(val))
                except ValueError:
                    pass

    # 补齐默认宽度
    default_w = 60.0
    while len(col_widths) < keys_num:
        col_widths.append(default_w)
    col_widths = col_widths[:keys_num]

    try:
        hit_pos = float(section.get("HitPosition", "400"))
    except ValueError:
        hit_pos = 400.0

    upside_down = section.get("UpsideDown", "0").strip() == "1"

    total_stage_width = sum(col_widths)
    try:
        col_start = float(section.get("ColumnStart", str((640.0 - total_stage_width) / 2.0)))
    except ValueError:
        col_start = (640.0 - total_stage_width) / 2.0

    return col_widths, hit_pos, upside_down, col_start
