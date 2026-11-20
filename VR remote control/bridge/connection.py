"""Local connection policy; wireless producers must present the pairing secret."""
import json
import secrets
import socket
import subprocess
import threading
from pathlib import Path

class Connection:
    def __init__(self, path):
        self.path=Path(path); self.lock=threading.RLock()
        self.mode='usb'; self.token=secrets.token_hex(4)
        if self.path.exists():
            saved=json.loads(self.path.read_text())
            self.mode=saved.get('mode','usb'); self.token=saved.get('token') or self.token
        self.save()
    def save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temp=self.path.with_suffix('.tmp');temp.write_text(json.dumps(dict(mode=self.mode,token=self.token)))
        temp.chmod(0o600);temp.replace(self.path)
    def snapshot(self):
        addresses=[]
        try:
            data=json.loads(subprocess.check_output(['ip','-j','-4','addr','show','up'],text=True,timeout=2))
            addresses=[a['local'] for link in data for a in link.get('addr_info',[]) if a.get('scope')=='global']
        except Exception: pass
        with self.lock: return dict(mode=self.mode,port=8766,addresses=addresses,pairingCode=self.token)
    def set(self, mode):
        if mode not in ('usb','wifi'): raise ValueError('连接方式必须为 USB 或 Wi-Fi')
        with self.lock: self.mode=mode; self.save()
    def permits(self, peer, token):
        with self.lock:
            return peer in ('127.0.0.1','::1') if self.mode=='usb' else secrets.compare_digest(str(token),self.token)
