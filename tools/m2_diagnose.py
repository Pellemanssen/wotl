#!/usr/bin/env python3
import json, math, os, struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIRS = ["Human/Female", "Orc Female", "Draenai Female", "Scourge Female", "bloodelf", "nightelf", "troll"]


def u32(b, o): return struct.unpack_from('<I', b, o)[0]
def u16(b, o): return struct.unpack_from('<H', b, o)[0]
def f3(b, o): return struct.unpack_from('<3f', b, o)

def finite3(v): return all(math.isfinite(x) for x in v)

def bbox(points):
    pts = [p for p in points if finite3(p)]
    if not pts: return None
    mn = [min(p[i] for p in pts) for i in range(3)]
    mx = [max(p[i] for p in pts) for i in range(3)]
    return {'min': mn, 'max': mx, 'size': [mx[i]-mn[i] for i in range(3)]}

def parse_m2(path):
    b = path.read_bytes()
    if b[:4] != b'MD20': raise ValueError(f'{path}: not MD20')
    version = u32(b, 4)
    nverts, ofsverts = u32(b, 0x3c), u32(b, 0x40)
    nskins = u32(b, 0x44)
    stride = 48
    end = ofsverts + nverts * stride
    if end > len(b): raise ValueError(f'{path}: vertex array OOB {nverts=} {ofsverts=:#x} size={len(b)}')
    verts=[]
    for i in range(nverts):
        o=ofsverts+i*stride
        pos=f3(b,o); weights=tuple(b[o+12:o+16]); bones=tuple(b[o+16:o+20]); normal=f3(b,o+20)
        verts.append({'pos':pos,'weights':weights,'bones':bones,'normal':normal})
    return b, {'version':version,'vertex_count':nverts,'vertex_offset':ofsverts,'skin_profiles':nskins,'vertices':verts,'bbox':bbox([v['pos'] for v in verts])}

def parse_skin(path, verts):
    b=path.read_bytes()
    if b[:4] != b'SKIN': raise ValueError(f'{path}: not SKIN')
    nidx, oidx = u32(b,4), u32(b,8)
    ntri, otri = u32(b,12), u32(b,16)
    nprop, oprop = u32(b,20), u32(b,24)
    nsub, osub = u32(b,28), u32(b,32)
    nbatch, obatch = u32(b,36), u32(b,40)
    lod = u32(b,44)
    if oidx+nidx*2>len(b) or osub+nsub*48>len(b): raise ValueError(f'{path}: arrays OOB')
    indices=[u16(b,oidx+i*2) for i in range(nidx)]
    subs=[]
    for i in range(nsub):
        o=osub+i*48
        sid,level,vstart,vcount,tstart,tcount,bcount,bstart,binfl,centerbone=struct.unpack_from('<10H',b,o)
        center=f3(b,o+20); sortcenter=f3(b,o+32); radius=struct.unpack_from('<f',b,o+44)[0]
        globals_=[]
        for j in range(vstart, min(vstart+vcount,len(indices))):
            gi=indices[j]
            if gi < len(verts): globals_.append(gi)
        pts=[verts[gi]['pos'] for gi in globals_]
        # dominant bones are useful to distinguish body from hair/gear without relying on names
        bone_weight={}
        for gi in globals_:
            v=verts[gi]
            for bi,w in zip(v['bones'],v['weights']):
                if w: bone_weight[bi]=bone_weight.get(bi,0)+w
        dom=sorted(bone_weight.items(), key=lambda kv:kv[1], reverse=True)[:8]
        subs.append({'index':i,'id':sid,'level':level,'vertex_start':vstart,'vertex_count':vcount,'triangle_index_start':tstart,'triangle_index_count':tcount,'bone_count':bcount,'bone_start':bstart,'bone_influences':binfl,'center_bone':centerbone,'center':center,'sort_center':sortcenter,'sort_radius':radius,'global_vertex_count':len(globals_),'bbox':bbox(pts),'dominant_bones':dom})
    return {'index_count':nidx,'triangle_index_count':ntri,'property_count':nprop,'submesh_count':nsub,'batch_count':nbatch,'lod':lod,'submeshes':subs}

def locate(folder):
    d=ROOT/folder
    if not d.exists(): return None,None
    m2s=sorted(d.rglob('*.m2'))
    skins=sorted(d.rglob('*.skin'))
    m2 = next((p for p in m2s if p.name.lower().endswith('female.m2')), m2s[0] if m2s else None)
    skin = next((p for p in skins if p.name.lower().endswith('00.skin')), skins[0] if skins else None)
    return m2,skin

def main():
    out={'models':{},'errors':{}}
    for folder in MODEL_DIRS:
        try:
            m2,skin=locate(folder)
            if not m2: continue
            _,info=parse_m2(m2)
            verts=info.pop('vertices')
            rec={'folder':folder,'m2':str(m2.relative_to(ROOT)),'m2_size':m2.stat().st_size,**info}
            if skin:
                rec['skin']=str(skin.relative_to(ROOT)); rec['skin_size']=skin.stat().st_size
                rec['skin_info']=parse_skin(skin,verts)
            out['models'][folder]=rec
        except Exception as e:
            out['errors'][folder]=repr(e)
    rep=ROOT/'analysis'; rep.mkdir(exist_ok=True)
    (rep/'m2_report.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
    lines=['# WotLK model geometry report','']
    for name,r in out['models'].items():
        lines += [f'## {name}',f"- M2: `{r['m2']}` ({r['m2_size']} bytes)",f"- Version: {r['version']}; vertices: {r['vertex_count']}; vertex offset: `0x{r['vertex_offset']:X}`; skin profiles: {r['skin_profiles']}",f"- Bounding box size: {r['bbox']['size'] if r.get('bbox') else None}"]
        si=r.get('skin_info')
        if si:
            lines += [f"- Skin: `{r['skin']}`; submeshes: {si['submesh_count']}; indices: {si['index_count']}",'','|idx|id|verts|tri-indices|bbox size|dominant bones|','|---:|---:|---:|---:|---|---|']
            for s in si['submeshes']:
                bs=s['bbox']['size'] if s.get('bbox') else None
                lines.append(f"|{s['index']}|{s['id']}|{s['vertex_count']}|{s['triangle_index_count']}|{bs}|{s['dominant_bones']}|")
        lines.append('')
    if out['errors']:
        lines += ['## Errors','```json',json.dumps(out['errors'],indent=2),'```']
    (rep/'m2_report.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'models':list(out['models']),'errors':out['errors']},indent=2))

if __name__=='__main__': main()
