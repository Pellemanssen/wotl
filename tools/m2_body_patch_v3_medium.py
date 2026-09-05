#!/usr/bin/env python3
import json, math, shutil, struct, hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TARGETS = {
    'Orc': {
        'm2': ROOT/'Orc Female'/'OrcFemale.m2',
        'skin': ROOT/'Orc Female'/'OrcFemale00.skin',
        'out_name': 'OrcFemale',
    },
    'Draenei': {
        'm2': ROOT/'Draenai Female'/'DRAENEIFemale.m2',
        'skin': ROOT/'Draenai Female'/'DRAENEIFemale00.skin',
        'out_name': 'DraeneiFemale',
    },
    'Scourge': {
        'm2': ROOT/'Scourge Female'/'ScourgeFemale.m2',
        'skin': ROOT/'Scourge Female'/'ScourgeFemale00.skin',
        'out_name': 'ScourgeFemale',
    },
}

# Explicit v3 Medium profiles. Values are skeleton-relative fractions.
# Draenei is deliberately bottom-heavy/thick with tighter Gaussian widths for rounder forms,
# but chest projection is kept close to the Human reference rather than the exaggerated v2.
PROFILES = {
    'Orc': {
        'breast_forward_torso': 0.180,
        'breast_side_torso':    0.045,
        'hip_widen':             0.180,
        'butt_back_torso':       0.145,
        'thigh_full':            0.115,
        'chest_y_arm':           0.480,
        'chest_sy_arm':          0.360,
        'chest_sz_torso':        0.180,
        'hip_sz_stature':        0.090,
        'butt_y_arm':            0.500,
        'butt_sy_arm':           0.500,
    },
    'Draenei': {
        'breast_forward_torso': 0.180,
        'breast_side_torso':    0.045,
        'hip_widen':             0.220,
        'butt_back_torso':       0.165,
        'thigh_full':            0.150,
        'chest_y_arm':           0.470,
        'chest_sy_arm':          0.330,
        'chest_sz_torso':        0.170,
        'hip_sz_stature':        0.105,
        'butt_y_arm':            0.500,
        'butt_sy_arm':           0.480,
    },
    'Scourge': {
        'breast_forward_torso': 0.140,
        'breast_side_torso':    0.035,
        'hip_widen':             0.140,
        'butt_back_torso':       0.110,
        'thigh_full':            0.090,
        'chest_y_arm':           0.470,
        'chest_sy_arm':          0.350,
        'chest_sz_torso':        0.170,
        'hip_sz_stature':        0.085,
        'butt_y_arm':            0.500,
        'butt_sy_arm':           0.500,
    },
}

# Body/equipment geoset groups. Facial customization, ears, cape etc. remain excluded.
BODY_GROUPS = {4,5,6,8,9,10,11,12,13,18,19,20}


def u32(b,o): return struct.unpack_from('<I', b, o)[0]
def i16(b,o): return struct.unpack_from('<h', b, o)[0]
def f3(b,o): return struct.unpack_from('<3f', b, o)
def put3(b,o,v): struct.pack_into('<3f', b, o, *v)
def sha(b): return hashlib.sha256(b).hexdigest()

def gauss(v,c,s):
    if s <= 0: return 0.0
    q = (v-c)/s
    return math.exp(-0.5*q*q)

def smoothstep(a,b,x):
    if a == b: return 0.0
    t = max(0.0, min(1.0, (x-a)/(b-a)))
    return t*t*(3.0-2.0*t)

def eligible_section(sid):
    return sid == 0 or sid//100 in BODY_GROUPS

def parse_landmarks(b):
    if u32(b,4) != 264:
        raise ValueError('expected WotLK M2 version 264')
    nb,ob = u32(b,0x2c),u32(b,0x30)
    nk,ok = u32(b,0x34),u32(b,0x38)
    bones = [{'pivot': f3(b,ob+i*88+76)} for i in range(nb)]
    lookup = [i16(b,ok+i*2) for i in range(nk)]
    def key(slot):
        if slot >= len(lookup): return None
        idx = lookup[slot]
        if idx < 0 or idx >= len(bones): return None
        return bones[idx]['pivot']
    lm = {
        'arm_l':key(0),'arm_r':key(1),
        'shoulder_l':key(2),'shoulder_r':key(3),
        'spine_low':key(4),'head':key(6),'root':key(26),
    }
    if not all(lm.values()):
        raise ValueError('missing required key bones')
    return lm

def skin_vertex_set(path,nverts):
    b = path.read_bytes()
    if b[:4] != b'SKIN': raise ValueError(f'{path}: invalid SKIN')
    nidx,oidx = u32(b,4),u32(b,8)
    nsub,osub = u32(b,28),u32(b,32)
    indices = [struct.unpack_from('<H',b,oidx+i*2)[0] for i in range(nidx)]
    eligible=set(); sections=[]
    for i in range(nsub):
        o=osub+i*48
        sid=struct.unpack_from('<H',b,o)[0]
        vstart=struct.unpack_from('<H',b,o+4)[0]
        vcount=struct.unpack_from('<H',b,o+6)[0]
        if eligible_section(sid):
            sections.append(sid)
            for j in range(vstart,min(vstart+vcount,len(indices))):
                gi=indices[j]
                if gi<nverts: eligible.add(gi)
    return eligible,sorted(set(sections))

