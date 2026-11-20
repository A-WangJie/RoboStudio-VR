"""Regenerate convex collision pieces; offline dependencies: trimesh, coacd==1.0.14.
Run from the project root. Runtime needs only the generated JSON assets.
"""
import coacd,trimesh,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
coacd.set_log_level('warn')
for name in ['2_Link','5_Link']:
 m=trimesh.load(ROOT/('app/assets/s1_v1/meshes/'+name+'.STL'))
 parts=coacd.run_coacd(coacd.Mesh(m.vertices,m.faces),threshold=.03,resolution=1500,mcts_iterations=60,mcts_max_depth=3,seed=0)
 (ROOT/('app/assets/s1_v1/collision/'+name+'.json')).write_text(json.dumps([{'vertices':v.tolist(),'faces':f.tolist()} for v,f in parts]))
 print(name,len(parts),flush=True)
