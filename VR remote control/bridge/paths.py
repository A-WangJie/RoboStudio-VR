"""Filesystem defaults shared by the bridge and the DK service launcher."""
import os
from pathlib import Path

RD_ROOT = Path(__file__).resolve().parents[1]


def local_dir():
    return Path(os.environ.get('ROBODATA_DATA_DIR', str(RD_ROOT / '.local'))).expanduser()


def config_dir():
    return Path(os.environ.get('ROBODATA_CONFIG_DIR', str(local_dir() / 'config'))).expanduser()


def log_dir():
    return Path(os.environ.get('ROBODATA_LOG_DIR', str(RD_ROOT / 'artifacts/logs'))).expanduser()


def recordings_dir():
    # DK continues to use its shared recordings directory. Standalone RD exports
    # use module-local storage instead of writing beside another repository.
    default = RD_ROOT.parent / 'recordings' if (RD_ROOT.parent / 'server.py').is_file() else local_dir() / 'recordings'
    return Path(os.environ.get('ROBODATA_RECORDINGS', str(default))).expanduser()
