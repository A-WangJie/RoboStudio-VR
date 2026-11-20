"""Restore the official Electron runtime pinned in desktop/runtime-lock.json."""
import argparse
import hashlib
import json
from pathlib import Path
import stat
import tempfile
from urllib.request import urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, help='Use a previously downloaded official zip')
    args = parser.parse_args()
    lock = json.loads((ROOT / 'desktop/runtime-lock.json').read_text())
    target = ROOT / 'desktop/runtime'
    with tempfile.TemporaryDirectory(prefix='s1-runtime-') as temporary:
        archive = args.archive
        if archive is None:
            archive = Path(temporary) / 'electron.zip'
            print(f'Downloading Electron {lock["version"]} from GitHub…', flush=True)
            with urlopen(lock['url'], timeout=60) as source, archive.open('wb') as output:
                while chunk := source.read(1024*1024):
                    output.write(chunk)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest != lock['sha256']:
            raise ValueError('Electron archive checksum does not match the pinned official release')
        if target.exists():
            raise FileExistsError('desktop/runtime already exists; preserve it or move it before reinstalling')
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                destination = (target / member.filename).resolve()
                if not destination.is_relative_to(target.resolve()) or stat.S_ISLNK(member.external_attr >> 16):
                    raise ValueError('Unexpected archive entry')
            target.mkdir(parents=True)
            bundle.extractall(target)
            for member in bundle.infolist():
                (target / member.filename).chmod((member.external_attr >> 16) & 0o777 or 0o644)
        print('Runtime installed and verified:', digest)


if __name__ == '__main__':
    main()
