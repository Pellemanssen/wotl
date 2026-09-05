#!/usr/bin/env python3
import json, math, shutil, struct, hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF_M2 = ROOT/'bloodelf'/'female'/'bloodelffemale.m2'
REF_SKIN = ROOT/'bloodelf'/'female'/'bloodelffemale00.skin'
TARGETS = {
    'Orc': {
        'm2': ROOT/'Orc Female'/'OrcFemale.m2',
        'skin': ROOT/'Orc Female'/'OrcFemale00.skin',
        'out': 'OrcFemale',
        'belly_lock': 0.650,
        'chest_high': 0.965,
        'hip_widen': 0.170,
        'butt_back_torso': 0.148,
        'butt_sz_stature': 0.100,
        'butt_power': 0.48,
        'thigh_full': 0.112,
    },
    'Draenei': {
        'm2': ROOT/'Draenai Female'/'DRAENEIFemale.m2',
        'skin': ROOT/'Draenai Female'/'DRAENEIFemale00.skin',
        'out': 'DraeneiFemale',
        'belly_lock': 0.705,
        'chest_high': 0.965,
        'hip_widen': 0.195,
        'butt_back_torso': 0.112,
        'butt_sz_stature': 0.092,
        'butt_power': 0.47,
        # Slightly below v8, per visual feedback.
        'thigh_full': 0.110,
    },
    'Scourge': {
        'm2': ROOT/'Scourge Female'/'ScourgeFemale.m2',
        'skin': ROOT/'Scourge Female'/'ScourgeFemale00.skin',
        'out': 'ScourgeFemale',
        'belly_lock': 0.645,
        'chest_high': 0.955,
        'hip_widen': 0.148,
        'butt_back_torso': 0.152,
        'butt_sz_stature': 0.096,
        'butt_power': 0.47,
        'thigh_full': 0.095,
    },
}

# WotLK body/equipment geoset families used by the prior stable builds.
BODY_GROUPS = {4,5,6,8,9,10,11,12,13,18,19,20}

# The important v9 change:
#   * NO invented breast gaussian / cone / point push.
#   * Measure the real A Little Extra Blood Elf chest front-surface profile.
#   * Measure each untouched target race profile.
#   * Transfer the Blood Elf *augmentation shape* in normalized torso coordinates.
#   * Work from the original race M2 every build, never from v7/v8 output.
#   * Breast operation changes X only. Y/Z are untouched by the breast transfer.
#   * Hard race-specific belly locks, especially Draenei.

Z0, Z1, NZ = 0.57, 1.00, 31
Y0, Y1, NY = 0.00, 0.95, 17
FRONT_Q = 0.86


def u32(b,o): return struct.unpack_from('<I',b,o)[0]
def i16(b,o): return struct.unpack_from('<h',b,o)[0]
def f3(b,o): return struct.unpack_from('<3f',b,o)
def put3(b,o,v): struct.pack_into('<3f',b,o,*v)
def sha(b): return hashlib.sha256(b).hexdigest()

def quantile(a,q):
    if not a: return None
    a=sorted(a); x=(len(a)-1)*q; lo=int(x); hi=min(len(a)-1,lo+1); t=x-lo
    return a[lo]*(1-t)+a[hi]*t

def gauss(v,c,s):
    q=(v-c)/s if s else 999.0
    return math.exp(-0.5*q*q)

def smoothstep(a,b,x):
    if a==b: return 0.0
    t=max(0.0,min(1.0,(x-a)/(b-a)))
    return t*t*(3.0-2.0*t)

def eligible_section(sid):
    return sid==0 or sid//100 in BODY_GROUPS

def parse_landmarks(b):
    if b[:4] != b'MD20' or u32(b,4) != 264:
        raise ValueError('expected WotLK MD20 v264')
    nb,ob=u32(b,0x2c),u32(b,0x30); nk,ok=u32(b,0x34),u32(b,0x38)
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
    nidx,oidx=u32(b,4),u32(b,8); nsub,osub=u32(b,28),u32(b,32)
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
                if idx[j] < nverts: out.add(idx[j])
    return out, sorted(set(secs))