def patch_race(race,cfg,profile):
    src_m2,src_skin = cfg['m2'],cfg['skin']
    src = src_m2.read_bytes()
    data = bytearray(src)
    if data[:4] != b'MD20': raise ValueError(f'{src_m2}: invalid M2')
    nverts,vofs = u32(data,0x3c),u32(data,0x40)
    if vofs+nverts*48 > len(data): raise ValueError('vertex block outside file')

    lm = parse_landmarks(data)
    eligible,sections = skin_vertex_set(src_skin,nverts)
    positions = [f3(data,vofs+i*48) for i in range(nverts)]
    ez = [positions[i][2] for i in eligible]
    zmin = min(ez)
    root,head = lm['root'],lm['head']
    sh = tuple((lm['shoulder_l'][i]+lm['shoulder_r'][i])/2 for i in range(3))
    arm_y = (abs(lm['arm_l'][1])+abs(lm['arm_r'][1]))/2
    torso = max(0.15,sh[2]-root[2])
    leg = max(0.2,root[2]-zmin)
    stature = max(0.5,head[2]-zmin)

    chest_z = root[2] + 0.70*torso
    chest_y = profile['chest_y_arm']*arm_y
    chest_sy = max(0.035,profile['chest_sy_arm']*arm_y)
    chest_sz = max(0.045,profile['chest_sz_torso']*torso)
    hip_z = root[2] - 0.055*stature
    hip_sz = max(0.07,profile['hip_sz_stature']*stature)
    thigh_z = root[2] - 0.24*leg
    thigh_sz = max(0.09,0.19*leg)
    thigh_y = 0.52*arm_y

    breast_forward = profile['breast_forward_torso']*torso
    breast_side = profile['breast_side_torso']*torso
    butt_back = profile['butt_back_torso']*torso
    hip_widen = profile['hip_widen']
    thigh_full = profile['thigh_full']

    changed=0; max_disp=0.0
    sums={'breast':0.0,'hip':0.0,'butt':0.0,'thigh':0.0}

    for i in eligible:
        x,y,z = positions[i]
        tt=max(0.0,min(1.0,(z-root[2])/max(1e-6,torso)))
        cx=root[0]+tt*(sh[0]-root[0])

        # Rounded breast volume: localized in both lateral and vertical axes.
        wy=gauss(abs(y),chest_y,chest_sy)
        wz=gauss(z,chest_z,chest_sz)
        front=smoothstep(cx-0.035*stature,cx+0.035*stature,x)
        wb=wy*wz*front
        nx=x+breast_forward*wb
        ny=y+(1 if y>=0 else -1)*breast_side*wb

        # Hips: smooth lateral widening around pelvis.
        wh=gauss(z,hip_z,hip_sz)*max(0.0,1.0-(abs(y)/(0.27*stature+1e-6))**4)
        ny *= 1.0 + hip_widen*wh

        # Butt: rear-only projection; tighter lateral Gaussian gives a rounder rather than shelf-like shape.
        rear=smoothstep(cx+0.025*stature,cx-0.035*stature,x)
        tail_guard=smoothstep(cx-0.22*stature,cx-0.10*stature,x)
        butt_y=gauss(abs(ny),profile['butt_y_arm']*arm_y,max(0.045,profile['butt_sy_arm']*arm_y))
        wbut=gauss(z,hip_z,hip_sz*0.92)*rear*tail_guard*butt_y
        nx -= butt_back*wbut

        # Upper-thigh fullness, fading before knee/lower leg.
        side=1 if ny>=0 else -1
        ty=side*thigh_y
        wt=gauss(z,thigh_z,thigh_sz)*max(0.0,1.0-(abs(ny)/(0.30*stature+1e-6))**6)
        tx=root[0]
        nx=tx+(nx-tx)*(1.0+thigh_full*wt)
        ny=ty+(ny-ty)*(1.0+thigh_full*wt)

        dx,dy=nx-x,ny-y
        disp=math.hypot(dx,dy)
        if disp>1e-7:
            put3(data,vofs+i*48,(nx,ny,z))
            changed += 1
            max_disp=max(max_disp,disp)
        sums['breast']+=wb; sums['hip']+=wh; sums['butt']+=wbut; sums['thigh']+=wt

    # Ensure ONLY XYZ vertex coordinates changed.
    allowed=bytearray(len(src))
    for i in range(nverts):
        o=vofs+i*48
        allowed[o:o+12]=b'\x01'*12
    illegal=[i for i,(a,b) in enumerate(zip(src,data)) if a!=b and not allowed[i]]
    if illegal: raise RuntimeError(f'{race}: illegal non-XYZ changes at {illegal[:10]}')

    outdir=ROOT/'generated_v3_medium'/'Character'/race/'Female'
    outdir.mkdir(parents=True,exist_ok=True)
    out_m2=outdir/(cfg['out_name']+'.m2')
    out_skin=outdir/(cfg['out_name']+'00.skin')
    out_m2.write_bytes(data)
    shutil.copy2(src_skin,out_skin)

    return {
        'race':race,
        'source':str(src_m2.relative_to(ROOT)),
        'output':str(out_m2.relative_to(ROOT)),
        'vertex_count':nverts,
        'eligible_vertices':len(eligible),
        'changed_vertices':changed,
        'max_displacement':max_disp,
        'only_vertex_xyz_changed':True,
        'source_sha256':sha(src),
        'output_sha256':sha(data),
        'skin_sha256':sha(src_skin.read_bytes()),
        'profile':profile,
        'derived':{
            'breast_forward':breast_forward,
            'breast_side':breast_side,
            'butt_back':butt_back,
            'hip_widen':hip_widen,
            'thigh_full':thigh_full,
            'chest_y':chest_y,'chest_sy':chest_sy,'chest_sz':chest_sz,
            'hip_z':hip_z,'hip_sz':hip_sz,
        },
        'eligible_sections':sections,
        'weight_sums':sums,
    }

def main():
    report={}
    for race,cfg in TARGETS.items():
        report[race]=patch_race(race,cfg,PROFILES[race])
    ad=ROOT/'analysis'; ad.mkdir(exist_ok=True)
    (ad/'body_patch_v3_medium_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    main()
