"""Relative XYZ preview only: Unity right/up/forward -> robot forward/left/up."""
import math

class Mapping:
    def __init__(self, position_gain=1.):
        self.target = [0., 0., 0.]
        self.anchor_hand = None
        self.anchor_target = None
        self.require_release = True
        self.status = '等待有效右手输入'
        self.last_time = None
        self.last_sample_ms = None
        self.scale = float(position_gain)
        if type(position_gain) not in (int, float) or not math.isfinite(position_gain) or not .25 <= position_gain <= 3:
            raise ValueError("三轴位移比例必须在 0.25～3 之间")
        self.position_gain = float(position_gain)
        self.clutch_id = 0

    def update(self, packet, valid, now):
        # Sender intervals survive Wi-Fi batching; receive intervals do not.
        sample_ms = packet.get('timeMs') if packet else None
        sample_dt = None
        if sample_ms is not None and self.last_sample_ms is not None:
            sample_dt = max(0., min(.1, (sample_ms-self.last_sample_ms)/1000.))
        self.last_sample_ms = sample_ms
        h = packet.get('right', {}) if packet else {}
        if not valid or not packet or packet.get('source') != 'quest' or not packet.get('focused') or not h.get('tracked'):
            self.require_release = True
            self.anchor_hand = None
            self.last_time = None
            self.status = '输入无效 · 保持目标，恢复后请先松开握键'
            return self.snapshot()
        grip = h['grip']
        if grip < .3:
            self.require_release = False
            self.anchor_hand = None
            self.last_time = now
            self.status = '已就绪 · 按住右握键移动预览目标'
            return self.snapshot()
        if self.require_release:
            self.status = '请先松开右握键'
            return self.snapshot()
        if self.anchor_hand is None:
            if grip < .7:
                return self.snapshot()
            self.clutch_id += 1
            self.anchor_hand = list(h['position'])
            self.anchor_target = list(self.target)
            self.last_time = now
        delta = [a-b for a,b in zip(h['position'], self.anchor_hand)]
        # A large tracking discontinuity requires a deliberate release/regrip.
        if math.sqrt(sum(v*v for v in delta)) > .8:
            return self.update(None, False, now)
        mapped = [delta[2], -delta[0], delta[1]]
        gains = [self.scale]*3
        limits = [.6]*3
        desired = [max(-limit, min(limit, a+gain*d)) for a,d,gain,limit in zip(self.anchor_target, mapped,gains,limits)]
        dt = sample_dt if sample_dt is not None else max(0., min(.1, now-self.last_time))
        step = [a-b for a,b in zip(desired, self.target)]
        length = math.sqrt(sum(v*v for v in step))
        fraction = min(1., .4*dt/length) if length else 1.
        self.target = [a+fraction*d for a,d in zip(self.target,step)]
        self.last_time = now
        self.status = '握键使能 · 三轴等比例目标'
        return self.snapshot()

    def snapshot(self):
        return dict(status=self.status, offsetMeters=list(self.target), scale=self.scale, positionGain=self.position_gain, limitsMeters=[.6,.6,.6],
                    active=self.anchor_hand is not None and not self.require_release,
                    releaseRequired=self.require_release, clutchId=self.clutch_id)
