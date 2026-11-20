"""Validate hierarchical navigation and project file updates through real Electron IPC."""
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NavigationDesktopTests(unittest.TestCase):
    def test_navigation_and_project_identity(self):
        if not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY'):
            self.skipTest('Desktop session required')
        env = dict(os.environ, S1_NAVIGATION_CHECK='1')
        command = ['bash', 'start-desktop.sh', '--s1-smoke-test']
        if os.environ.get('DISPLAY'): command.append('--ozone-platform=x11')
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=45)
        self.assertEqual(result.returncode, 0, (result.stdout+result.stderr)[-5000:])
        report = json.loads((ROOT/'artifacts/reports/navigation-desktop-checks.json').read_text())
        self.assertTrue(report['ok'])
        self.assertGreaterEqual(len(report['checks']), 35)
        with self.assertRaises(ProcessLookupError): os.kill(report['backendPID'], 0)


if __name__ == '__main__': unittest.main()
