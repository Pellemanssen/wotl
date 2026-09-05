#!/usr/bin/env python3
import json, math, shutil, struct, hashlib
from pathlib import Path
import m2_body_patch_v9_ale_transfer as v9

ROOT=Path(__file__).resolve().parents[1]
OUTROOT=ROOT/'generated_v14_shape_search'

RACES={
 'Orc':dict(m2=ROOT/'Orc Female/OrcFemale.m2',skin=ROOT/'Orc Female/OrcFemale00.skin',out='OrcFemale',zc=.760,peak_min=.110,peak_max=.145,fwhm_min=.190,yscale=.115,
            hip_widen=.170,butt_back_torso=.150,butt_sz_stature=.100,butt_power=.48,thigh_full=.112),
 'Draenei':dict(m2=ROOT/'Draenai Female/DRAENEIFemale.m2',skin=ROOT/'Draenai Female/DRAENEIFemale00.skin',out='DraeneiFemale',zc=.850,peak_min=.120,peak_max=.155,fwhm_min=.180,yscale=.095,
            hip_widen=.188,butt_back_torso=.110,butt_sz_stature=.092,butt_power=.47,thigh_full=.100),
 'Scourge':dict(m2=ROOT/'Scourge Female/ScourgeFemale.m2',skin=ROOT/'Scourge Female/ScourgeFemale00.skin',out='ScourgeFemale',zc=.740,peak_min=.095,peak_max=.135,fwhm_min=.170,yscale=.120,
            hip_widen=.148,butt_back_torso=.154,butt_sz_stature=.096,butt_power=.47,thigh_full=.095),
}

def u32(b,o):return struct.unpack_from('<I',b,o)[0]
def sha(b):return hashlib.sha256(b).hexdigest()
def q(a,p):
    if not a:return 0.0
    a=sorted(a);t=(len(a)-1)*p;l=int(t);h=min(len(a)-1,l+1);f=t-l
    return a[l]*(1-f)+a[h]*f

def section_sets(skin,n):
    b=Path(skin).read_bytes();ni,oi=u32(b,4),u32(b,8);ns,os=u32(b,28),u32(b,32)
    idx=[struct.unpack_from('<H',b,oi+i*2)[0] for i in range(ni)];out={}
    for a in range(ns):
        o=os+a*48;sid=struct.unpack_from('<H',b,o)[0];vs,vc=struct.unpack_from('<HH',b,o+4);s=out.setdefault(sid,set())
        for j in range(vs,min(vs+vc,len(idx))):
            if idx[j]<n:s.add(idx[j])
    return out

def native_stats(m,body,c):
    pts=[]
    for i in body:
        x,y,z=m['pos'][i];yn=abs(y)/max(m['arm_y'],1e-9);zn=(z-m['root'][2])/m['torso'];xn=(x-m['cx'](z))/m['torso']
        if .14<=yn<=.72 and abs(zn-c['zc'])<=.11 and xn>-.14:pts.append((xn,yn,zn))
    if len(pts)<12:raise RuntimeError('too few native breast points')
    cut=q([p[0] for p in pts],.68);front=[p for p in pts if p[0]>=cut]
    yc=max(.34,min(.56,q([p[1] for p in front],.50)))
    return dict(yc=yc,tip_lo=q([p[0] for p in pts],.82),tip_hi=q([p[0] for p in pts],.96),n=len(pts))

def plateau(rad):
    if rad<=.55:return 1.0
    if rad>=1.10:return 0.0
    return v9.smoothstep(1.10,.55,rad)

def chest_delta(xn,yn,zn,st,hz,amp,suppress,trim):
    uy=abs(yn-st['yc'])/.37;uz=abs(zn-st['zc'])/hz;rad=math.sqrt(uy*uy+uz*uz);w=plateau(rad)
    if w<=0:return 0.0,w,0.0
    front=v9.smoothstep(-.10,.10,xn)
    tip=v9.smoothstep(st['tip_lo'],st['tip_hi'],xn)
    # Key constraint: broad displacement is independent of current X. The native tip
    # explicitly receives LESS displacement, and can be pulled back a little.
    dx=(amp*(1.0-suppress*tip)-trim*tip)*w*front
    return dx,w,tip

