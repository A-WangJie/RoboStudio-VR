"""Runtime locations shared by the web service and hardware adapters."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def data_dir():
    return Path(os.environ.get('S1_STUDIO_DATA_DIR', str(ROOT/'.local'))).expanduser()

def config_dir():
    return Path(os.environ.get('S1_STUDIO_CONFIG_DIR', str(data_dir()/'config'))).expanduser()

def log_dir():
    return Path(os.environ.get('S1_STUDIO_LOG_DIR', str(ROOT/'artifacts/logs'))).expanduser()

def artifacts_dir():
    return Path(os.environ.get('S1_STUDIO_ARTIFACTS_DIR', str(ROOT/'artifacts'))).expanduser()

def workspaces_dir():
    return Path(os.environ.get('S1_STUDIO_WORKSPACES_DIR', str(data_dir()/'workspaces'))).expanduser()
