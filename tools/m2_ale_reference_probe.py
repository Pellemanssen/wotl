#!/usr/bin/env python3
import json, math, struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
MODELS={
 'BloodElfALE':(ROOT/'bloodelf'/'female'/'bloodelffemale.m2',ROOT/'bloodelf'/'female'/'bloodelffemale00.skin'),
 'Orc':(ROOT/'Orc Female'/'OrcFemale.m2',ROOT/'Orc Female'/'OrcFemale00.skin'),
 'Draenei':(ROOT/'Draenai Female'/'DRAENEIFemale.m2',ROOT/'Draenai Female'/'DRAENEIFemale00.skin'),
 'Scourge':(ROOT/'Scourge Female'/'ScourgeFemale.m2',ROOT/'Scourge Female'/'ScourgeFemale00.skin'),
}
BODY_GROUPS={4,5,6,8,9,10,11,12,13,18,19,20}
def u32(b,o): return struct.unpack_from('<I',b,o)[0]
def i16(b,o): return struct.unpack_from('<h',b,o)[0]
def f3(b,o): return struct.unpack_from('<3f',b,o)
def quantile(a,q):
 a=sorted(a)
 if not a:return None
 x=(len(a)-1)*q; lo=int(x); hi=min(len(a)-1,lo+1); t=x-lo
 return a[lo]*(1-t)+a[hi]*t
def eligible_section(sid): return sid==0 or sid//100 in BODY_GROUPS
def landmarks(b):
 nb,ob=u32(b,0x2c),u32(b,0x30); nk,ok=u32(b,0x34),u32(b,0x38)
 bones=[f3(b,ob+i*88+76) for i in range(nb)]; lookup=[i16(b,ok+i*2) for i in range(nk)]
 def key(slot):
  idx=lookup[slot] if slot<len(lookup) else -1
  return bones[idx] if 0<=idx<len(bones) else None
 lm={'arm_l':key(0),'arm_r':key(1),'shoulder_l':key(2),'shoulder_r':key(3),'head':key(6),'root':key(26)}
 if not all(lm.values()): raise ValueError('missing key bones')
 return lm
def eligible(path,n):
 b=path.read_bytes(); nidx,oidx=u32(b,4),u32(b,8); nsub,osub=u32(b,28),u32(b,32)
 idx=[struct.unpack_from('<H',b,oidx+i*2)[0] for i in range(nidx)]; out=set()
 for i in range(nsub):
  o=osub+i*48; sid=struct.unpack_from('<H',b,o)[0]; vs=struct.unpack_from('<H',b,o+4)[0]; vc=struct.unpack_from('<H',b,o+6)[0]
  if eligible_section(sid):
   for j in range(vs,min(vs+vc,len(idx))):
    if idx[j]<n: out.add(idx[j])
 return out
def model(path,skin):
 b=path.read_bytes(); n,vo=u32(b,0x3c),u32(b,0x40); pos=[f3(b,vo+i*48) for i in range(n)]; lm=landmarks(b); e=eligible(skin,n)
 root=lm['root']; sh=tuple((lm['shoulder_l'][i]+lm['shoulder_r'][i])/2 for i in range(3)); arm_y=(abs(lm['arm_l'][1])+abs(lm['arm_r'][1]))/2
 zmin=min(pos[i][2] for i in e); torso=sh[2]-root[2]; stature=lm['head'][2]-zmin
 def cx(z):
  t=max(0,min(1,(z-root[2])/torso)); return root[0]+t*(sh[0]-root[0])
 rows=[]
 for i in e:
  x,y,z=pos[i]; zn=(z-root[2])/torso; yn=abs(y)/arm_y; xn=(x-cx(z))/torso
  rows.append((xn,yn,zn))
 return {'rows':rows,'torso':torso,'arm_y':arm_y,'stature':stature,'count':len(e)}
def profile(m):
 rows=m['rows']; z0,z1=.54,.98; nz=23; y0,y1=0,1.10; ny=18
 zprof=[]
 for k in range(nz):
  a=z0+(z1-z0)*k/nz; c=z0+(z1-z0)*(k+.5)/nz; d=z0+(z1-z0)*(k+1)/nz
  vals=[x for x,y,z in rows if a<=z<d and .12<=y<=.78 and x>-.10]
  zprof.append([c,quantile(vals,.86),len(vals)])
 yprof=[]
 for k in range(ny):
  a=y0+(y1-y0)*k/ny; c=y0+(y1-y0)*(k+.5)/ny; d=y0+(y1-y0)*(k+1)/ny
  vals=[x for x,y,z in rows if a<=y<d and .66<=z<=.91 and x>-.10]
  yprof.append([c,quantile(vals,.86),len(vals)])
 # linear torso baseline from lower and upper chest endpoints
 pts=[(z,x) for z,x,n in zprof if x is not None and (z<.62 or z>.91)]
 if len(pts)>=2:
  mz=sum(z for z,x in pts)/len(pts); mx=sum(x for z,x in pts)/len(pts); den=sum((z-mz)**2 for z,x in pts) or 1
  slope=sum((z-mz)*(x-mx) for z,x in pts)/den; intercept=mx-slope*mz
 else: slope=0; intercept=0
 augz=[[z,x,(None if x is None else max(0,x-(intercept+slope*z)))] for z,x,n in zprof]
 max_aug=max((a for z,x,a in augz if a is not None),default=0)
 return {'z_profile':zprof,'y_profile':yprof,'baseline':[intercept,slope],'z_augmentation':augz,'max_z_augmentation':max_aug}
def main():
 out={}
 for name,(p,s) in MODELS.items():
  m=model(p,s); out[name]={'torso':m['torso'],'arm_y':m['arm_y'],'stature':m['stature'],'eligible_vertices':m['count'],'profile':profile(m)}
 (ROOT/'analysis').mkdir(exist_ok=True)
 (ROOT/'analysis'/'ale_reference_probe.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
 summary={k:{'torso':v['torso'],'arm_y':v['arm_y'],'max_z_augmentation':v['profile']['max_z_augmentation']} for k,v in out.items()}
 print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
