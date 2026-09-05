#!/usr/bin/env python3
import json, math, shutil, struct, hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    'Orc': {'m2':ROOT/'Orc Female'/'OrcFemale.m2','skin':ROOT/'Orc Female'/'OrcFemale00.skin','out':'OrcFemale'},
    'Draenei': {'m2':ROOT/'Draenai Female'/'DRAENEIFemale.m2','skin':ROOT/'Draenai Female'/'DRAENEIFemale00.skin','out':'DraeneiFemale'},
    'Scourge': {'m2':ROOT/'Scourge Female'/'ScourgeFemale.m2','skin':ROOT/'Scourge Female'/'ScourgeFemale00.skin','out':'ScourgeFemale'},
}

# v4: localized rounded breast/butt domes instead of broad Gaussian projection.
# Values are relative to each race's skeleton measurements.
PROFILES = {
    'Orc': {
        'breast_forward_torso':0.205, 'breast_side_torso':0.052,
        'breast_y_arm':0.480, 'breast_sy_arm':0.390, 'breast_z_torso':0.700, 'breast_sz_torso':0.145,
        'breast_round_y':0.075, 'breast_round_z':0.085,
        'chest_low_torso':0.515, 'chest_high_torso':0.905,
        'hip_widen':0.170, 'hip_sz_stature':0.085,
        'butt_back_torso':0.145, 'butt_z_stature':-0.060, 'butt_sz_stature':0.075,
        'butt_y_arm':0.500, 'butt_sy_arm':0.540, 'butt_round_z':0.080,
        'thigh_full':0.105,
    },
    'Draenei': {
        'breast_forward_torso':0.180, 'breast_side_torso':0.050,
        'breast_y_arm':0.470, 'breast_sy_arm':0.365, 'breast_z_torso':0.705, 'breast_sz_torso':0.140,
        'breast_round_y':0.080, 'breast_round_z':0.095,
        'chest_low_torso':0.525, 'chest_high_torso':0.910,
        # Still thick, but less rear projection than v3 and a tighter round butt dome.
        'hip_widen':0.190, 'hip_sz_stature':0.095,
        'butt_back_torso':0.125, 'butt_z_stature':-0.060, 'butt_sz_stature':0.078,
        'butt_y_arm':0.500, 'butt_sy_arm':0.500, 'butt_round_z':0.095,
        'thigh_full':0.130,
    },
    'Scourge': {
        'breast_forward_torso':0.175, 'breast_side_torso':0.043,
        'breast_y_arm':0.470, 'breast_sy_arm':0.385, 'breast_z_torso':0.695, 'breast_sz_torso':0.145,
        'breast_round_y':0.070, 'breast_round_z':0.080,
        'chest_low_torso':0.505, 'chest_high_torso':0.900,
        'hip_widen':0.145, 'hip_sz_stature':0.082,
        'butt_back_torso':0.135, 'butt_z_stature':-0.060, 'butt_sz_stature':0.074,
        'butt_y_arm':0.500, 'butt_sy_arm':0.530, 'butt_round_z':0.075,
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
    q=(v-c)/s if s>0 else 1e9
    return math.exp(-0.5*q*q)
def smoothstep(a,b,x):
    if a==b: return 0.0
    t=max(0.0,min(1.0,(x-a)/(b-a)))
    return t*t*(3-2*t)
def dome(q2,power=0.68):
    # Elliptic dome: visually rounder/less pointy than a Gaussian projection.
    return max(0.0,1.0-q2)**power if q2 < 1.0 else 0.0
def eligible_section(sid): return sid==0 or sid//100 in BODY_GROUPS

def parse_landmarks(b):
    if u32(b,4)!=264: raise ValueError('expected WotLK M2 version 264')
    nb,ob=u32(b,0x2c),u32(b,0x30); nk,ok=u32(b,0x34),u32(b,0x38)
    bones=[{'pivot':f3(b,ob+i*88+76)} for i in range(nb)]
    lookup=[i16(b,ok+i*2) for i in range(nk)]
    def key(slot):
        if slot>=len(lookup): return None
        idx=lookup[slot]
        return bones[idx]['pivot'] if 0<=idx<len(bones) else None
    lm={'arm_l':key(0),'arm_r':key(1),'shoulder_l':key(2),'shoulder_r':key(3),'spine_low':key(4),'head':key(6),'root':key(26)}
    if not all(lm.values()): raise ValueError('missing required key bones')
    return lm

def skin_vertex_set(path,nverts):
    b=path.read_bytes()
    if b[:4]!=b'SKIN': raise ValueError(f'{path}: invalid SKIN')
    nidx,oidx=u32(b,4),u32(b,8); nsub,osub=u32(b,28),u32(b,32)
    indices=[struct.unpack_from('<H',b,oidx+i*2)[0] for i in range(nidx)]
    eligible=set(); sections=[]
    for i in range(nsub):
        o=osub+i*48; sid=struct.unpack_from('<H',b,o)[0]; vs=struct.unpack_from('<H',b,o+4)[0]; vc=struct.unpack_from('<H',b,o+6)[0]
        if eligible_section(sid):
            sections.append(sid)
            for j in range(vs,min(vs+vc,len(indices))):
                gi=indices[j]
                if gi<nverts: eligible.add(gi)
    return eligible,sorted(set(sections))

def patch_race(race,cfg,p):
    src=cfg['m2'].read_bytes(); data=bytearray(src)
    if data[:4]!=b'MD20': raise ValueError('invalid M2')
    nv,vo=u32(data,0x3c),u32(data,0x40)
    if vo+nv*48>len(data): raise ValueError('vertex block outside file')
    lm=parse_landmarks(data); eligible,sections=skin_vertex_set(cfg['skin'],nv)
    pos=[f3(data,vo+i*48) for i in range(nv)]
    zmin=min(pos[i][2] for i in eligible)
    root,head=lm['root'],lm['head']
    sh=tuple((lm['shoulder_l'][i]+lm['shoulder_r'][i])/2 for i in range(3))
    arm_y=(abs(lm['arm_l'][1])+abs(lm['arm_r'][1]))/2
    torso=max(0.15,sh[2]-root[2]); leg=max(0.2,root[2]-zmin); stature=max(0.5,head[2]-zmin)

    chest_z=root[2]+p['breast_z_torso']*torso
    chest_y=p['breast_y_arm']*arm_y
    chest_sy=max(0.035,p['breast_sy_arm']*arm_y)
    chest_sz=max(0.040,p['breast_sz_torso']*torso)
    chest_low=root[2]+p['chest_low_torso']*torso
    chest_high=root[2]+p['chest_high_torso']*torso
    breast_forward=p['breast_forward_torso']*torso
    breast_side=p['breast_side_torso']*torso

    hip_z=root[2]-0.055*stature; hip_sz=max(0.065,p['hip_sz_stature']*stature)
    butt_z=root[2]+p['butt_z_stature']*stature; butt_sz=max(0.060,p['butt_sz_stature']*stature)
    butt_y=p['butt_y_arm']*arm_y; butt_sy=max(0.045,p['butt_sy_arm']*arm_y)
    butt_back=p['butt_back_torso']*torso
    thigh_z=root[2]-0.24*leg; thigh_sz=max(0.09,0.18*leg); thigh_y=0.52*arm_y

    changed=0; maxd=0.0; sums={'breast':0.0,'hip':0.0,'butt':0.0,'thigh':0.0}
    for i in eligible:
        x,y,z=pos[i]
        tt=max(0.0,min(1.0,(z-root[2])/max(1e-6,torso)))
        cx=root[0]+tt*(sh[0]-root[0])
        nx,ny,nz=x,y,z

        # Breast: compact two-lobe ellipsoid with a strict under-bust/upper-chest band.
        side=1.0 if y>=0 else -1.0
        cy=side*chest_y
        qy=(y-cy)/chest_sy; qz=(z-chest_z)/chest_sz
        radial=dome(qy*qy+qz*qz,0.62)
        low=smoothstep(chest_low,chest_low+0.055*torso,z)
        high=1.0-smoothstep(chest_high-0.045*torso,chest_high,z)
        front=smoothstep(cx-0.020*stature,cx+0.030*stature,x)
        wb=radial*low*high*front
        if wb>0:
            nx += breast_forward*wb
            # Expand around each lobe centre in Y/Z to remove the pointed cone look.
            ny += (y-cy)*p['breast_round_y']*wb + side*breast_side*wb
            nz += (z-chest_z)*p['breast_round_z']*wb

        # Hips: broad but mild transition; does not touch upper abdomen.
        wh=gauss(z,hip_z,hip_sz)*max(0.0,1.0-(abs(ny)/(0.27*stature+1e-6))**4)
        ny *= 1.0+p['hip_widen']*wh

        # Butt: compact ellipsoid/dome. Tight Z support avoids the long shelf seen in v3.
        rear=smoothstep(cx+0.020*stature,cx-0.035*stature,nx)
        tail_guard=smoothstep(cx-0.22*stature,cx-0.10*stature,nx)
        bcy=(1.0 if ny>=0 else -1.0)*butt_y
        bqy=(ny-bcy)/butt_sy; bqz=(nz-butt_z)/butt_sz
        wbut=dome(bqy*bqy+bqz*bqz,0.60)*rear*tail_guard
        if wbut>0:
            nx -= butt_back*wbut
            nz += (nz-butt_z)*p['butt_round_z']*wbut

        # Upper thigh fullness, modest and localized.
        sgn=1.0 if ny>=0 else -1.0; ty=sgn*thigh_y
        wt=gauss(nz,thigh_z,thigh_sz)*max(0.0,1.0-(abs(ny)/(0.30*stature+1e-6))**6)
        tx=root[0]
        nx=tx+(nx-tx)*(1.0+p['thigh_full']*wt)
        ny=ty+(ny-ty)*(1.0+p['thigh_full']*wt)

        d=math.sqrt((nx-x)**2+(ny-y)**2+(nz-z)**2)
        if d>1e-7:
            put3(data,vo+i*48,(nx,ny,nz)); changed+=1; maxd=max(maxd,d)
        sums['breast']+=wb; sums['hip']+=wh; sums['butt']+=wbut; sums['thigh']+=wt

    allowed=bytearray(len(src))
    for i in range(nv): allowed[vo+i*48:vo+i*48+12]=b'\x01'*12
    illegal=[i for i,(a,b) in enumerate(zip(src,data)) if a!=b and not allowed[i]]
    if illegal: raise RuntimeError(f'{race}: illegal non-XYZ change at {illegal[:10]}')

    outdir=ROOT/'generated_v4_round'/'Character'/race/'Female'; outdir.mkdir(parents=True,exist_ok=True)
    outm=outdir/(cfg['out']+'.m2'); outs=outdir/(cfg['out']+'00.skin')
    outm.write_bytes(data); shutil.copy2(cfg['skin'],outs)
    return {'race':race,'output':str(outm.relative_to(ROOT)),'changed_vertices':changed,'max_displacement':maxd,'profile':p,'weight_sums':sums,'only_vertex_xyz_changed':True,'source_sha256':sha(src),'output_sha256':sha(data),'skin_sha256':sha(cfg['skin'].read_bytes()),'eligible_sections':sections}

def main():
    report={r:patch_race(r,c,PROFILES[r]) for r,c in TARGETS.items()}
    ad=ROOT/'analysis'; ad.mkdir(exist_ok=True)
    (ad/'body_patch_v4_round_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
if __name__=='__main__': main()
