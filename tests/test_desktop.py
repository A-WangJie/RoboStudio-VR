"""Real Electron integration, with temporary config/profile and no hardware."""
import json
import os
from pathlib import Path
import subprocess
import unittest
from urllib.request import urlopen
from urllib.error import URLError

ROOT = Path(__file__).resolve().parents[1]


class DesktopTests(unittest.TestCase):
    def test_window_backend_settings_and_workspace(self):
        if not (ROOT / 'desktop/runtime/electron').exists():
            self.skipTest('Electron runtime is not installed')
        if not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY'):
            self.skipTest('A graphical desktop session is required')
        command = ['bash', 'start-desktop.sh', '--s1-smoke-test']
        if os.environ.get('DISPLAY'):
            command.append('--ozone-platform=x11')
        result = subprocess.run(command, cwd=ROOT,
                                text=True, capture_output=True, timeout=75)
        self.assertEqual(result.returncode, 0, (result.stdout + result.stderr)[-7000:])
        report_path = ROOT / 'artifacts/reports/desktop-checks.json'
        report = json.loads(report_path.read_text())
        self.assertTrue(report['ok'])
        with self.assertRaises(ProcessLookupError):
            os.kill(report['backendPID'], 0)
        with self.assertRaises((URLError, ConnectionError, TimeoutError)):
            urlopen(report['backendURL'] + '/api/sim/state', timeout=2)
        report['checks'].append('Closing a running desktop stops the owned backend and releases its port')
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    unittest.main()
