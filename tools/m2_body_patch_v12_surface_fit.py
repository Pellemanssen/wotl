#!/usr/bin/env python3
import json, math, shutil, struct, hashlib
from pathlib import Path
import m2_body_patch_v9_ale_transfer as v9

ROOT = Path(__file__).resolve().parents[1]
OUTROOT = ROOT/'generated_v12_surface_fit'

# v12 is a structural rewrite, not a v11 parameter tune.
# The breast SHAPE is derived from body submesh 0 only. Every race keeps its own
# anatomical vertical centre. The front surface is fitted to an absolute broad cap;
# we do not add the same projection delta to every vertex in a profile cell.
# Z stays byte-identical for rig safety. Other supported torso geosets receive the
# body-surface delta so shirts/body replacements follow without defining the shape.
TARGETS = {
    'Orc': {
        'm2': ROOT/'Orc Female'/'OrcFemale.m2', 'skin': ROOT/'Orc Female'/'OrcFemale00.skin', 'out':'OrcFemale',
        'zc':0.780, 'hz':0.118, 'yc':0.445, 'hy':0.310, 'peak':0.122,
        'side_gain':0.020,
        'hip_widen':0.170, 'butt_back_torso':0.150, 'butt_sz_stature':0.100, 'butt_power':0.48, 'thigh_full':0.112,
    },
    'Draenei': {
        'm2': ROOT/'Draenai Female'/'DRAENEIFemale.m2', 'skin': ROOT/'Draenai Female'/'DRAENEIFemale00.skin', 'out':'DraeneiFemale',
        'zc':0.842, 'hz':0.122, 'yc':0.440, 'hy':0.315, 'peak':0.135,
        'side_gain':0.022,
        'hip_widen':0.188, 'butt_back_torso':0.110, 'butt_sz_stature':0.092, 'butt_power':0.47, 'thigh_full':0.100,
    },
    'Scourge': {
        'm2': ROOT/'Scourge Female'/'ScourgeFemale.m2', 'skin': ROOT/'Scourge Female'/'ScourgeFemale00.skin', 'out':'ScourgeFemale',
        'zc':0.755, 'hz':0.120, 'yc':0.445, 'hy':0.315, 'peak':0.125,
        'side_gain':0.020,
        'hip_widen':0.148, 'butt_back_torso':0.154, 'butt_sz_stature':0.096, 'butt_power':0.47, 'thigh_full':0.095,
    },
}

Y0,Y1,NY = 0.06,0.84,35
Z0,Z1,NZ = 0.54,1.01,65

def u32(b,o): return struct.unpack_from('<I',b,o)[0]
def sha(b): return hashlib.sha256(b).hexdigest()

def quantile(a,q):
    if not a: return None
    a=sorted(a); x=(len(a)-1)*q; lo=int(x); hi=min(len(a)-1,lo+1); t=x-lo
    return a[lo]*(1-t)+a[hi]*t

def section_vertex_sets(skin,nverts):
    b=Path(skin).read_bytes()
    if b[:4]!=b'SKIN': raise ValueError('invalid SKIN')
    nidx,oidx=u32(b,4),u32(b,8); nsub,osub=u32(b,28),u32(b,32)
    idx=[struct.unpack_from('<H',b,oidx+i*2)[0] for i in range(nidx)]
    out={}
    for i in range(nsub):
        o=osub+i*48; sid=struct.unpack_from('<H',b,o)[0]
        vs=struct.unpack_from('<H',b,o+4)[0]; vc=struct.unpack_from('<H',b,o+6)[0]
        s=out.setdefault(sid,set())
        for j in range(vs,min(vs+vc,len(idx))):
            vi=idx[j]
            if vi<nverts: s.add(vi)
    return out

def build_body_front(m,body):
    cells=[[[] for _ in range(NZ)] for _ in range(NY)]
    for i in body:
        x,y,z=m['pos'][i]
        yn=abs(y)/max(1e-8,m['arm_y']); zn=(z-m['root'][2])/m['torso']
        if not (Y0<=yn<Y1 and Z0<=zn<Z1): continue
        xn=(x-m['cx'](z))/m['torso']
        if xn<-.24: continue
        j=min(NY-1,max(0,int((yn-Y0)/(Y1-Y0)*NY)))
        k=min(NZ-1,max(0,int((zn-Z0)/(Z1-Z0)*NZ)))
        cells[j][k].append(xn)
    front=[[quantile(cells[j][k],.95) for k in range(NZ)] for j in range(NY)]
    # Fill sparse cells from nearby body-only neighbours. Never use equipment geosets.
    for _ in range(5):
        changed=False
        old=[r[:] for r in front]
        for j in range(NY):
            for k in range(NZ):
                if old[j][k] is not None: continue
                vals=[]
                for dj,dk in ((0,-1),(0,1),(-1,0),(1,0),(-1,-1),(-1,1),(1,-1),(1,1)):
                    jj,kk=j+dj,k+dk
                    if 0<=jj<NY and 0<=kk<NZ and old[jj][kk] is not None: vals.append(old[jj][kk])
                if vals:
                    front[j][k]=sum(vals)/len(vals); changed=True
        if not changed: break
    return front

