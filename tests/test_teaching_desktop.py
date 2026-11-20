"""Validate teaching configuration via real Electron IPC in a temporary profile."""
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class TeachingDesktopTests(unittest.TestCase):
    def test_teaching_config_ipc(self):
        if not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY'):
            self.skipTest('Desktop session required')
        env = dict(os.environ, S1_TEACHING_CHECK='1')
        command = ['bash', 'start-desktop.sh', '--s1-smoke-test']
        if os.environ.get('DISPLAY'): command.append('--ozone-platform=x11')
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=45)
        self.assertEqual(result.returncode, 0, (result.stdout+result.stderr)[-5000:])
        report = json.loads((ROOT/'artifacts/reports/teaching-desktop-checks.json').read_text())
        self.assertTrue(report['ok'])
        self.assertEqual(len(report['checks']), 3)
        with self.assertRaises(ProcessLookupError): os.kill(report['backendPID'], 0)


if __name__ == '__main__': unittest.main()
