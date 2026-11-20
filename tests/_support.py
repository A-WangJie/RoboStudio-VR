"""Portable tooling and generated-output paths for local integration checks."""
import json
import os
from pathlib import Path
import shutil
import unittest
from backend.paths import artifacts_dir,config_dir

def node_binary():
 value=os.environ.get('NODE_BINARY') or shutil.which('node')
 if not value:
  p=config_dir()/'runtime.json'
  if p.is_file(): value=json.loads(p.read_text()).get('nodeBinary')
 if not value or not (shutil.which(value) or Path(value).is_file()):
  raise unittest.SkipTest('Node.js unavailable; set NODE_BINARY')
 return str(value)

def prepare_artifacts(root=None):
 for name in ('reports','screenshots'): (artifacts_dir()/name).mkdir(parents=True,exist_ok=True)
