"""Install DK-owned extensions into an explicitly selected editable SDK checkout.

Does not import the SDK, open CAN, install dependencies, or alter upstream files.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]

def install(sdk_root, apply=False):
    sdk_root = sdk_root.expanduser().resolve(strict=True)
    target = sdk_root / 'src/S1_SDK'
    if not (target / '__init__.py').is_file():
        raise ValueError('Expected an editable S1_SDK_V2 checkout with src/S1_SDK/__init__.py')
    source = ROOT / 'integrations/s1_sdk_extensions'
    manifest = json.loads((source / 'manifest.json').read_text())
    planned = []
    for item in manifest['files']:
        name = item['file']
        if name not in ('safe_can.py','device_session.py','native_session.py'):
            raise ValueError('Unexpected extension filename')
        data = (source / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != item['sha256']:
            raise ValueError('Extension checksum mismatch: ' + name)
        dest = target / name
        if dest.is_symlink():
            raise ValueError('Refusing symlink: ' + str(dest))
        if dest.exists() and dest.read_bytes() != data:
            raise ValueError('Existing extension differs; keep your working SDK intact: ' + str(dest))
        planned.append((source / name, dest, dest.exists()))
    # Preflight every file before making any change. Never overwrite differing files.
    for src, dest, exists in planned:
        print(('Already matches: ' if exists else 'Add: ') + str(dest))
        if apply and not exists:
            with dest.open('xb') as f:
                f.write(src.read_bytes())
    return planned

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sdk-root', type=Path, required=True)
    p.add_argument('--apply', action='store_true', help='Write missing extension files; default is preview only')
    args = p.parse_args()
    install(args.sdk_root,args.apply)
    print('Applied.' if args.apply else 'Preview only. Add --apply to write missing extensions.')