def load_model(m2,skin,raw=None):
    src = m2.read_bytes() if raw is None else raw
    if src[:4]!=b'MD20': raise ValueError(f'{m2}: invalid M2')
    n,vo=u32(src,0x3c),u32(src,0x40)
    if vo+n*48>len(src): raise ValueError(f'{m2}: vertex block outside file')
    pos=[f3(src,vo+i*48) for i in range(n)]
    lm=parse_landmarks(src); eligible,secs=skin_vertex_set(skin,n)
    zmin=min(pos[i][2] for i in eligible)
    root=lm['root']; head=lm['head']
    sh=tuple((lm['shoulder_l'][i]+lm['shoulder_r'][i])/2 for i in range(3))
    arm_y=(abs(lm['arm_l'][1])+abs(lm['arm_r'][1]))/2
    torso=max(.15,sh[2]-root[2]); leg=max(.2,root[2]-zmin); stature=max(.5,head[2]-zmin)
    def cx(z):
        t=max(0.0,min(1.0,(z-root[2])/torso))
        return root[0]+t*(sh[0]-root[0])
    return {
        'bytes':src,'n':n,'vo':vo,'pos':pos,'lm':lm,'eligible':eligible,'sections':secs,
        'zmin':zmin,'root':root,'head':head,'sh':sh,'arm_y':arm_y,'torso':torso,'leg':leg,'stature':stature,'cx':cx,
    }

def bin_index(v,a,b,n):
    if v<a or v>=b: return None
    return min(n-1,max(0,int((v-a)/(b-a)*n)))

def z_center(k): return Z0+(Z1-Z0)*(k+.5)/NZ
def y_center(j): return Y0+(Y1-Y0)*(j+.5)/NY

def build_profile(m):
    cells=[[[] for _ in range(NZ)] for _ in range(NY)]
    for i in m['eligible']:
        x,y,z=m['pos'][i]
        zn=(z-m['root'][2])/m['torso']
        yn=abs(y)/max(1e-6,m['arm_y'])
        j=bin_index(yn,Y0,Y1,NY); k=bin_index(zn,Z0,Z1,NZ)
        if j is None or k is None: continue
        xn=(x-m['cx'](z))/m['torso']
        if xn > -0.20:
            cells[j][k].append(xn)

    front=[[quantile(cells[j][k],FRONT_Q) for k in range(NZ)] for j in range(NY)]

    # Fill small holes from nearest z neighbours so interpolation stays stable.
    for j in range(NY):
        for k in range(NZ):
            if front[j][k] is not None: continue
            vals=[]
            for d in range(1,5):
                for kk in (k-d,k+d):
                    if 0<=kk<NZ and front[j][kk] is not None: vals.append(front[j][kk])
                if vals: break
            if vals: front[j][k]=sum(vals)/len(vals)

    # Baseline per horizontal slice. Fit the non-breast lower/upper chest bands.
    baseline=[[None]*NZ for _ in range(NY)]
    aug=[[0.0]*NZ for _ in range(NY)]
    for j in range(NY):
        pts=[]
        for k in range(NZ):
            zc=z_center(k); f=front[j][k]
            if f is not None and (0.57<=zc<=0.635 or 0.945<=zc<=0.995):
                pts.append((zc,f))
        if len(pts)>=2:
            mz=sum(z for z,x in pts)/len(pts); mx=sum(x for z,x in pts)/len(pts)
            den=sum((z-mz)**2 for z,x in pts) or 1.0
            slope=sum((z-mz)*(x-mx) for z,x in pts)/den
            intercept=mx-slope*mz
        else:
            vals=[x for x in front[j] if x is not None]
            intercept=quantile(vals,0.25) if vals else 0.0; slope=0.0
        for k in range(NZ):
            base=intercept+slope*z_center(k)
            baseline[j][k]=base
            if front[j][k] is not None:
                aug[j][k]=max(0.0,front[j][k]-base)

    # Gentle 2D smoothing: preserve the real ALE shape while removing bin noise.
    sm=[[0.0]*NZ for _ in range(NY)]
    for j in range(NY):
        for k in range(NZ):
            vals=[]
            for dj,dk,w in ((0,0,4),(0,-1,2),(0,1,2),(-1,0,1),(1,0,1)):
                jj,kk=j+dj,k+dk
                if 0<=jj<NY and 0<=kk<NZ:
                    vals += [aug[jj][kk]]*w
            sm[j][k]=sum(vals)/len(vals) if vals else 0.0
    return {'front':front,'baseline':baseline,'aug':sm}

