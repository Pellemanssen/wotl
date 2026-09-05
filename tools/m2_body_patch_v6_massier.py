#!/usr/bin/env python3
import json, math, shutil, struct, hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TARGETS={
 'Orc':{'m2':ROOT/'Orc Female'/'OrcFemale.m2','skin':ROOT/'Orc Female'/'OrcFemale00.skin','out':'OrcFemale'},
 'Draenei':{'m2':ROOT/'Draenai Female'/'DRAENEIFemale.m2','skin':ROOT/'Draenai Female'/'DRAENEIFemale00.skin','out':'DraeneiFemale'},
 'Scourge':{'m2':ROOT/'Scourge Female'/'ScourgeFemale.m2','skin':ROOT/'Scourge Female'/'ScourgeFemale00.skin','out':'ScourgeFemale'},
}

# v6: "massier" breasts: much broader volume around each breast lobe, flatter forward peak,
# added lateral + vertical fullness, hard under-breast cutoff so the belly stays mostly untouched.
# Draenei thighs are slightly reduced vs v5.
PROFILES={
 'Orc':{
  'breast_forward_torso':0.205,
  'breast_side_push_torso':0.066,
  'breast_y_arm':0.48,
  'breast_sy_arm':0.50,
  'breast_sz_torso':0.245,
  'breast_power':0.34,
  'breast_side_expand':0.26,
  'breast_vertical_expand':0.24,
  'chest_low':0.565,
  'chest_high':0.955,
  'hip_widen':0.17,
  'hip_sz_stature':0.085,
  'butt_back_torso':0.148,
  'butt_sz_stature':0.100,
  'butt_power':0.44,
  'butt_side_expand':0.10,
  'thigh_full':0.112,
 },
 'Draenei':{
  'breast_forward_torso':0.195,
  'breast_side_push_torso':0.074,
  'breast_y_arm':0.47,
  'breast_sy_arm':0.50,
  'breast_sz_torso':0.250,
  'breast_power':0.33,
  'breast_side_expand':0.29,
  'breast_vertical_expand':0.26,
  'chest_low':0.575,
  'chest_high':0.955,
  'hip_widen':0.195,
  'hip_sz_stature':0.098,
  'butt_back_torso':0.112,
  'butt_sz_stature':0.092,
  'butt_power':0.43,
  'butt_side_expand':0.10,
  'thigh_full':0.132,
 },
 'Scourge':{
  'breast_forward_torso':0.188,
  'breast_side_push_torso':0.068,
  'breast_y_arm':0.47,
  'breast_sy_arm':0.49,
  'breast_sz_torso':0.240,
  'breast_power':0.34,
  'breast_side_expand':0.27,
  'breast_vertical_expand':0.25,
  'chest_low':0.555,
  'chest_high':0.95,
  'hip_widen':0.148,
  'hip_sz_stature':0.087,
  'butt_back_torso':0.152,
  'butt_sz_stature':0.096,
  'butt_power':0.43,
  'butt_side_expand':0.11,
  'thigh_full':0.095,
 },
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
 nb,ob=u32(b,0x2c),u32(b,0x30)
 nk,ok=u32(b,0x34),u32(b,0x38)
 bones=[f3(b,ob+i*88+76) for i in range(nb)]
 lookup=[i16(b,ok+i*2) for i in range(nk)]
 def key(slot):
  idx=lookup[slot] if slot<len(lookup) else -1
  return bones[idx] if 0<=idx<len(bones) else None
 lm={'arm_l':key(0),'arm_r':key(1),'shoulder_l':key(2),'shoulder_r':key(3),'head':key(6),'root':key(26)}
 if not all(lm.values()): raise ValueError('missing key bones')
 return lm

def skin_vertex_set(path,nverts):
 b=path.read_bytes()
 if b[:4]!=b'SKIN': raise ValueError(f'{path}: invalid SKIN')
 nidx,oidx=u32(b,4),u32(b,8)
 nsub,osub=u32(b,28),u32(b,32)
 idx=[struct.unpack_from('<H',b,oidx+i*2)[0] for i in range(nidx)]
 out=set(); secs=[]
 for i in range(nsub):
  o=osub+i*48
  sid=struct.unpack_from('<H',b,o)[0]
  vs=struct.unpack_from('<H',b,o+4)[0]
  vc=struct.unpack_from('<H',b,o+6)[0]
  if eligible_section(sid):
   secs.append(sid)
   for j in range(vs,min(vs+vc,len(idx))):
    if idx[j]<nverts: out.add(idx[j])
 return out,sorted(set(secs))

def patch_race(race,cfg,p):
 src=cfg['m2'].read_bytes()
 data=bytearray(src)
 if data[:4]!=b'MD20': raise ValueError(f"{cfg['m2']}: invalid M2")
 n,vo=u32(data,0x3c),u32(data,0x40)
 if vo+n*48>len(data): raise ValueError('vertex block outside file')
 lm=parse_landmarks(data)
 eligible,secs=skin_vertex_set(cfg['skin'],n)
 pos=[f3(data,vo+i*48) for i in range(n)]
 zmin=min(pos[i][2] for i in eligible)
 root,head=lm['root'],lm['head']
 sh=tuple((lm['shoulder_l'][i]+lm['shoulder_r'][i])/2 for i in range(3))
 arm_y=(abs(lm['arm_l'][1])+abs(lm['arm_r'][1]))/2
 torso=max(.15,sh[2]-root[2])
 leg=max(.2,root[2]-zmin)
 stature=max(.5,head[2]-zmin)

 chest_z=root[2]+.70*torso
 chest_y=p['breast_y_arm']*arm_y
 chest_sy=max(.045,p['breast_sy_arm']*arm_y)
 chest_sz=max(.055,p['breast_sz_torso']*torso)
 hip_z=root[2]-.055*stature
 hip_sz=max(.07,p['hip_sz_stature']*stature)
 butt_sz=max(.07,p['butt_sz_stature']*stature)
 thigh_z=root[2]-.24*leg
 thigh_sz=max(.09,.19*leg)
 thigh_y=.52*arm_y

 bf=p['breast_forward_torso']*torso
 bsp=p['breast_side_push_torso']*torso
 bb=p['butt_back_torso']*torso
 changed=0; maxd=0.0
 sums={'breast':0.0,'butt':0.0,'hip':0.0,'thigh':0.0}

 for i in eligible:
  x,y,z=pos[i]
  tt=max(0,min(1,(z-root[2])/max(1e-6,torso)))
  cx=root[0]+tt*(sh[0]-root[0])

  # HARD under-breast + upper-chest gate. This keeps the abdomen from following the bust.
  low0=root[2]+p['chest_low']*torso
  low1=low0+.055*torso
  hi0=root[2]+p['chest_high']*torso
  hi1=hi0-.055*torso
  gate=smoothstep(low0,low1,z)*smoothstep(hi0,hi1,z)

  # Broad super-ellipse-like breast weighting. Low exponent = broad plateau, less cone-like peak.
  wy=gauss(abs(y),chest_y,chest_sy)
  wz=gauss(z,chest_z,chest_sz)
  front=smoothstep(cx-.045*stature,cx+.018*stature,x)
  raw=max(0.0,min(1.0,wy*wz*front*gate))
  wb=(raw**p['breast_power']) if raw>0 else 0.0

  side=1 if y>=0 else -1
  cy=side*chest_y
  nx=x+bf*wb
  # Add actual circumference instead of only forward projection.
  ny=cy+(y-cy)*(1.0+p['breast_side_expand']*wb)
  ny+=side*bsp*wb
  nz=chest_z+(z-chest_z)*(1.0+p['breast_vertical_expand']*wb)
  # Keep the under-breast cutoff from being pulled too far down.
  if nz < low0:
   nz=low0 + (nz-low0)*0.20

  # Hips.
  wh=gauss(z,hip_z,hip_sz)*max(0.0,1.0-(abs(ny)/(.27*stature+1e-6))**4)
  ny*=1+p['hip_widen']*wh

  # Butt: broad/round plateau plus a little lateral expansion, still compact vertically.
  rear=smoothstep(cx+.025*stature,cx-.035*stature,x)
  guard=smoothstep(cx-.22*stature,cx-.10*stature,x)
  rawb=gauss(z,hip_z,butt_sz)*rear*guard*gauss(abs(ny),.50*arm_y,max(.045,.54*arm_y))
  wbut=(rawb**p['butt_power']) if rawb>0 else 0.0
  nx-=bb*wbut
  ny*=1.0+p['butt_side_expand']*wbut

  # Upper thighs. Draenei is intentionally slightly reduced vs v5.
  side2=1 if ny>=0 else -1
  ty=side2*thigh_y
  wt=gauss(z,thigh_z,thigh_sz)*max(0.0,1.0-(abs(ny)/(.30*stature+1e-6))**6)
  tx=root[0]
  nx=tx+(nx-tx)*(1+p['thigh_full']*wt)
  ny=ty+(ny-ty)*(1+p['thigh_full']*wt)

  d=math.sqrt((nx-x)**2+(ny-y)**2+(nz-z)**2)
  if d>1e-7:
   put3(data,vo+i*48,(nx,ny,nz))
   changed+=1
   maxd=max(maxd,d)
  sums['breast']+=wb; sums['butt']+=wbut; sums['hip']+=wh; sums['thigh']+=wt

 # Strict binary QA: only vertex XYZ is allowed to differ.
 allowed=bytearray(len(src))
 for i in range(n): allowed[vo+i*48:vo+i*48+12]=b'\x01'*12
 illegal=[k for k,(a,b) in enumerate(zip(src,data)) if a!=b and not allowed[k]]
 if illegal: raise RuntimeError(f'{race}: illegal non-XYZ changes at {illegal[:10]}')

 outdir=ROOT/'generated_v6_massier'/'Character'/race/'Female'
 outdir.mkdir(parents=True,exist_ok=True)
 outm=outdir/(cfg['out']+'.m2')
 outs=outdir/(cfg['out']+'00.skin')
 outm.write_bytes(data)
 shutil.copy2(cfg['skin'],outs)
 return {
  'race':race,'changed_vertices':changed,'max_displacement':maxd,'profile':p,
  'source_sha256':sha(src),'output_sha256':sha(data),'skin_sha256':sha(cfg['skin'].read_bytes()),
  'only_vertex_xyz_changed':True,'eligible_sections':secs,'weight_sums':sums
 }

def main():
 r={k:patch_race(k,TARGETS[k],PROFILES[k]) for k in TARGETS}
 (ROOT/'analysis').mkdir(exist_ok=True)
 (ROOT/'analysis'/'body_patch_v6_massier_report.json').write_text(json.dumps(r,indent=2),encoding='utf-8')
 print(json.dumps(r,indent=2))

if __name__=='__main__': main()
