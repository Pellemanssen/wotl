#!/usr/bin/env python3
import json, math, shutil, struct, hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TARGETS={
 'Orc':{'m2':ROOT/'Orc Female'/'OrcFemale.m2','skin':ROOT/'Orc Female'/'OrcFemale00.skin','out':'OrcFemale'},
 'Draenei':{'m2':ROOT/'Draenai Female'/'DRAENEIFemale.m2','skin':ROOT/'Draenai Female'/'DRAENEIFemale00.skin','out':'DraeneiFemale'},
 'Scourge':{'m2':ROOT/'Scourge Female'/'ScourgeFemale.m2','skin':ROOT/'Scourge Female'/'ScourgeFemale00.skin','out':'ScourgeFemale'},
}

# v7: start from the stable v5 method. Never change vertex Z.
# Rounder/massier bust is achieved by a broader, flatter forward-weight field,
# not by vertically stretching vertices. This avoids the v6 exploding robes/limbs.
PROFILES={
 'Orc':{
  'breast_forward_torso':0.205,'breast_side_torso':0.058,
  'breast_y_arm':0.48,'breast_sy_arm':0.46,'breast_sz_torso':0.245,
  'breast_power':0.40,'chest_low':0.575,'chest_high':0.95,
  'hip_widen':0.17,'hip_sz_stature':0.085,
  'butt_back_torso':0.148,'butt_sz_stature':0.100,'butt_power':0.48,
  'thigh_full':0.112},
 'Draenei':{
  'breast_forward_torso':0.198,'breast_side_torso':0.064,
  'breast_y_arm':0.47,'breast_sy_arm':0.46,'breast_sz_torso':0.250,
  'breast_power':0.39,'chest_low':0.585,'chest_high':0.95,
  'hip_widen':0.195,'hip_sz_stature':0.098,
  'butt_back_torso':0.112,'butt_sz_stature':0.092,'butt_power':0.47,
  'thigh_full':0.132},
 'Scourge':{
  'breast_forward_torso':0.195,'breast_side_torso':0.058,
  'breast_y_arm':0.47,'breast_sy_arm':0.45,'breast_sz_torso':0.240,
  'breast_power':0.40,'chest_low':0.565,'chest_high':0.945,
  'hip_widen':0.148,'hip_sz_stature':0.087,
  'butt_back_torso':0.152,'butt_sz_stature':0.096,'butt_power':0.47,
  'thigh_full':0.095},
}

BODY_GROUPS={4,5,6,8,9,10,11,12,13,18,19,20}

def u32(b,o): return struct.unpack_from('<I',b,o)[0]
def i16(b,o): return struct.unpack_from('<h',b,o)[0]
def f3(b,o): return struct.unpack_from('<3f',b,o)
def put3(b,o,v): struct.pack_into('<3f',b,o,*v)
def sha(b): return hashlib.sha256(b).hexdigest()
def gauss(v,c,s):
 q=(v-c)/s if s else 999.0
 return math.exp(-0.5*q*q)
def smoothstep(a,b,x):
 if a==b:return 0.0
 t=max(0.0,min(1.0,(x-a)/(b-a)))
 return t*t*(3-2*t)
def eligible_section(sid): return sid==0 or sid//100 in BODY_GROUPS

def parse_landmarks(b):
 if u32(b,4)!=264: raise ValueError('expected WotLK M2 v264')
 nb,ob=u32(b,0x2c),u32(b,0x30); nk,ok=u32(b,0x34),u32(b,0x38)
 bones=[f3(b,ob+i*88+76) for i in range(nb)]; lookup=[i16(b,ok+i*2) for i in range(nk)]
 def key(slot):
  idx=lookup[slot] if slot<len(lookup) else -1
  return bones[idx] if 0<=idx<len(bones) else None
 lm={'arm_l':key(0),'arm_r':key(1),'shoulder_l':key(2),'shoulder_r':key(3),'head':key(6),'root':key(26)}
 if not all(lm.values()): raise ValueError('missing key bones')
 return lm

def skin_vertex_set(path,nverts):
 b=path.read_bytes(); nidx,oidx=u32(b,4),u32(b,8); nsub,osub=u32(b,28),u32(b,32)
 idx=[struct.unpack_from('<H',b,oidx+i*2)[0] for i in range(nidx)]
 out=set(); secs=[]
 for i in range(nsub):
  o=osub+i*48; sid=struct.unpack_from('<H',b,o)[0]; vs=struct.unpack_from('<H',b,o+4)[0]; vc=struct.unpack_from('<H',b,o+6)[0]
  if eligible_section(sid):
   secs.append(sid)
   for j in range(vs,min(vs+vc,len(idx))):
    if idx[j]<nverts: out.add(idx[j])
 return out,sorted(set(secs))