def sample(grid,yn,zn):
    yn=max(Y0,min(Y1-1e-7,yn)); zn=max(Z0,min(Z1-1e-7,zn))
    fy=(yn-Y0)/(Y1-Y0)*NY-.5; fz=(zn-Z0)/(Z1-Z0)*NZ-.5
    j0=math.floor(fy); k0=math.floor(fz); ty=fy-j0; tz=fz-k0
    def g(j,k):
        j=max(0,min(NY-1,j)); k=max(0,min(NZ-1,k)); v=grid[j][k]
        if v is not None:return v
        # deterministic nearest fallback
        for d in range(1,10):
            vals=[]
            for jj in range(max(0,j-d),min(NY,j+d+1)):
                for kk in range(max(0,k-d),min(NZ,k+d+1)):
                    if grid[jj][kk] is not None: vals.append(grid[jj][kk])
            if vals:return sum(vals)/len(vals)
        return 0.0
    a=g(j0,k0)*(1-ty)+g(j0+1,k0)*ty
    b=g(j0,k0+1)*(1-ty)+g(j0+1,k0+1)*ty
    return a*(1-tz)+b*tz

def shape_terms(cfg,yn,zn):
    uy=abs(yn-cfg['yc'])/cfg['hy']
    uz=abs(zn-cfg['zc'])/cfg['hz']
    if uy>=1 or uz>=1: return 0.0,0.0,0.0
    # Wide lateral lobe with a separate sternum. The vertical 2.2-power cap has a
    # deliberately broad crown: neighbouring rows retain almost the apex depth.
    lat=(max(0.0,1.0-uy*uy))**0.72
    vert=(max(0.0,1.0-uz**2.2))**0.65
    zone=lat*vert
    return lat,vert,zone

def baseline(front,cfg,yn,zn):
    zl=max(Z0+0.005,cfg['zc']-cfg['hz']*1.08)
    zh=min(Z1-0.005,cfg['zc']+cfg['hz']*1.08)
    xl=sample(front,yn,zl); xh=sample(front,yn,zh)
    t=max(0.0,min(1.0,(zn-zl)/max(1e-8,zh-zl)))
    return xl*(1-t)+xh*t

def desired_front(front,cfg,yn,zn):
    lat,vert,zone=shape_terms(cfg,yn,zn)
    cur=sample(front,yn,zn)
    if zone<=0:return cur,0.0
    base=baseline(front,cfg,yn,zn)
    target=base + cfg['peak']*lat*vert
    # Fade from untouched native surface into the absolute target at the lobe edge.
    edge=v9.smoothstep(0.03,0.18,zone)
    return cur + (target-cur)*edge, edge

