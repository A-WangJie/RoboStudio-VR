"""Read-only S1 SDK acquisition in an isolated, time-bounded subprocess."""
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time

PREFIX = 'ROBODATA_SAMPLE '


def validate_options(options):
    devices = options.get('devices')
    if not isinstance(devices, list) or not 1 <= len(devices) <= 2:
        raise ValueError('请先在示教模块保存一至两个主臂 CAN 接口')
    if any(not isinstance(d, str) or not re.fullmatch(r'[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,14}', d) for d in devices) or len(set(devices)) != len(devices):
        raise ValueError('主臂 CAN 接口无效或重复')
    rate = options.get('rateHz', 30)
    timeout = options.get('timeoutMs', 1000)
    if type(rate) is not int or not 1 <= rate <= 100 or type(timeout) is not int or not 100 <= timeout <= 5000:
        raise ValueError('采样率须为 1–100 Hz，超时须为 100–5000 ms')
    return dict(devices=devices, rateHz=rate, timeoutMs=timeout)


def validate_sample(sample, devices):
    if not isinstance(sample, dict) or sample.get('source') != 'teaching-sdk':
        raise ValueError('示教 SDK 数据格式错误')
    arms = sample.get('arms')
    if not isinstance(arms, list) or len(arms) != len(devices):
        raise ValueError('示教 SDK 臂数量不符')
    for arm, device in zip(arms, devices):
        if not isinstance(arm, dict) or arm.get('device') != device:
            raise ValueError('示教 SDK 接口不符')
        q = arm.get('jointsRad')
        if not isinstance(q, list) or len(q) != 6 or not all(type(v) in (int, float) and math.isfinite(v) for v in q):
            raise ValueError('示教 SDK 未返回六轴有效关节角')
    return sample


class TeachingCapture:
    def __init__(self, recorder, command=None):
        self.recorder = recorder
        self.command = command or [os.environ.get('ROBODATA_SDK_PYTHON', sys.executable), '-u', str(Path(__file__).with_name('teaching_reader.py'))]
        self.lock = threading.RLock()
        self.process = None
        self.thread = None
        self.ready = threading.Event()
        self.error = ''
        self.latest = None
        self.received = 0

    def snapshot(self):
        with self.lock:
            return dict(status='reading' if self.process and self.process.poll() is None else 'disconnected',
                        error=self.error, latest=self.latest,
                        ageMs=round((time.monotonic()-self.received)*1000) if self.received else None)

    def start(self, task, options):
        config = validate_options(options)
        with self.lock:
            if self.process or self.recorder.snapshot()['active']:
                raise ValueError('正在采集，请先结束当前任务')
            self.error = ''; self.latest = None; self.received = 0; self.ready = threading.Event()
            self.process = subprocess.Popen(self.command+[json.dumps(config)], stdin=subprocess.DEVNULL,
                                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            self.thread = threading.Thread(target=self._read, args=(self.process, config, self.ready), daemon=True)
            self.thread.start()
        if not self.ready.wait(10):
            self.stop('sdk_start_timeout')
            raise ValueError('示教 SDK 初始化超时，未开始采集')
        with self.lock:
            if self.error or not self.process or self.process.poll() is not None or not self.latest:
                error = self.error or '示教 SDK 未返回有效读数'
            else:
                try:
                    self.recorder.start(task, dict(source='teaching-sdk', simulationOnly=False,
                        robot='S1 V1', **config, jointOrder=['J1','J2','J3','J4','J5','J6'],
                        readOnly=True, freshness='CAN bus activity; SDK exposes cached angles without per-joint timestamps'))
                    self.recorder.frame(self.latest, None, None)
                    return self.recorder.snapshot()
                except Exception:
                    self.stop('recording_start_failed')
                    raise
        self.stop('sdk_error')
        raise ValueError(error)

    def _read(self, process, config, ready):
        # A watchdog also covers native constructors/getters that never return.
        def watchdog():
            while process.poll() is None:
                time.sleep(.1)
                with self.lock:
                    overdue = self.received and time.monotonic()-self.received > config['timeoutMs']/1000 + .5
                    if overdue:
                        self.error = '示教 SDK 数据超时，采集已结束'
                        process.kill()
        threading.Thread(target=watchdog, daemon=True).start()
        try:
            for line in process.stdout:
                if line.startswith('ROBODATA_ERROR '):
                    raise ValueError(line[len('ROBODATA_ERROR '):].strip())
                if not line.startswith(PREFIX):
                    continue  # Native library may log to stdout.
                sample = validate_sample(json.loads(line[len(PREFIX):]), config['devices'])
                with self.lock:
                    self.latest = sample; self.received = time.monotonic()
                    recording = self.recorder.snapshot()
                    if recording['active'] and recording.get('source') == 'teaching-sdk':
                        self.recorder.frame(sample, None, None)
                        if not self.recorder.snapshot()['active']:
                            raise RuntimeError(self.recorder.snapshot()['error'] or '采集文件已关闭')
                    ready.set()
            with self.lock:
                if self.process is process and not self.error:
                    self.error = '示教 SDK 读取中断，采集已结束'
        except Exception as error:
            with self.lock: self.error = str(error)
            if process.poll() is None: process.kill()
        finally:
            process.wait()
            process.stdout.close()
            with self.lock:
                if self.process is process:
                    if self.recorder.snapshot().get('source') == 'teaching-sdk':
                        self.recorder.stop('sdk_disconnected')
                    self.process = None
                ready.set()

    def stop(self, reason='operator'):
        with self.lock:
            process = self.process
            self.process = None
            if self.recorder.snapshot().get('source') == 'teaching-sdk':
                self.recorder.stop(reason)
            if process and process.poll() is None: process.kill()
        if process:
            process.wait(timeout=3)
        return self.recorder.snapshot()
