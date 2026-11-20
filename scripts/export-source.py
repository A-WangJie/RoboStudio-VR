#!/usr/bin/env python3
"""Create a reviewable DK source copy, including the RD source module."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re

ROOT_FILES=('README.md','CONTRIBUTING.md','THIRD_PARTY_NOTICES.md','LICENSE','NOTICE',
 '.gitignore','.gitattributes','server.py','S1Studio','start-desktop.sh','start-studio.sh',
 'install-desktop.sh','requirements.txt','requirements-simulation.txt','requirements-lock.txt')
SOURCE_DIRS=('app','backend','desktop','scripts','tools','tests','docs','config','.github','integrations')
SKIP={'__pycache__','.git','.local','artifacts','runtime','node_modules','history'}

def walk(folder):
 for p in sorted(folder.iterdir()):
  if p.is_symlink(): raise ValueError('Source contains symlink: '+str(p))
  if p.is_dir():
   if p.name not in SKIP: yield from walk(p)
  elif p.suffix not in ('.pyc','.pyo'): yield p

def source_files(root, include_models=False):
 for name in ROOT_FILES:
  if (root/name).is_file(): yield root/name
 for name in SOURCE_DIRS:
  if (root/name).is_dir():
   for p in walk(root/name):
    if name=='config' and not p.name.endswith('.example.json'): continue
    if not include_models and p.is_relative_to(root/'app/assets/s1_v1'): continue
    yield p
 rd=root/'VR remote control'
 spec=importlib.util.spec_from_file_location('rd_release_export',rd/'scripts/export-source.py')
 release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)
 yield from release.source_files(rd)

def export(root,output,include_models=False):
 root,output=root.resolve(),output.resolve()
 if root==output or root in output.parents: raise ValueError('Output must be outside DK')
 if output.exists(): raise ValueError('Output already exists; use a new directory')
 entries=[]
 for source in source_files(root,include_models):
  if source.is_symlink(): raise ValueError('Refusing symlink: '+str(source))
  rel=source.relative_to(root);data=source.read_bytes()
  if rel.as_posix().endswith('QuestControllerClient/ProjectSettings/ProjectSettings.asset'):
   data=re.sub(r'(?m)^(  (?:cloudProjectId|organizationId|projectName):).*$',r'\1 ',data.decode()).encode()
  target=output/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
  target.chmod(source.stat().st_mode & 0o777)
  entries.append(dict(path=rel.as_posix(),bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
 manifest=dict(formatVersion=1,project='RoboStudio-VR',files=entries,
  totalBytes=sum(e['bytes'] for e in entries),
  modelsIncluded=include_models,
  license='MIT for original RS/RD code; third-party terms apply; S1 model redistribution rights pending verification')
 (output/'SOURCE_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
 return manifest

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--output',type=Path,required=True)
 parser.add_argument('--include-models',action='store_true',help='Private copy only until redistribution rights are verified')
 args=parser.parse_args();m=export(Path(__file__).resolve().parents[1],args.output,args.include_models)
 print(f"Exported {len(m['files'])} source files, {m['totalBytes']/1024/1024:.1f} MiB")
