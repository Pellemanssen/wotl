#!/usr/bin/env python3
import json, math, shutil, struct, hashlib
from pathlib import Path
import m2_body_patch_v9_ale_transfer as v9

ROOT=Path(__file__).resolve().parents[1]
OUTROOT=ROOT/'generated_v15_mass_surface'

CFG={
 'Orc':dict(mode='surface',m2=ROOT/'Orc Female/OrcFemale.m2',skin=ROOT/'Orc Female/OrcFemale00.skin',out='OrcFemale',
            zc=.760,hz=.185,hy=.390,target_peak=.525,blend=.82,pull=.45,yscale=.150,chest_low=.610,
            hip_widen=.170,butt_back_torso=.150,butt_sz_stature=.100,butt_power=.48,thigh_full=.112),
 'Draenei':dict(mode='native',m2=ROOT/'Draenai Female/DRAENEIFemale.m2',skin=ROOT/'Draenai Female/DRAENEIFemale00.skin',out='DraeneiFemale',
            zc=.890,hz=.170,hy=.355,xscale=.170,fill=.040,yscale=.115,chest_low=.735,
            hip_widen=.188,butt_back_torso=.110,butt_sz_stature=.092,butt_power=.47,thigh_full=.100),
 'Scourge':dict(mode='surface',m2=ROOT/'Scourge Female/ScourgeFemale.m2',skin=ROOT/'Scourge Female/ScourgeFemale00.skin',out='ScourgeFemale',
            zc=.740,hz=.190,hy=.395,target_peak=.360,blend=.86,pull=.55,yscale=.160,chest_low=.585,
            hip_widen=.148,butt_back_torso=.154,butt_sz_stature=.096,butt_power=.47,thigh_full=.095),
}

def u32(b,o): return struct.unpack_from('<I',b,o)[0]
def sha(b): return hashlib.sha256(b).hexdigest()
def q(a,p):
    if not a:return 0.0
    a=sorted(a);t=(len(a)-1)*p;lo=int(t);hi=min(len(a)-1,lo+1);f=t-lo
    return a[lo]*(1-f)+a[hi]*f

def sections(skin,n):
    b=Path(skin).read_bytes();ni,oi=u32(b,4),u32(b,8);ns,os=u32(b,28),u32(b,32)
    idx=[struct.unpack_from('<H',b,oi+i*2)[0] for i in range(ni)];r={}
    for a in range(ns):
        o=os+a*48;sid=struct.unpack_from('<H',b,o)[0];vs,vc=struct.unpack_from('<HH',b,o+4);s=r.setdefault(sid,set())
        for j in range(vs,min(vs+vc,len(idx))):
            if idx[j]<n:s.add(idx[j])
    return r

def plateau(rad):
    if rad<=.62:return 1.0
    if rad>=1.05:return 0.0
    return v9.smoothstep(1.05,.62,rad)

def detect(m,body,c):
    cand=[]
    for i in body:
        x,y,z=m['pos'][i];yn=abs(y)/max(m['arm_y'],1e-9);zn=(z-m['root'][2])/m['torso'];xn=(x-m['cx'](z))/m['torso']
        if .14<=yn<=.72 and abs(zn-c['zc'])<=.105 and xn>-.14:
            cand.append((xn,yn,zn))
    if len(cand)<10:raise RuntimeError('not enough native breast candidates')
    cut=q([r[0] for r in cand],.72);front=[r for r in cand if r[0]>=cut]
    yc=max(.34,min(.56,q([r[1] for r in front],.50)))
    return dict(yc=yc,base=q([r[0] for r in cand],.24),tip_lo=q([r[0] for r in cand],.82),tip_hi=q([r[0] for r in cand],.96),candidate_n=len(cand),front_n=len(front))

def surface_profile(u,v):
    # Broad super-ellipse: much flatter than a Gaussian at the centre, so the
    # upper/lower shell is filled instead of producing a cone.
    rr=(abs(u)**2.6 + abs(v)**2.6)
    if rr>=1.0:return 0.0
    return (1.0-rr)**0.42

def chest_surface(xn,yn,zn,st,c):
    if zn < c['chest_low']:return xn,0.0,0.0
    u=(yn-st['yc'])/c['hy'];v=(zn-c['zc'])/c['hz'];prof=surface_profile(u,v)
    if prof<=0:return xn,0.0,0.0
    front=v9.smoothstep(-.09,.08,xn)
    if front<=0:return xn,0.0,0.0
    target=st['base']+(c['target_peak']-st['base'])*prof
    tip=v9.smoothstep(st['tip_lo'],st['tip_hi'],xn)
    if xn <= target:
        desired=xn+(target-xn)*c['blend']*front
    else:
        # Real anti-tip action: only foremost rows are allowed to move backward.
        desired=xn+(target-xn)*c['pull']*tip*front
    return desired,prof*front,tip

def chest_native(xn,yn,zn,st,c):
    if zn < c['chest_low']:return xn,0.0,0.0
    u=abs(yn-st['yc'])/c['hy'];v=abs(zn-c['zc'])/c['hz'];rad=math.sqrt(u*u+v*v);w=plateau(rad)
    if w<=0:return xn,0.0,0.0
    front=v9.smoothstep(-.08,.10,xn)
    if front<=0:return xn,0.0,0.0
    tip=v9.smoothstep(st['tip_lo'],st['tip_hi'],xn)
    anchor_x=-.035
    # Same native-lobe shape that looked round on Draenei, only uniformly larger.
    xgain=c['xscale']*(1-.48*tip)
    dx=(xn-anchor_x)*xgain*w*front + c['fill']*(1-.72*tip)*w*front - .008*tip*w*front
    return xn+dx,w*front,tip

