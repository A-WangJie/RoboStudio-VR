"""Versioned, append-only telemetry episodes. No executable user filenames."""
import json
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

class Recorder:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.lock = threading.RLock()
        self.file = None
        self.info = dict(active=False, frames=0, file='', task='', error='', duration=0)
        self.started = 0

    def snapshot(self):
        with self.lock:
            result = dict(self.info)
            if self.file: result['duration'] = round(time.monotonic()-self.started, 1)
            return result

    def write(self, row):
        self.file.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+'\n')
        self.file.flush()

    def start(self, task, metadata):
        with self.lock:
            if self.file: raise ValueError('正在采集，请先结束当前任务')
            if not isinstance(task, str) or len(task) > 80: raise ValueError('任务名最长 80 字')
            task = task.strip() or '未命名任务'
            safe = re.sub(r'[^\w\-\u4e00-\u9fff]+', '_', task).strip('_')[:64] or 'task'
            name = safe+'_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid4().hex[:6]+'.jsonl'
            self.directory.mkdir(parents=True, exist_ok=True)
            self.file = (self.directory/name).open('x', encoding='utf8')
            self.started = time.monotonic()
            self.info = dict(active=True, frames=0, file=str(self.directory/name), task=task, error='', duration=0, source=metadata.get('source', ''))
            try:
                self.write(dict(type='header', protocol='robodata.episode', version=1,
                    startedAt=datetime.now(timezone.utc).isoformat(), task=task, units={'position':'m','rotation':'xyzw','joints':'rad'},
                    coordinateFrame=('S1 joint coordinates; device encoder zero' if metadata.get('source') == 'teaching-sdk' else 'Unity local tracking space; robot base frame'), metadata=metadata))
            except Exception:
                self.file.close(); self.file=None; self.info['active']=False
                raise
            return self.snapshot()

    def frame(self, packet, simulation, mapping):
        with self.lock:
            if not self.file: return
            try:
                self.write(dict(type='frame', receivedAtMs=int(time.time()*1000), elapsedMs=round((time.monotonic()-self.started)*1000),
                    input=packet, simulation=simulation, mapping=mapping))
                self.info['frames'] += 1
            except Exception as e:
                self.info['error']=str(e)
                self.file.close(); self.file=None; self.info['active']=False

    def stop(self, reason='operator'):
        with self.lock:
            if self.file:
                self.info['duration']=round(time.monotonic()-self.started, 1)
                try: self.write(dict(type='footer', frames=self.info['frames'], duration=self.info['duration'], reason=reason))
                finally: self.file.close(); self.file=None; self.info['active']=False
            return self.snapshot()