def sample_grid(grid,yn,zn):
    if yn<Y0 or yn>Y1 or zn<Z0 or zn>Z1: return 0.0
    fy=(yn-Y0)/(Y1-Y0)*NY-.5; fz=(zn-Z0)/(Z1-Z0)*NZ-.5
    j0=math.floor(fy); k0=math.floor(fz); ty=fy-j0; tz=fz-k0
    def g(j,k):
        j=max(0,min(NY-1,j)); k=max(0,min(NZ-1,k))
        v=grid[j][k]
        return 0.0 if v is None else v
    a=g(j0,k0)*(1-ty)+g(j0+1,k0)*ty
    b=g(j0,k0+1)*(1-ty)+g(j0+1,k0+1)*ty
    return a*(1-tz)+b*tz

def rmse_to_ref(profile,ref,lock,high):
    vals=[]
    for j in range(NY):
        yc=y_center(j)
        if yc>0.90: continue
        for k in range(NZ):
            zc=z_center(k)
            if not (lock<=zc<=high): continue
            vals.append((profile['aug'][j][k]-ref['aug'][j][k])**2)
    return math.sqrt(sum(vals)/len(vals)) if vals else None

def patch_race(race,cfg,ref_profile):
    m=load_model(cfg['m2'],cfg['skin'])
    src=m['bytes']; data=bytearray(src); before=build_profile(m)
    root=m['root']; torso=m['torso']; stature=m['stature']; arm_y=m['arm_y']; leg=m['leg']
    hip_z=root[2]-.055*stature
    hip_sz=max(.07,.095*stature)
    butt_sz=max(.07,cfg['butt_sz_stature']*stature)
    thigh_z=root[2]-.24*leg; thigh_sz=max(.09,.19*leg); thigh_y=.52*arm_y
    bb=cfg['butt_back_torso']*torso

    changed=0; breast_changed=0; breast_below_lock=0; maxd=0.0; max_breast_dx=0.0
    for i in m['eligible']:
        x,y,z=m['pos'][i]
        zn=(z-root[2])/torso; yn=abs(y)/max(1e-6,arm_y); xn=(x-m['cx'](z))/torso
        nx,ny=x,y

        # ALE chest transfer. No breast Y or Z edit.
        if cfg['belly_lock'] < zn < cfg['chest_high'] and Y0 <= yn <= Y1:
            cur_aug=sample_grid(before['aug'],yn,zn)
            ref_aug=sample_grid(ref_profile['aug'],yn,zn)
            cur_surface=sample_grid(before['front'],yn,zn)
            # Exact normalized ALE magnitude; race size comes naturally from its torso length.
            delta_n=ref_aug-cur_aug
            # Keep the transfer conservative per pass, but allow a small pull-back where a native tip
            # sticks farther out than the ALE curve. Surrounding zones are filled more strongly.
            delta_n=max(-0.055,min(0.155,delta_n))
            frontness=smoothstep(cur_surface-0.105,cur_surface-0.025,xn)
            # Outer side fades naturally; this is copied from ALE's y-profile rather than a made-up side push.
            side_fade=smoothstep(0.97,0.82,yn)
            dx=delta_n*torso*frontness*side_fade
            if abs(dx)>1e-7:
                nx += dx
                breast_changed += 1
                max_breast_dx=max(max_breast_dx,abs(dx))
                if zn <= cfg['belly_lock']: breast_below_lock += 1

        # Stable lower-body logic from v8; independent from the new ALE chest transfer.
        wh=gauss(z,hip_z,hip_sz)*max(0.0,1.0-(abs(ny)/(.27*stature+1e-6))**4)
        ny*=1+cfg['hip_widen']*wh

        tt=max(0.0,min(1.0,(z-root[2])/max(1e-6,torso)))
        cx=root[0]+tt*(m['sh'][0]-root[0])
        rear=smoothstep(cx+.025*stature,cx-.035*stature,x)
        guard=smoothstep(cx-.22*stature,cx-.10*stature,x)
        rawb=gauss(z,hip_z,butt_sz)*rear*guard*gauss(abs(ny),.50*arm_y,max(.045,.54*arm_y))
        wbut=(rawb**cfg['butt_power']) if rawb>0 else 0.0
        nx-=bb*wbut

        side=1 if ny>=0 else -1; ty=side*thigh_y
        wt=gauss(z,thigh_z,thigh_sz)*max(0.0,1.0-(abs(ny)/(.30*stature+1e-6))**6)
        tx=root[0]
        nx=tx+(nx-tx)*(1+cfg['thigh_full']*wt)
        ny=ty+(ny-ty)*(1+cfg['thigh_full']*wt)

        d=math.hypot(nx-x,ny-y)
        if d>1e-7:
            put3(data,m['vo']+i*48,(nx,ny,z)); changed+=1; maxd=max(maxd,d)

    # Hard binary invariant: only vertex X/Y bytes may differ; all Z bytes and all other M2 data stay exact.
    allowed=bytearray(len(src))
    for i in range(m['n']): allowed[m['vo']+i*48:m['vo']+i*48+8]=b'\x01'*8
    illegal=[k for k,(a,b) in enumerate(zip(src,data)) if a!=b and not allowed[k]]
    if illegal: raise RuntimeError(f'{race}: illegal byte changes outside vertex X/Y: {illegal[:10]}')
    if breast_below_lock: raise RuntimeError(f'{race}: breast transfer leaked below belly lock')

    after_model=load_model(cfg['m2'],cfg['skin'],bytes(data))
    after=build_profile(after_model)
    before_rmse=rmse_to_ref(before,ref_profile,cfg['belly_lock'],cfg['chest_high'])
    after_rmse=rmse_to_ref(after,ref_profile,cfg['belly_lock'],cfg['chest_high'])

    outdir=ROOT/'generated_v9_ale_transfer'/'Character'/race/'Female'
    outdir.mkdir(parents=True,exist_ok=True)
    outm=outdir/(cfg['out']+'.m2'); outs=outdir/(cfg['out']+'00.skin')
    outm.write_bytes(data); shutil.copy2(cfg['skin'],outs)

    return {
        'race':race,'method':'normalized BloodElf ALE front-surface augmentation transfer',
        'changed_vertices':changed,'breast_changed_vertices':breast_changed,
        'breast_below_belly_lock':breast_below_lock,'belly_lock_norm':cfg['belly_lock'],
        'max_breast_dx':max_breast_dx,'max_displacement_xy':maxd,
        'ale_profile_rmse_before':before_rmse,'ale_profile_rmse_after':after_rmse,
        'ale_profile_improved': (after_rmse is not None and before_rmse is not None and after_rmse < before_rmse),
        'source_sha256':sha(src),'output_sha256':sha(data),'skin_sha256':sha(cfg['skin'].read_bytes()),
        'only_vertex_xy_changed':True,'breast_changes_x_only':True,
        'eligible_sections':m['sections'],'lower_body':{k:cfg[k] for k in ('hip_widen','butt_back_torso','butt_sz_stature','butt_power','thigh_full')}
    }

def main():
    ref_model=load_model(REF_M2,REF_SKIN)
    ref_profile=build_profile(ref_model)
    report={
        'reference':{
            'model':str(REF_M2.relative_to(ROOT)),
            'skin':str(REF_SKIN.relative_to(ROOT)),
            'torso':ref_model['torso'],'arm_y':ref_model['arm_y'],
            'profile_grid':{'z':[Z0,Z1,NZ],'y':[Y0,Y1,NY],'front_quantile':FRONT_Q},
            'max_aug':max(max(row) for row in ref_profile['aug'])
        },
        'races':{}
    }
    for race,cfg in TARGETS.items():
        report['races'][race]=patch_race(race,cfg,ref_profile)
    (ROOT/'analysis').mkdir(exist_ok=True)
    (ROOT/'analysis'/'body_patch_v9_ale_transfer_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    main()
