"""Publication boundaries, local configuration and USB selection. No real ADB."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

RD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RD / 'bridge'))
from adb_device import usb_serial
import paths

spec = importlib.util.spec_from_file_location('rd_export', RD / 'scripts/export-source.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ProjectLayoutTests(unittest.TestCase):
    def test_usb_selection_never_chooses_network_or_unauthorized_device(self):
        def run(devices):
            return lambda *a, **k: SimpleNamespace(returncode=0, stdout='List of devices attached\n'+devices, stderr='')
        with patch.dict(os.environ, {'QUEST_SERIAL': ''}):
            self.assertEqual(usb_serial(run('test-quest\tdevice\n192.0.2.1:5555\tdevice\n')), 'test-quest')
            for data in ('', 'test-quest\tunauthorized\n', '192.0.2.1:5555\tdevice\n'):
                with self.assertRaisesRegex(RuntimeError, '未发现'): usb_serial(run(data))
            with self.assertRaisesRegex(RuntimeError, '多个'):
                usb_serial(run('one\tdevice\ntwo\tdevice\n'))
        with patch.dict(os.environ, {'QUEST_SERIAL': 'chosen-quest'}):
            self.assertEqual(usb_serial(lambda *_: self.fail('must not scan')), 'chosen-quest')

    def test_config_override_applies_to_all_local_config(self):
        with patch.dict(os.environ, {'ROBODATA_DATA_DIR': '/tmp/rd-data', 'ROBODATA_CONFIG_DIR': '/tmp/rd-config', 'ROBODATA_RECORDINGS': '/tmp/rd-records'}):
            self.assertEqual(paths.local_dir(), Path('/tmp/rd-data'))
            self.assertEqual(paths.config_dir(), Path('/tmp/rd-config'))
            self.assertEqual(paths.recordings_dir(), Path('/tmp/rd-records'))

    def test_release_export_excludes_local_state_and_preserves_unity_guids(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'rd';root.mkdir()
            samples={'README.md':'hello', 'config/connection.json':'private-token',
                'config/connection.example.json':'{"mode":"usb","token":""}',
                '.local/config/wireless-adb.json':'private-ip', 'artifacts/apk/RoboData.apk':'binary',
                'QuestControllerClient/Library/secret':'cache',
                'QuestControllerClient/Assets/Main.cs':'source',
                'QuestControllerClient/Assets/Main.cs.meta':'guid: 1234',
                'QuestControllerClient/ProjectSettings/ProjectSettings.asset':'  cloudProjectId: personal\n  organizationId: account\n  productName: RoboData\n'}
            for name,data in samples.items():
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(data)
            output=Path(temp)/'release';manifest=release.export(root,output)
            names={item['path'] for item in manifest['files']}
            self.assertNotIn('config/connection.json',names)
            self.assertFalse(any('Library/' in name or name.startswith(('.local/','artifacts/')) for name in names))
            self.assertEqual((output/'QuestControllerClient/Assets/Main.cs.meta').read_text(),'guid: 1234')
            self.assertNotIn('personal',(output/'QuestControllerClient/ProjectSettings/ProjectSettings.asset').read_text())
            self.assertIn('personal',(root/'QuestControllerClient/ProjectSettings/ProjectSettings.asset').read_text())
            with self.assertRaises(ValueError):release.export(root,output)
            with self.assertRaises(ValueError):release.export(root,root/'nested')
