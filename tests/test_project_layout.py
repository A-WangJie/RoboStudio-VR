"""Runtime relocation and source publication boundaries; no live hardware."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from backend import paths
from _support import node_binary

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('dk_release',ROOT/'scripts/export-source.py')
release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)

class LayoutTests(unittest.TestCase):
 def test_python_and_desktop_share_overridden_locations(self):
  env=dict(os.environ,S1_STUDIO_DATA_DIR='/tmp/dk-data',S1_STUDIO_CONFIG_DIR='/tmp/dk-config',
   S1_STUDIO_LOG_DIR='/tmp/dk-logs',S1_STUDIO_WORKSPACES_DIR='/tmp/dk-workspaces')
  script="console.log(JSON.stringify(require('./desktop/paths.cjs').runtimePaths(process.cwd())))"
  r=subprocess.run([node_binary(),'-e',script],cwd=ROOT,env=env,text=True,capture_output=True,check=True)
  actual=json.loads(r.stdout)
  with patch.dict(os.environ,env):
   self.assertEqual(str(paths.data_dir()),actual['data'])
   self.assertEqual(str(paths.config_dir()),actual['config'])
   self.assertEqual(str(paths.log_dir()),actual['logs'])
   self.assertEqual(str(paths.workspaces_dir()),actual['workspaces'])

 def test_export_has_sources_but_no_workstation_state(self):
  files={p.relative_to(ROOT).as_posix() for p in release.source_files(ROOT)}
  for name in ['server.py','LICENSE','integrations/s1_sdk_extensions/safe_can.py','app/vendor/THREE-LICENSE.txt',
   'config/settings.example.json','VR remote control/QuestControllerClient/Assets/Scenes/ControllerDiagnostics.unity.meta']:
   self.assertIn(name,files)
  self.assertFalse(any(name.startswith("app/assets/s1_v1/") for name in files))
  for name in files:
   self.assertFalse(any(part in release.SKIP for part in Path(name).parts),name)
   self.assertFalse(name.startswith(('recordings/','Gallery/','workspaces/','tmp_numcai/','var/')),name)
   if name.startswith('config/'): self.assertTrue(name.endswith('.example.json'),name)
  with tempfile.TemporaryDirectory() as temp:
   dest=Path(temp)/'source';m=release.export(ROOT,dest)
   self.assertGreater(len(m['files']),100)
   cloud=(dest/'VR remote control/QuestControllerClient/ProjectSettings/ProjectSettings.asset').read_text()
   for line in cloud.splitlines():
    if line.lstrip().startswith(('cloudProjectId:','organizationId:','projectName:')):
     self.assertFalse(line.split(':',1)[1].strip())
   with self.assertRaises(ValueError): release.export(ROOT,dest)
   with self.assertRaises(ValueError): release.export(ROOT,ROOT/'nested-output')
