"""Extension installer has no SDK initialization or real CAN operations."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('dk_sdk_install',ROOT/'tools/install_s1_extensions.py')
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)

class ExtensionInstallTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.sdk=Path(self.tmp.name);self.pkg=self.sdk/'src/S1_SDK';self.pkg.mkdir(parents=True)
  (self.pkg/'__init__.py').write_text('raise RuntimeError("must never import SDK during installation")')
 def test_preview_does_not_write(self):
  installer.install(self.sdk)
  self.assertEqual([p.name for p in self.pkg.iterdir()],['__init__.py'])
 def test_apply_is_repeatable_and_keeps_upstream_untouched(self):
  original=(self.pkg/'__init__.py').read_bytes()
  installer.install(self.sdk,True);installer.install(self.sdk,True)
  self.assertEqual((self.pkg/'__init__.py').read_bytes(),original)
  self.assertTrue((self.pkg/'safe_can.py').is_file())
 def test_conflict_preflight_prevents_partial_install(self):
  (self.pkg/'native_session.py').write_text('custom version')
  with self.assertRaises(ValueError):installer.install(self.sdk,True)
  self.assertFalse((self.pkg/'safe_can.py').exists())
 def test_rejects_symlink(self):
  (self.pkg/'safe_can.py').symlink_to(self.pkg/'__init__.py')
  with self.assertRaises(ValueError):installer.install(self.sdk,True)
