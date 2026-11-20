"""Validated settings shared by the desktop launcher and simulation."""
import json
from pathlib import Path
import math

DEFAULTS = {
    'speed_rad_s': .6,
    'ik_position_tolerance_mm': .5,
    'ik_orientation_tolerance_deg': 1.,
    'collision_protection': True,
    'obstacle': False,
}
BOUNDS = {
    'speed_rad_s': (.01, 2.),
    'ik_position_tolerance_mm': (.01, 5.),
    'ik_orientation_tolerance_deg': (.01, 10.),
}


def validate_simulation(values):
    if not isinstance(values, dict):
        raise ValueError('simulation 设置必须为对象')
    result = {**DEFAULTS, **{key: values[key] for key in DEFAULTS if key in values}}
    for name, (minimum, maximum) in BOUNDS.items():
        value = result[name]
        if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
            raise ValueError(f'{name} 必须在 {minimum}–{maximum} 之间')
    for name in ('collision_protection', 'obstacle'):
        if type(result[name]) is not bool:
            raise ValueError(name + ' 必须为布尔值')
    return result


def load_settings(path):
    if path is None:
        return dict(DEFAULTS)
    document = json.loads(Path(path).read_text())
    if not isinstance(document, dict) or document.get('version') != 1:
        raise ValueError('配置文件版本无效，需要 version: 1')
    return validate_simulation(document.get('simulation', {}))
