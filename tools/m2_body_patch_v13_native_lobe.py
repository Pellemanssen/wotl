#!/usr/bin/env python3
import json, math, shutil, struct, hashlib
from pathlib import Path
import m2_body_patch_v9_ale_transfer as v9

ROOT=Path(__file__).resolve().parents[1]
OUTROOT=ROOT/'generated_v13_native_lobe'

# Structural approach: enlarge each race's own native breast lobe instead of imposing
# a Blood-Elf Gaussian/profile. The centre zone is a plateau, so the apex and its
# neighbours are transformed together. The native foremost vertices receive LESS
# added X than the surrounding shell. Z is never changed.
CFG={
 'Orc':dict(m2=ROOT/'Orc Female/OrcFemale.m2',skin=ROOT/'Orc Female/OrcFemale00.skin',out='OrcFemale',zc=.760,hz=.170,hy=.350,xscale=.20,fill=.035,yscale=.115,
            hip_widen=.170,butt_back_torso=.150,butt_sz_stature=.100,butt_power=.48,thigh_full=.112),
 'Draenei':dict(m2=ROOT/'Draenai Female/DRAENEIFemale.m2',skin=ROOT/'Draenai Female/DRAENEIFemale00.skin',out='DraeneiFemale',zc=.890,hz=.165,hy=.345,xscale=.13,fill=.027,yscale=.095,
            hip_widen=.188,butt_back_torso=.110,butt_sz_stature=.092,butt_power=.47,thigh_full=.100),
 'Scourge':dict(m2=ROOT/'Scourge Female/ScourgeFemale.m2',skin=ROOT/'Scourge Female/ScourgeFemale00.skin',out='ScourgeFemale',zc=.740,hz=.175,hy=.350,xscale=.22,fill=.038,yscale=.120,
            hip_widen=.148,butt_back_torso=.154,butt_sz_stature=.096,butt_power=.47,thigh_full=.095),
}

def u32(b,o):return struct.unpack_from('<I',b,o)[0]
def sha(b):return hashlib.sha256(b).hexdigest()
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

def plateau(qr):
    if qr<=.60:return 1.0
    if qr>=1.08:return 0.0
    return v9.smoothstep(1.08,.60,qr)

def detect_lobe_stats(m,body,c):
    cand=[]
    for i in body:
        x,y,z=m['pos'][i];yn=abs(y)/max(m['arm_y'],1e-9);zn=(z-m['root'][2])/m['torso'];xn=(x-m['cx'](z))/m['torso']
        if .14<=yn<=.72 and abs(zn-c['zc'])<=.095 and xn>-.12:cand.append((xn,yn,zn))
    if len(cand)<10:raise RuntimeError('not enough native breast candidates')
    cut=q([r[0] for r in cand],.72);front=[r for r in cand if r[0]>=cut]
    yc=q([r[1] for r in front],.50);yc=max(.34,min(.56,yc))
    x80=q([r[0] for r in cand],.80);x94=q([r[0] for r in cand],.94)
    if x94<=x80:x94=x80+.02
    return {'yc':yc,'tip_lo':x80,'tip_hi':x94,'candidate_n':len(cand),'front_n':len(front)}

def patch(race,c):
    m=v9.load_model(c['m2'],c['skin']);src=m['bytes'];data=bytearray(src)
    sec=sections(c['skin'],m['n']);body=set(sec.get(0,set()));eligible=set(m['eligible'])
    stats=detect_lobe_stats(m,body,c);yc=stats['yc']
    root=m['root'];torso=m['torso'];stature=m['stature'];arm=m['arm_y'];leg=m['leg']
    hip_z=root[2]-.055*stature;hip_sz=max(.07,.095*stature);butt_sz=max(.07,c['butt_sz_stature']*stature)
    thigh_z=root[2]-.24*leg;thigh_sz=max(.09,.19*leg);thigh_y=.52*arm;bb=c['butt_back_torso']*torso
    bchg=gchg=pos=neg=0;dxs=[];ap=[];sh=[];maxd=0

    for i in eligible:
        x,y,z=m['pos'][i];nx,ny=x,y
        zn=(z-root[2])/torso;yn=abs(y)/max(arm,1e-9);xn=(x-m['cx'](z))/torso
        uy=abs(yn-yc)/c['hy'];uz=abs(zn-c['zc'])/c['hz'];qr=math.sqrt(uy*uy+uz*uz)
        w=plateau(qr)
        if w>0:
            # Only front torso shell. Anchor is behind the skin, so scaling enlarges the
            # native curvature instead of creating a synthetic point.
            front=v9.smoothstep(-.08,.10,xn)
            if front>0:
                tip=v9.smoothstep(stats['tip_lo'],stats['tip_hi'],xn)
                anchor=m['cx'](z)-.035*torso
                # Tip gets substantially less added projection than the surrounding shell.
                xgain=c['xscale']*(1-.48*tip)
                fill=c['fill']*torso*(1-.72*tip)
                dx=(x-anchor)*xgain*w*front + fill*w*front
                # Small explicit tip trim prevents any isolated foremost row from becoming
                # a spike after enlargement; it is much smaller than the broad shell fill.
                dx-=.008*torso*tip*w*front
                # True circumference growth: scale Y away from each breast's own centre.
                side=1 if y>=0 else -1;cy=side*yc*arm
                dy=(y-cy)*c['yscale']*w*front
                nx+=dx;ny+=dy
                if i in body:
                    bchg+=1;nd=dx/torso;dxs.append(nd)
                    if nd>1e-6:pos+=1
                    elif nd<-1e-6:neg+=1
                    if abs(zn-c['zc'])<=.025 and abs(yn-yc)<=.14:ap.append(nd)
                    elif abs(zn-c['zc'])<=.105 and abs(yn-yc)<=.27:sh.append(nd)
                else:gchg+=1

        # Keep the already accepted lower-body tuning.
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
    if bad:raise RuntimeError(f'{race}: illegal bytes {bad[:8]}')
    od=OUTROOT/'Character'/race/'Female';od.mkdir(parents=True,exist_ok=True);om=od/(c['out']+'.m2');os=od/(c['out']+'00.skin')
    om.write_bytes(data);shutil.copy2(c['skin'],os)
    return {'race':race,'method':'native lobe plateau expansion','body0_vertices':len(body),'native_lobe':stats,
            'body_chest_changed':bchg,'replacement_chest_changed':gchg,'body_positive_dx':pos,'body_negative_dx':neg,
            'body_dx_min':min(dxs) if dxs else 0,'body_dx_max':max(dxs) if dxs else 0,
            'apex_mean_dx':sum(ap)/len(ap) if ap else 0,'shell_mean_dx':sum(sh)/len(sh) if sh else 0,'apex_n':len(ap),'shell_n':len(sh),
            'max_displacement_xy':maxd,'only_vertex_xy_changed':True,'z_unchanged':True,
            'source_sha256':sha(src),'output_sha256':sha(data),'skin_sha256':sha(c['skin'].read_bytes()),
            'shape':{k:c[k] for k in ('zc','hz','hy','xscale','fill','yscale')}}

def main():
    if OUTROOT.exists():shutil.rmtree(OUTROOT)
    r={'version':'v13 native-lobe plateau','races':{}}
    for race,c in CFG.items():r['races'][race]=patch(race,c)
    (ROOT/'analysis').mkdir(exist_ok=True);(ROOT/'analysis/body_patch_v13_native_lobe_report.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))
if __name__=='__main__':main()
