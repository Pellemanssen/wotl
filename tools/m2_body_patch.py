#!/usr/bin/env python3
import json, math, shutil, struct
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TARGETS={
 'Orc':('Orc Female/OrcFemale.m2','Orc Female/OrcFemale00.skin','generated/Character/Orc/Female/OrcFemale.m2','generated/Character/Orc/Female/OrcFemale00.skin'),
 'Draenei':('Draenai Female/DRAENEIFemale.m2','Draenai Female/DRAENEIFemale00.skin','generated/Character/Draenei/Female/DraeneiFemale.m2','generated/Character/Draenei/Female/DraeneiFemale00.skin'),
 'Scourge':('Scourge Female/ScourgeFemale.m2','Scourge Female/ScourgeFemale00.skin','generated/Character/Scourge/Female/ScourgeFemale.m2','generated/Character/Scourge/Female/ScourgeFemale00.skin'),
}
# Body/equipment geoset groups. 1-3 are facial customisation, 7 ears, 15 cape; they are deliberately excluded.
BODY_GROUPS={4,5,6,8,9,10,11,12,13,18,19,20}

def u32(b,o): return struct.unpack_from('<I',b,o)[0]
def i16(b,o): return struct.unpack_from('<h',b,o)[0]
def f3(b,o): return struct.unpack_from('<3f',b,o)
def put3(b,o,v): struct.pack_into('<3f',b,o,*v)
def gauss(v,c,s):
 if s<=0: return 0.0
 q=(v-c)/s
 return math.exp(-0.5*q*q)
def smoothstep(a,b,x):
 if a==b: return 0.0
 t=max(0.0,min(1.0,(x-a)/(b-a)))
 return t*t*(3-2*t)
def eligible_section(sid):
 if sid==0: return True
 return sid//100 in BODY_GROUPS

def parse_landmarks(b):
 ver=u32(b,4)
 if ver!=264: raise ValueError(f'expected WotLK M2 version 264, got {ver}')
 nb,ob=u32(b,0x2c),u32(b,0x30); nk,ok=u32(b,0x34),u32(b,0x38)
 stride=88
 bones=[]
 for i in range(nb): bones.append({'pivot':f3(b,ob+i*stride+76)})
 lookup=[i16(b,ok+i*2) for i in range(nk)]
 def key(slot):
  if slot>=len(lookup) or lookup[slot]<0 or lookup[slot]>=len(bones): return None
  return bones[lookup[slot]]['pivot']
 vals={'arm_l':key(0),'arm_r':key(1),'shoulder_l':key(2),'shoulder_r':key(3),'spine_low':key(4),'head':key(6),'root':key(26)}
 if not all(vals[k] for k in ('arm_l','arm_r','shoulder_l','shoulder_r','spine_low','head','root')): raise ValueError('missing required key bones')
 return vals

def skin_vertex_set(skin_path,nverts):
 b=skin_path.read_bytes()
 if b[:4]!=b'SKIN': raise ValueError(f'{skin_path}: invalid SKIN')
 nidx,oidx=u32(b,4),u32(b,8); nsub,osub=u32(b,28),u32(b,32)
 indices=[struct.unpack_from('<H',b,oidx+i*2)[0] for i in range(nidx)]
 eligible=set(); sections=[]
 for i in range(nsub):
  o=osub+i*48; sid,vstart,vcount=struct.unpack_from('<HxxHH',b,o)[0],struct.unpack_from('<H',b,o+4)[0],struct.unpack_from('<H',b,o+6)[0]
  # Above unpack is intentionally avoided for the ID due to packed shorts; use direct reads for clarity.
  sid=struct.unpack_from('<H',b,o)[0]; vstart=struct.unpack_from('<H',b,o+4)[0]; vcount=struct.unpack_from('<H',b,o+6)[0]
  if eligible_section(sid):
   sections.append(sid)
   for j in range(vstart,min(vstart+vcount,len(indices))):
    gi=indices[j]
    if gi<nverts: eligible.add(gi)
 return eligible,sorted(set(sections))

