#!/usr/bin/env python3
"""Export only reviewed source roots; never recurse through Unity caches."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT_FILES = ('README.md', 'CONTRIBUTING.md', 'THIRD_PARTY_NOTICES.md',
              '.gitignore', '.gitattributes', 'pyproject.toml', 'requirements.txt',
              'start-bridge.sh', 'quest-unmounted.sh', 'bridge_service.py', 'hardware_control.py')
SOURCE_DIRS = ('bridge', 'ui', 'scripts', 'tests', 'tests_hardware', 'config', 'docs',
               'QuestControllerClient/Assets', 'QuestControllerClient/Packages',
               'QuestControllerClient/ProjectSettings', 'ci')
SKIP_DIRS = {'__pycache__', '.git', '.local', 'artifacts', 'history', 'previews',
             '_Recovery', 'Temp', 'Library', 'Logs', 'UserSettings'}


def walk_source(folder):
    for path in sorted(folder.iterdir()):
        if path.is_symlink():
            raise ValueError('源码目录不能含符号链接：' + str(path))
        if path.is_dir():
            if path.name not in SKIP_DIRS:
                yield from walk_source(path)
        elif path.name not in {'_Recovery.meta', 'Temp.meta'} and path.suffix not in {'.pyc', '.pyo'}:
            yield path


def source_files(root):
    for name in ROOT_FILES:
        path = root / name
        if path.is_file():
            yield path
    for name in SOURCE_DIRS:
        folder = root / name
        if folder.is_dir():
            for path in walk_source(folder):
                rel = path.relative_to(root)
                if rel.parts[0] == 'config' and not (path.name.endswith('.example.json') or path.suffix == '.rules'):
                    continue
                yield path


def export(root, output):
    root, output = root.resolve(), output.resolve()
    if output == root or root in output.parents:
        raise ValueError('导出目录必须在本模块之外')
    if output.exists():
        raise ValueError('导出目录已存在，请选择一个新目录')
    entries = []
    for source in source_files(root):
        if source.is_symlink():
            raise ValueError('不导出符号链接：' + str(source))
        rel = source.relative_to(root)
        data = source.read_bytes()
        if rel.as_posix() == 'QuestControllerClient/ProjectSettings/ProjectSettings.asset':
            text = data.decode('utf-8')
            # Cloud account binding belongs to this workstation, not the source release.
            text = re.sub(r'(?m)^(  (?:cloudProjectId|organizationId|projectName):).*$', r'\1 ', text)
            data = text.encode('utf-8')
        target = output / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(source.stat().st_mode & 0o777)
        entries.append(dict(path=rel.as_posix(), bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
    manifest = dict(formatVersion=1, module='RoboData', files=entries,
                    totalBytes=sum(item['bytes'] for item in entries),
                    license='MIT for original RD code; see repository root LICENSE; third-party terms apply')
    (output / 'SOURCE_MANIFEST.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = export(Path(__file__).resolve().parents[1], args.output)
    print(f"Exported {len(result['files'])} source files, {result['totalBytes']/1024/1024:.1f} MiB")