def patch(race,c):
    m=v9.load_model(c['m2'],c['skin']);src=m['bytes'];data=bytearray(src)
    sec=sections(c['skin'],m['n']);body=set(sec.get(0,set()));eligible=set(m['eligible']);st=detect(m,body,c)
    root=m['root'];torso=m['torso'];stature=m['stature'];arm=m['arm_y'];leg=m['leg']
    hip_z=root[2]-.055*stature;hip_sz=max(.07,.095*stature);butt_sz=max(.07,c['butt_sz_stature']*stature)
    thigh_z=root[2]-.24*leg;thigh_sz=max(.09,.19*leg);thigh_y=.52*arm;bb=c['butt_back_torso']*torso
    bchg=gchg=pos=neg=0;dxs=[];ap=[];shell=[];below=0;maxd=0

    for i in eligible:
        x,y,z=m['pos'][i];nx,ny=x,y
        zn=(z-root[2])/torso;yn=abs(y)/max(arm,1e-9);xn=(x-m['cx'](z))/torso
        if c['mode']=='surface': newxn,w,tip=chest_surface(xn,yn,zn,st,c)
        else: newxn,w,tip=chest_native(xn,yn,zn,st,c)
        if w>0 and abs(newxn-xn)>1e-9:
            dx=(newxn-xn)*torso;nx+=dx
            side=1 if y>=0 else -1;cy=side*st['yc']*arm
            ny+=(y-cy)*c['yscale']*w
            if i in body:
                bchg+=1;nd=dx/torso;dxs.append(nd)
                if nd>1e-6:pos+=1
                elif nd<-1e-6:neg+=1
                if zn<c['chest_low']:below+=1
                if tip>=.65 and abs(zn-c['zc'])<=.055:ap.append(nd)
                elif abs(zn-c['zc'])<=.115 and abs(yn-st['yc'])<=.31:shell.append(nd)
            else:gchg+=1

        # Lower-body tuning carried over unchanged from the accepted v13 test.
        wh=v9.gauss(z,hip_z,hip_sz)*max(0.0,1.0-(abs(ny)/(.27*stature+1e-6))**4);ny*=1+c['hip_widen']*wh
        tt=max(0,min(1,(z-root[2])/max(1e-6,torso)));cx=root[0]+tt*(m['sh'][0]-root[0])
        rear=v9.smoothstep(cx+.025*stature,cx-.035*stature,x);guard=v9.smoothstep(cx-.22*stature,cx-.10*stature,x)
        raw=v9.gauss(z,hip_z,butt_sz)*rear*guard*v9.gauss(abs(ny),.50*arm,max(.045,.54*arm));wb=raw**c['butt_power'] if raw>0 else 0
        nx-=bb*wb
        side=1 if ny>=0 else -1;ty=side*thigh_y;wt=v9.gauss(z,thigh_z,thigh_sz)*max(0.0,1.0-(abs(ny)/(.30*stature+1e-6))**6)
        nx=root[0]+(nx-root[0])*(1+c['thigh_full']*wt);ny=ty+(ny-ty)*(1+c['thigh_full']*wt)
        d=math.hypot(nx-x,ny-y)
        if d>1e-7:v9.put3(data,m['vo']+i*48,(nx,ny,z));maxd=max(maxd,d)

    allowed=bytearray(len(src))
    for i in range(m['n']):allowed[m['vo']+i*48:m['vo']+i*48+8]=b'\1'*8
    bad=[i for i,(a,b) in enumerate(zip(src,data)) if a!=b and not allowed[i]]
    if bad:raise RuntimeError(f'{race}: illegal non-XY bytes {bad[:8]}')
    od=OUTROOT/'Character'/race/'Female';od.mkdir(parents=True,exist_ok=True);om=od/(c['out']+'.m2');os=od/(c['out']+'00.skin')
    om.write_bytes(data);shutil.copy2(c['skin'],os)
    apm=sum(ap)/len(ap) if ap else 0.0;shm=sum(shell)/len(shell) if shell else 0.0
    return dict(race=race,mode=c['mode'],native=st,body_chest_changed=bchg,replacement_chest_changed=gchg,
                body_positive_dx=pos,body_negative_dx=neg,body_dx_min=min(dxs) if dxs else 0,body_dx_max=max(dxs) if dxs else 0,
                apex_mean_dx=apm,shell_mean_dx=shm,apex_n=len(ap),shell_n=len(shell),breast_below_chest_low=below,
                max_displacement_xy=maxd,only_vertex_xy_changed=True,z_unchanged=True,
                source_sha256=sha(src),output_sha256=sha(data),skin_sha256=sha(c['skin'].read_bytes()))

def main():
    if OUTROOT.exists():shutil.rmtree(OUTROOT)
    r={'version':'v15 per-race mass surface','races':{}}
    for race,c in CFG.items():r['races'][race]=patch(race,c)
    (ROOT/'analysis').mkdir(exist_ok=True);(ROOT/'analysis/body_patch_v15_mass_surface_report.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))
if __name__=='__main__':main()