def patch_one(name,src_m2,src_skin,out_m2,out_skin):
 data=bytearray(src_m2.read_bytes())
 if data[:4]!=b'MD20': raise ValueError(f'{src_m2}: invalid M2')
 nverts,vofs=u32(data,0x3c),u32(data,0x40); stride=48
 if vofs+nverts*stride>len(data): raise ValueError('vertex block outside file')
 lm=parse_landmarks(data)
 eligible,sections=skin_vertex_set(src_skin,nverts)
 positions=[f3(data,vofs+i*stride) for i in range(nverts)]
 ez=[positions[i][2] for i in eligible]
 if not ez: raise ValueError('no eligible body vertices')
 zmin=min(ez)
 root=lm['root']; head=lm['head']
 sh=((lm['shoulder_l'][0]+lm['shoulder_r'][0])/2,(lm['shoulder_l'][1]+lm['shoulder_r'][1])/2,(lm['shoulder_l'][2]+lm['shoulder_r'][2])/2)
 arm_y=(abs(lm['arm_l'][1])+abs(lm['arm_r'][1]))/2
 torso=max(0.15,sh[2]-root[2]); leg=max(0.2,root[2]-zmin); stature=max(0.5,head[2]-zmin)
 # Shape anchors are skeleton-relative so each race keeps its own proportions.
 chest_z=root[2]+0.70*torso; chest_sy=max(0.035,0.40*arm_y); chest_y=0.48*arm_y; chest_sz=max(0.045,0.20*torso)
 hip_z=root[2]-0.055*stature; hip_sz=max(0.07,0.095*stature)
 thigh_z=root[2]-0.24*leg; thigh_sz=max(0.09,0.19*leg); thigh_y=0.52*arm_y
 # Deliberately noticeable but not cartoon-level. Values are fractions of skeleton spans.
 breast_forward=0.19*torso; breast_side=0.055*torso
 butt_back=0.17*torso; hip_widen=0.22; thigh_full=0.13
 changed=0; max_disp=0.0; sums={'breast':0.0,'hip':0.0,'butt':0.0,'thigh':0.0}
 for i in eligible:
  x,y,z=positions[i]
  # Dynamic centreline along the torso (x is front/back, y left/right, z up in WoW).
  tt=max(0.0,min(1.0,(z-root[2])/max(1e-6,torso)))
  cx=root[0]+tt*(sh[0]-root[0])
  # Chest: two smooth lobes; only the front half receives the forward projection.
  wy=gauss(abs(y),chest_y,chest_sy); wz=gauss(z,chest_z,chest_sz)
  front=smoothstep(cx-0.035*stature,cx+0.035*stature,x)
  wb=wy*wz*front
  nx=x+breast_forward*wb
  ny=y+(1 if y>=0 else -1)*breast_side*wb
  # Hips: broad lateral expansion centred just below the root/pelvis.
  wh=gauss(z,hip_z,hip_sz)*max(0.0,1.0-(abs(y)/(0.27*stature+1e-6))**4)
  ny*=1.0+hip_widen*wh
  # Butt: rear half only, with a cutoff that protects long tails/hair behind the character.
  rear=smoothstep(cx+0.025*stature,cx-0.035*stature,x)
  tail_guard=smoothstep(cx-0.22*stature,cx-0.10*stature,x)
  butt_y=gauss(abs(ny),0.50*arm_y,max(0.045,0.55*arm_y))
  wbut=gauss(z,hip_z,hip_sz*0.95)*rear*tail_guard*butt_y
  nx-=butt_back*wbut
  # Thighs: radial thickening around each leg, fading before knees/lower legs.
  side=1 if ny>=0 else -1; ty=side*thigh_y
  wt=gauss(z,thigh_z,thigh_sz)*max(0.0,1.0-(abs(ny)/(0.30*stature+1e-6))**6)
  tx=root[0]
  nx=tx+(nx-tx)*(1.0+thigh_full*wt)
  ny=ty+(ny-ty)*(1.0+thigh_full*wt)
  dx,dy,dz=nx-x,ny-y,0.0; disp=math.sqrt(dx*dx+dy*dy)
  if disp>1e-7:
   put3(data,vofs+i*stride,(nx,ny,z)); changed+=1; max_disp=max(max_disp,disp)
  sums['breast']+=wb; sums['hip']+=wh; sums['butt']+=wbut; sums['thigh']+=wt
 out_m2.parent.mkdir(parents=True,exist_ok=True); out_skin.parent.mkdir(parents=True,exist_ok=True)
 out_m2.write_bytes(data); shutil.copy2(src_skin,out_skin)
 # Structural invariants: offsets/counts/file size unchanged.
 chk=out_m2.read_bytes()
 assert len(chk)==len(src_m2.read_bytes()) and chk[:4]==b'MD20' and u32(chk,0x3c)==nverts and u32(chk,0x40)==vofs
 return {'race':name,'source':str(src_m2.relative_to(ROOT)),'output':str(out_m2.relative_to(ROOT)),'vertices':nverts,'eligible_vertices':len(eligible),'changed_vertices':changed,'max_displacement':max_disp,'eligible_sections':sections,'landmarks':lm,'anchors':{'zmin':zmin,'root':root,'shoulder_mid':sh,'head':head,'arm_y':arm_y,'torso_span':torso,'leg_span':leg,'stature':stature},'weights_sum':sums,'parameters':{'breast_forward':breast_forward,'breast_side':breast_side,'butt_back':butt_back,'hip_widen':hip_widen,'thigh_full':thigh_full}}

def main():
 report={}
 for name,(a,b,c,d) in TARGETS.items(): report[name]=patch_one(name,ROOT/a,ROOT/b,ROOT/c,ROOT/d)
 ad=ROOT/'analysis'; ad.mkdir(exist_ok=True)
 (ad/'body_patch_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 readme=ROOT/'generated'/'README.md'; readme.parent.mkdir(exist_ok=True)
 readme.write_text('# WotLK 3.3.5a – A Little Extra style test build\n\nGenerated non-destructively from the source models. Original files are untouched.\n\nTargets: Female Orc, Draenei and Scourge. The patch changes vertex positions only; topology, weights, animations and SKIN indices remain unchanged.\n\nInternal MPQ-ready paths are under `generated/Character/...`. Test in a separate client copy before packing/deploying.\n',encoding='utf-8')
 print(json.dumps(report,indent=2))
if __name__=='__main__': main()
