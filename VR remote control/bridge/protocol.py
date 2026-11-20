"""Shared Quest telemetry schema; validation has no device side effects."""
import math

def validate(p):
    if not isinstance(p, dict) or p.get('version') != 1 or p.get('source') not in ('quest', 'simulated'):
        raise ValueError('protocol/source')
    if type(p.get('seq')) is not int or p['seq'] < 0 or type(p.get('focused')) is not bool:
        raise ValueError('sequence/focus')
    def number(x):
        return type(x) in (int, float) and math.isfinite(x)
    if not number(p.get('timeMs')) or p['timeMs'] < 0:
        raise ValueError('timestamp')
    for side in ('left', 'right'):
        h = p.get(side, {})
        if not isinstance(h, dict):
            raise ValueError(side + '.object')
        for k in ('connected', 'tracked', 'primary', 'secondary'):
            if type(h.get(k)) is not bool:
                raise ValueError(side + '.' + k)
        if h['tracked'] and (not h['connected'] or not p['focused']):
            raise ValueError('inconsistent tracking')
        for k, n in (('position', 3), ('rotation', 4), ('stick', 2)):
            v = h.get(k)
            if not isinstance(v, list) or len(v) != n or not all(number(x) for x in v):
                raise ValueError(side + '.' + k)
        if h['tracked'] and not .9 < sum(x*x for x in h['rotation']) < 1.1:
            raise ValueError('quaternion norm')
        for k in ('trigger', 'grip'):
            if not number(h.get(k)) or not 0 <= h[k] <= 1:
                raise ValueError(side + '.' + k)
    if type(p.get('uiInteracting',False)) is not bool: raise ValueError('uiInteracting')
    return p