def smooth_curve(points,zc,st,params=None):
    # points: (xn,yn,zn); if params supplied evaluate transformed X.
    zs=[zc-.16+i*.004 for i in range(81)];raw=[]
    for zz in zs:
        vals=[]
        for xn,yn,zn in points:
            if .17<=yn<=.67 and abs(zn-zz)<=.018:
                xx=xn
                if params:
                    dx,_,_=chest_delta(xn,yn,zn,st,*params);xx+=dx
                if xx>-.20:vals.append(xx)
        raw.append(q(vals,.97) if len(vals)>=2 else (max(vals) if vals else None))
    for k in range(len(raw)):
        if raw[k] is not None:continue
        vals=[]
        for d in range(1,8):
            for kk in (k-d,k+d):
                if 0<=kk<len(raw) and raw[kk] is not None:vals.append(raw[kk])
            if vals:break
        raw[k]=sum(vals)/len(vals) if vals else 0
    sm=[]
    for k in range(len(raw)):
        total=0;ws=0
        for d,w in ((-2,1),(-1,2),(0,3),(1,2),(2,1)):
            kk=max(0,min(len(raw)-1,k+d));total+=raw[kk]*w;ws+=w
        sm.append(total/ws)
    # Endpoints are outside every searched lobe (max hz .22 * 1.10 = .242 but
    # plateau is already strongly faded at +- .16); use robust first/last bands.
    xl=sum(sm[:5])/5;xh=sum(sm[-5:])/5;zl=zs[2];zh=zs[-3]
    dep=[max(0.0,x-(xl+(xh-xl)*(z-zl)/(zh-zl))) for x,z in zip(sm,zs)]
    ks=[i for i,z in enumerate(zs) if abs(z-zc)<=.09];kp=max(ks,key=lambda i:dep[i]);pk=dep[kp];zp=zs[kp]
    def at(d):return dep[min(range(len(zs)),key=lambda i:abs(zs[i]-(zp+d)))]
    half=[zs[i] for i in range(len(zs)) if dep[i]>=pk*.5]
    area=sum(dep)*.004
    return dict(zs=zs,x=sm,dep=dep,zpeak=zp,peak=pk,s02=(at(-.02)+at(.02))/2/max(pk,1e-9),s04=(at(-.04)+at(.04))/2/max(pk,1e-9),s06=(at(-.06)+at(.06))/2/max(pk,1e-9),s07=(at(-.07)+at(.07))/2/max(pk,1e-9),s08=(at(-.08)+at(.08))/2/max(pk,1e-9),fwhm=max(half)-min(half) if half else 0,area=area)

def displacement_stats(points,st,params):
    ap=[];shell=[];allv=[]
    for xn,yn,zn in points:
        dx,w,tip=chest_delta(xn,yn,zn,st,*params)
        if w<=.08 or dx==0:continue
        allv.append(dx)
        if tip>=.72 and abs(zn-st['zc'])<=.06:ap.append(dx)
        elif tip<=.45 and abs(zn-st['zc'])<=.11 and abs(yn-st['yc'])<=.28:shell.append(dx)
    return dict(apex=sum(ap)/len(ap) if ap else 0,shell=sum(shell)/len(shell) if shell else 0,apex_n=len(ap),shell_n=len(shell),minimum=min(allv) if allv else 0,maximum=max(allv) if allv else 0,negative=sum(d<0 for d in allv),positive=sum(d>0 for d in allv))

def choose(m,body,c,st):
    points=[]
    for i in body:
        x,y,z=m['pos'][i];points.append(((x-m['cx'](z))/m['torso'],abs(y)/max(m['arm_y'],1e-9),(z-m['root'][2])/m['torso']))
    orig=smooth_curve(points,c['zc'],st,None)
    feasible=[];tested=0
    for hz in (.165,.175,.185,.195,.205,.215):
      for amp in (.055,.065,.075,.085,.095,.105,.115):
       for suppress in (.65,.72,.79,.86,.93):
        for trim in (.000,.006,.012,.018,.024):
            tested+=1;par=(hz,amp,suppress,trim);cur=smooth_curve(points,c['zc'],st,par);ds=displacement_stats(points,st,par)
            # Hard no-cone / no-peak-shift gates. These are intentionally strict.
            if not(c['peak_min']<=cur['peak']<=c['peak_max']):continue
            if cur['s04']<.72 or cur['s07']<.55:continue
            if cur['fwhm']<c['fwhm_min']:continue
            if abs(cur['zpeak']-c['zc'])>.045:continue
            if ds['shell_n']<8:continue
            if ds['apex_n'] and ds['apex']>ds['shell']*.80+.003:continue
            if ds['maximum']>.125 or ds['minimum']<-.035:continue
            # Prefer maximum broad volume, then shoulder fullness, but penalize high peak.
            score=cur['area']*10 + cur['s04']*.08 + cur['s07']*.04 - cur['peak']*.10
            feasible.append((score,par,cur,ds))
    if not feasible:raise RuntimeError(f'No constrained round solution for {c}')
    feasible.sort(key=lambda x:x[0],reverse=True);score,par,cur,ds=feasible[0]
    return dict(tested=tested,feasible=len(feasible),params=dict(hz=par[0],amp=par[1],suppress=par[2],trim=par[3]),original=orig,selected=cur,displacement=ds,score=score),points

