#!/usr/bin/env python3
import json
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'analysis'/'m2_report.json'
d=json.loads(p.read_text(encoding='utf-8'))
out={}
for name,r in d.get('models',{}).items():
    si=r.get('skin_info',{})
    subs=[]
    for s in si.get('submeshes',[]):
        # Keep naked/base geosets and low IDs; these are the most useful body candidates.
        if s.get('id',999999) < 100 or s.get('index',999) < 3:
            subs.append({
                'index':s['index'],'id':s['id'],'verts':s['vertex_count'],
                'bbox':s.get('bbox',{}).get('size'),
                'min':s.get('bbox',{}).get('min'),'max':s.get('bbox',{}).get('max'),
                'dominant_bones':s.get('dominant_bones',[])[:5]
            })
    out[name]={
        'm2':r['m2'],'skin':r.get('skin'),'vertices':r['vertex_count'],
        'bbox':r.get('bbox'),'submesh_count':si.get('submesh_count'),
        'base_candidates':subs
    }
Path(__file__).resolve().parents[1].joinpath('analysis','m2_compact.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps(out,indent=2))