def patch_race(race,cfg):
    m=v9.load_model(cfg['m2'],cfg['skin'])
    src=m['bytes']; data=bytearray(src)
    sec=section_vertex_sets(cfg['skin'],m['n'])
    body=set(sec.get(0,set()))
    if len(body)<500: raise RuntimeError(f'{race}: body submesh 0 unavailable')
    front=build_body_front(m,body)
    eligible=set(m['eligible']); other=eligible-body

    root=m['root']; torso=m['torso']; stature=m['stature']; arm_y=m['arm_y']; leg=m['leg']
    # Delta field used only to make replacement/clothing torso geosets follow body0.
    def surface_delta(yn,zn):
        desired,edge=desired_front(front,cfg,yn,zn)
        return (desired-sample(front,yn,zn))*edge

    hip_z=root[2]-.055*stature; hip_sz=max(.07,.095*stature)
    butt_sz=max(.07,cfg['butt_sz_stature']*stature)
    thigh_z=root[2]-.24*leg; thigh_sz=max(.09,.19*leg); thigh_y=.52*arm_y
    bb=cfg['butt_back_torso']*torso

    changed=body_changed=gear_changed=0
    chest_pos=chest_neg=0
    body_dx=[]; apex_dx=[]; shell_dx=[]
    maxd=0.0

    for i in eligible:
        x,y,z=m['pos'][i]
        zn=(z-root[2])/torso; yn=abs(y)/max(1e-8,arm_y); xn=(x-m['cx'](z))/torso
        nx,ny=x,y

        # Breast rewrite only inside race-aligned lobe footprint.
        lat,vert,zone=shape_terms(cfg,yn,zn)
        if zone>0.015:
            cur_front=sample(front,yn,zn)
            # Only the front shell; back/inner torso is untouched.
            frontness=v9.smoothstep(cur_front-.075,cur_front-.008,xn)
            if i in body:
                desired,edge=desired_front(front,cfg,yn,zn)
                dnorm=(desired-xn)*frontness
                # The apex is deliberately NOT given an extra push. Each actual vertex
                # is fitted to the same broad surface, so a protruding tip can move back.
                dx=dnorm*torso
                # Mild circumference only; do not use Y to fake side-view roundness.
                dy=(1 if y>=0 else -1)*cfg['side_gain']*torso*lat*vert*frontness
                if abs(dx)>1e-7 or abs(dy)>1e-7:
                    nx+=dx; ny+=dy; body_changed+=1
                    ndx=dx/torso; body_dx.append(ndx)
                    if ndx>1e-6: chest_pos+=1
                    elif ndx<-1e-6: chest_neg+=1
                    if abs(zn-cfg['zc'])<=.025 and abs(yn-cfg['yc'])<=.16: apex_dx.append(ndx)
                    elif abs(zn-cfg['zc'])<=cfg['hz']*.80 and abs(yn-cfg['yc'])<=cfg['hy']*.82: shell_dx.append(ndx)
            elif i in other:
                dnorm=surface_delta(yn,zn)
                # Replacement geosets preserve their own offset from the body shell.
                gearfront=v9.smoothstep(cur_front-.12,cur_front-.015,xn)
                dx=dnorm*torso*gearfront
                dy=(1 if y>=0 else -1)*cfg['side_gain']*torso*lat*vert*gearfront
                if abs(dx)>1e-7 or abs(dy)>1e-7:
                    nx+=dx; ny+=dy; gear_changed+=1

        # Stable lower body, unchanged from v11 tuning.
        wh=v9.gauss(z,hip_z,hip_sz)*max(0.0,1.0-(abs(ny)/(.27*stature+1e-6))**4)
        ny*=1+cfg['hip_widen']*wh
        tt=max(0.0,min(1.0,(z-root[2])/max(1e-6,torso)))
        cx=root[0]+tt*(m['sh'][0]-root[0])
        rear=v9.smoothstep(cx+.025*stature,cx-.035*stature,x)
        guard=v9.smoothstep(cx-.22*stature,cx-.10*stature,x)
        rawb=v9.gauss(z,hip_z,butt_sz)*rear*guard*v9.gauss(abs(ny),.50*arm_y,max(.045,.54*arm_y))
        wbut=(rawb**cfg['butt_power']) if rawb>0 else 0.0
        nx-=bb*wbut
        side=1 if ny>=0 else -1; ty=side*thigh_y
        wt=v9.gauss(z,thigh_z,thigh_sz)*max(0.0,1.0-(abs(ny)/(.30*stature+1e-6))**6)
        tx=root[0]; nx=tx+(nx-tx)*(1+cfg['thigh_full']*wt); ny=ty+(ny-ty)*(1+cfg['thigh_full']*wt)

        d=math.hypot(nx-x,ny-y)
        if d>1e-7:
            v9.put3(data,m['vo']+i*48,(nx,ny,z)); changed+=1; maxd=max(maxd,d)

    # Byte safety: X/Y only, Z and every other byte unchanged.
    allowed=bytearray(len(src))
    for i in range(m['n']): allowed[m['vo']+i*48:m['vo']+i*48+8]=b'\x01'*8
    illegal=[k for k,(a,b) in enumerate(zip(src,data)) if a!=b and not allowed[k]]
    if illegal: raise RuntimeError(f'{race}: illegal bytes outside vertex XY: {illegal[:8]}')

    outdir=OUTROOT/'Character'/race/'Female'; outdir.mkdir(parents=True,exist_ok=True)
    outm=outdir/(cfg['out']+'.m2'); outs=outdir/(cfg['out']+'00.skin')
    outm.write_bytes(data); shutil.copy2(cfg['skin'],outs)

    return {
        'race':race,'method':'body0 absolute broad surface fit','changed_vertices':changed,
        'body_chest_changed':body_changed,'replacement_chest_changed':gear_changed,
        'body_positive_dx':chest_pos,'body_negative_dx':chest_neg,
        'body_dx_min':min(body_dx) if body_dx else 0,'body_dx_max':max(body_dx) if body_dx else 0,
        'apex_mean_dx':sum(apex_dx)/len(apex_dx) if apex_dx else 0,
        'shell_mean_dx':sum(shell_dx)/len(shell_dx) if shell_dx else 0,
        'apex_n':len(apex_dx),'shell_n':len(shell_dx),'body0_vertices':len(body),
        'max_displacement_xy':maxd,'only_vertex_xy_changed':True,'z_unchanged':True,
        'source_sha256':sha(src),'output_sha256':sha(data),'skin_sha256':sha(cfg['skin'].read_bytes()),
        'shape':{k:cfg[k] for k in ('zc','hz','yc','hy','peak','side_gain')},
    }

def main():
    if OUTROOT.exists(): shutil.rmtree(OUTROOT)
    report={'version':'v12 surface-fit structural rewrite','races':{}}
    for race,cfg in TARGETS.items(): report['races'][race]=patch_race(race,cfg)
    (ROOT/'analysis').mkdir(exist_ok=True)
    p=ROOT/'analysis'/'body_patch_v12_surface_fit_report.json'; p.write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))

if __name__=='__main__': main()
