"""Observe RS cached feedback over HTTP; never open CAN or send control requests."""
import argparse
import csv
from datetime import datetime
import json
import math
from pathlib import Path
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--duration', type=float, default=900)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    url = f'http://127.0.0.1:{args.port}/api/hardware/mouse/state'
    started = time.monotonic()
    stats = {str(n): dict(samples=0, peakFeedbackDegS=0., peakDifferenceDegS=0.,
                         peakWindowDegS=0., movingSamples=0) for n in range(1, 7)}
    previous, windows, seen = {}, {}, {}
    errors = 0
    batches = 0
    last_summary = 0.
    status = 'waiting-for-active-mouse-control'
    fields = ['observedAt', 'receivedAtMs', 'arm', 'node', 'positionDeg',
              'feedbackVelocityDegS', 'differenceVelocityDegS', 'windowVelocityDegS',
              'configuredSpeedDegS', 'torqueNm', 'mosTemperatureC', 'coilTemperatureC']
    print(str(args.output), flush=True)
    with (args.output/'joints.csv').open('w', newline='') as csv_file, \
            (args.output/'feedback.jsonl').open('w') as raw:
        writer = csv.DictWriter(csv_file, fieldnames=fields)
        writer.writeheader()
        while time.monotonic()-started < args.duration and not (args.output/'STOP').exists():
            tick = time.monotonic()
            try:
                with urllib.request.urlopen(url, timeout=1.) as response:
                    state = json.load(response)
                active = state.get('active') is True and state.get('owner') == 'mouse'
                status = 'recording' if active else 'waiting-for-active-mouse-control'
                if not active:
                    previous.clear()
                    windows.clear()
                accepted = []
                for sample in state.get('samples', []) if active else []:
                    n = sample.get('node')
                    stamp = sample.get('receivedAtMs')
                    key = (state.get('armId'), state.get('device'), n)
                    if n not in range(1, 7) or type(stamp) not in (int, float):
                        continue
                    if not 0 <= time.time()*1000-stamp <= 250 or stamp <= seen.get(key, 0):
                        continue
                    seen[key] = stamp
                    if not sample.get('positionValid') or sample.get('fault') or not sample.get('enabled'):
                        previous.pop(key, None)
                        windows.pop(key, None)
                        continue
                    position = sample['positionDeg']
                    velocity = math.degrees(sample['velocityRadS'])
                    if not all(math.isfinite(v) for v in (position, velocity)):
                        continue
                    derivative = ''
                    old = previous.get(key)
                    if old and 0 < stamp-old[0] <= 250:
                        derivative = (position-old[1])*1000/(stamp-old[0])
                    else:
                        windows[key] = []
                    previous[key] = (stamp, position)
                    history = windows.setdefault(key, [])
                    history.append((stamp, position))
                    while history and stamp-history[0][0] > 500:
                        history.pop(0)
                    window_velocity = ''
                    if stamp-history[0][0] >= 250:
                        window_velocity = (position-history[0][1])*1000/(stamp-history[0][0])
                    observed = datetime.now().astimezone().isoformat(timespec='milliseconds')
                    writer.writerow(dict(observedAt=observed, receivedAtMs=stamp, arm=state.get('armId'),
                                         node=n, positionDeg=position, feedbackVelocityDegS=velocity,
                                         differenceVelocityDegS=derivative, windowVelocityDegS=window_velocity,
                                         configuredSpeedDegS=state.get('speedDegS'), torqueNm=sample.get('torqueNm'),
                                         mosTemperatureC=sample.get('mosTemperatureC'),
                                         coilTemperatureC=sample.get('coilTemperatureC')))
                    item = stats[str(n)]
                    item['samples'] += 1
                    item['peakFeedbackDegS'] = max(item['peakFeedbackDegS'], abs(velocity))
                    if derivative != '':
                        item['peakDifferenceDegS'] = max(item['peakDifferenceDegS'], abs(derivative))
                    if window_velocity != '':
                        item['peakWindowDegS'] = max(item['peakWindowDegS'], abs(window_velocity))
                        if abs(window_velocity) > .5:
                            item['movingSamples'] += 1
                    accepted.append(sample)
                if accepted:
                    batches += 1
                    raw.write(json.dumps(dict(observedAt=time.time(), arm=state.get('armId'),
                                              device=state.get('device'), speedDegS=state.get('speedDegS'),
                                              feedbackStatus=state.get('feedbackStatus'), samples=accepted),
                                         ensure_ascii=False)+'\n')
                    csv_file.flush()
                    raw.flush()
            except Exception as error:
                errors += 1
                status = 'read-error: '+str(error)
                previous.clear()
                windows.clear()
            if tick-last_summary >= 1:
                report = dict(status=status, elapsedSeconds=round(tick-started, 1),
                              updatedAt=datetime.now().astimezone().isoformat(), batches=batches,
                              readErrors=errors, joints=stats, method='RS cached motor feedback, GET only; '
                              'deduplicated by motor receive timestamp; no CAN access; '
                              'angle differences excluded across gaps >250ms; window 250–500ms; '
                              'these observations do not establish rated speed or safe maximum')
                temporary = args.output/'summary.tmp'
                temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2))
                temporary.replace(args.output/'summary.json')
                last_summary = tick
            time.sleep(max(0., .05-(time.monotonic()-tick)))
    report['status'] = 'finished'
    report['finishReason'] = 'stop-request' if (args.output/'STOP').exists() else 'duration-limit'
    (args.output/'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