def patch_race(race,cfg,p):
 src=cfg['m2'].read_bytes(); data=bytearray(src)
 n,vo=u32(data,0x3c),u32(data,0x40)
 lm=parse_landmarks(data); eligible,secs=skin_vertex_set(cfg['skin'],n)
 pos=[f3(data,vo+i*48) for i in range(n)]
 zmin=min(pos[i][2] for i in eligible); root,head=lm['root'],lm['head']
 sh=tuple((lm['shoulder_l'][i]+lm['shoulder_r'][i])/2 for i in range(3))
 arm_y=(abs(lm['arm_l'][1])+abs(lm['arm_r'][1]))/2
 torso=max(.15,sh[2]-root[2]); leg=max(.2,root[2]-zmin); stature=max(.5,head[2]-zmin)

 chest_z=root[2]+.70*torso
 chest_y=p['breast_y_arm']*arm_y
 chest_sy=max(.04,p['breast_sy_arm']*arm_y)
 chest_sz=max(.05,p['breast_sz_torso']*torso)
 hip_z=root[2]-.055*stature
 hip_sz=max(.07,p['hip_sz_stature']*stature)
 butt_sz=max(.07,p['butt_sz_stature']*stature)
 thigh_z=root[2]-.24*leg; thigh_sz=max(.09,.19*leg); thigh_y=.52*arm_y

 bf=p['breast_forward_torso']*torso; bs=p['breast_side_torso']*torso; bb=p['butt_back_torso']*torso
 changed=0; maxd=0.0; max_z_change=0.0

 for i in eligible:
  x,y,z=pos[i]
  tt=max(0,min(1,(z-root[2])/max(1e-6,torso)))
  cx=root[0]+tt*(sh[0]-root[0])

  low0=root[2]+p['chest_low']*torso; low1=low0+.055*torso
  hi0=root[2]+p['chest_high']*torso; hi1=hi0-.055*torso
  gate=smoothstep(low0,low1,z)*smoothstep(hi0,hi1,z)

  # Broad + low-power weighting creates a fuller silhouette while Z is untouched.
  raw=gauss(abs(y),chest_y,chest_sy)*gauss(z,chest_z,chest_sz)*smoothstep(cx-.045*stature,cx+.018*stature,x)*gate
  wb=(max(0.0,min(1.0,raw))**p['breast_power']) if raw>0 else 0.0
  nx=x+bf*wb
  ny=y+(1 if y>=0 else -1)*bs*wb

  # Stable v5 hips.
  wh=gauss(z,hip_z,hip_sz)*max(0.0,1.0-(abs(ny)/(.27*stature+1e-6))**4)
  ny*=1+p['hip_widen']*wh

  # Stable v5 butt, only slightly broader power profile.
  rear=smoothstep(cx+.025*stature,cx-.035*stature,x)
  guard=smoothstep(cx-.22*stature,cx-.10*stature,x)
  rawb=gauss(z,hip_z,butt_sz)*rear*guard*gauss(abs(ny),.50*arm_y,max(.045,.54*arm_y))
  wbut=(rawb**p['butt_power']) if rawb>0 else 0.0
  nx-=bb*wbut

  # Stable thighs; Draenei slightly reduced.
  side=1 if ny>=0 else -1; ty=side*thigh_y
  wt=gauss(z,thigh_z,thigh_sz)*max(0.0,1.0-(abs(ny)/(.30*stature+1e-6))**6)
  tx=root[0]
  nx=tx+(nx-tx)*(1+p['thigh_full']*wt)
  ny=ty+(ny-ty)*(1+p['thigh_full']*wt)

  # CRITICAL v7 invariant: Z is exactly the source Z.
  nz=z
  d=math.hypot(nx-x,ny-y)
  if d>1e-7:
   put3(data,vo+i*48,(nx,ny,nz)); changed+=1; maxd=max(maxd,d)
  max_z_change=max(max_z_change,abs(nz-z))

 # Strict QA: only X/Y bytes may differ; Z bytes must be identical.
 allowed=bytearray(len(src))
 for i in range(n):
  allowed[vo+i*48:vo+i*48+8]=b'\x01'*8
 illegal=[k for k,(a,b) in enumerate(zip(src,data)) if a!=b and not allowed[k]]
 if illegal: raise RuntimeError(f'{race}: illegal change outside vertex X/Y at {illegal[:10]}')
 if max_z_change != 0.0: raise RuntimeError(f'{race}: Z changed')

 outdir=ROOT/'generated_v7_safe_round'/'Character'/race/'Female'; outdir.mkdir(parents=True,exist_ok=True)
 outm=outdir/(cfg['out']+'.m2'); outs=outdir/(cfg['out']+'00.skin')
 outm.write_bytes(data); shutil.copy2(cfg['skin'],outs)
 return {'race':race,'changed_vertices':changed,'max_displacement_xy':maxd,'max_z_change':max_z_change,'profile':p,'source_sha256':sha(src),'output_sha256':sha(data),'skin_sha256':sha(cfg['skin'].read_bytes()),'only_vertex_xy_changed':True,'eligible_sections':secs}

def main():
 r={k:patch_race(k,TARGETS[k],PROFILES[k]) for k in TARGETS}
 (ROOT/'analysis').mkdir(exist_ok=True)
 (ROOT/'analysis'/'body_patch_v7_safe_round_report.json').write_text(json.dumps(r,indent=2),encoding='utf-8')
 print(json.dumps(r,indent=2))

if __name__=='__main__': main()