def patch_race(race,c):
    m=v9.load_model(c['m2'],c['skin']);src=m['bytes'];data=bytearray(src);sec=section_sets(c['skin'],m['n']);body=set(sec.get(0,set()));eligible=set(m['eligible']);st=native_stats(m,body,c);st['zc']=c['zc']
    search,points=choose(m,body,c,st);p=search['params'];params=(p['hz'],p['amp'],p['suppress'],p['trim'])
    root=m['root'];torso=m['torso'];stature=m['stature'];arm=m['arm_y'];leg=m['leg']
    hip_z=root[2]-.055*stature;hip_sz=max(.07,.095*stature);butt_sz=max(.07,c['butt_sz_stature']*stature);thigh_z=root[2]-.24*leg;thigh_sz=max(.09,.19*leg);thigh_y=.52*arm;bb=c['butt_back_torso']*torso
    bodychg=otherchg=0;maxd=0
    for i in eligible:
        x,y,z=m['pos'][i];nx,ny=x,y;xn=(x-m['cx'](z))/torso;yn=abs(y)/max(arm,1e-9);zn=(z-root[2])/torso
        dxn,w,tip=chest_delta(xn,yn,zn,st,*params)
        if abs(dxn)>1e-8:
            nx+=dxn*torso
            side=1 if y>=0 else -1;cy=side*st['yc']*arm
            ny+=(y-cy)*c['yscale']*w*v9.smoothstep(-.10,.10,xn)
            if i in body:bodychg+=1
            else:otherchg+=1
        wh=v9.gauss(z,hip_z,hip_sz)*max(0.0,1.0-(abs(ny)/(.27*stature+1e-6))**4);ny*=1+c['hip_widen']*wh
        tt=max(0,min(1,(z-root[2])/max(1e-6,torso)));cx=root[0]+tt*(m['sh'][0]-root[0]);rear=v9.smoothstep(cx+.025*stature,cx-.035*stature,x);guard=v9.smoothstep(cx-.22*stature,cx-.10*stature,x)
        raw=v9.gauss(z,hip_z,butt_sz)*rear*guard*v9.gauss(abs(ny),.50*arm,max(.045,.54*arm));wb=raw**c['butt_power'] if raw>0 else 0;nx-=bb*wb
        side=1 if ny>=0 else -1;ty=side*thigh_y;wt=v9.gauss(z,thigh_z,thigh_sz)*max(0.0,1.0-(abs(ny)/(.30*stature+1e-6))**6);nx=root[0]+(nx-root[0])*(1+c['thigh_full']*wt);ny=ty+(ny-ty)*(1+c['thigh_full']*wt)
        d=math.hypot(nx-x,ny-y)
        if d>1e-7:v9.put3(data,m['vo']+i*48,(nx,ny,z));maxd=max(maxd,d)
    allowed=bytearray(len(src))
    for i in range(m['n']):allowed[m['vo']+i*48:m['vo']+i*48+8]=b'\1'*8
    bad=[k for k,(a,b) in enumerate(zip(src,data)) if a!=b and not allowed[k]]
    if bad:raise RuntimeError(f'{race}: illegal non-XY changes {bad[:8]}')
    od=OUTROOT/'Character'/race/'Female';od.mkdir(parents=True,exist_ok=True);om=od/(c['out']+'.m2');os=od/(c['out']+'00.skin');om.write_bytes(data);shutil.copy2(c['skin'],os)
    def small(d):return {k:v for k,v in d.items() if k not in ('zs','x','dep')}
    search['original']=small(search['original']);search['selected']=small(search['selected'])
    return dict(race=race,method='constrained broad-shell search; tip displacement capped',native=st,search=search,body_chest_changed=bodychg,other_chest_changed=otherchg,max_displacement_xy=maxd,only_vertex_xy_changed=True,z_unchanged=True,source_sha256=sha(src),output_sha256=sha(data),skin_sha256=sha(c['skin'].read_bytes()))

def main():
    if OUTROOT.exists():shutil.rmtree(OUTROOT)
    rep={'version':'v14 constrained shape search','races':{}}
    for race,c in RACES.items():rep['races'][race]=patch_race(race,c)
    (ROOT/'analysis').mkdir(exist_ok=True);(ROOT/'analysis/body_patch_v14_shape_search_report.json').write_text(json.dumps(rep,indent=2));print(json.dumps(rep,indent=2))
if __name__=='__main__':main()
