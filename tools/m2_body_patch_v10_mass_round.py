#!/usr/bin/env python3
import json, math, shutil, hashlib
from pathlib import Path
import m2_body_patch_v9_ale_transfer as v9

ROOT=Path(__file__).resolve().parents[1]
REF_M2=ROOT/'bloodelf'/'female'/'bloodelffemale.m2'
REF_SKIN=ROOT/'bloodelf'/'female'/'bloodelffemale00.skin'

# v10: keep the real Blood Elf ALE chest as the reference, but change HOW it is
# transferred. v9 moved too few front-most vertices and visually produced a cone.
# v10 broadens/flattens the ALE augmentation profile (mass instead of tip), moves a
# thicker front surface band, adds a small safe Y fullness, and never changes Z.
TARGETS={
 'Orc':{
   'm2':ROOT/'Orc Female'/'OrcFemale.m2','skin':ROOT/'Orc Female'/'OrcFemale00.skin','out':'OrcFemale',
   'chest_low':0.605,'chest_high':0.972,'mass_gamma':0.48,'mass_scale':1.00,'y_sample_scale':0.84,
   'vertical_spread':0.050,'max_forward_delta':0.225,'max_pullback':0.030,'side_gain_torso':0.034,
   'hip_widen':0.170,'butt_back_torso':0.148,'butt_sz_stature':0.100,'butt_power':0.48,'thigh_full':0.112},
 'Draenei':{
   'm2':ROOT/'Draenai Female'/'DRAENEIFemale.m2','skin':ROOT/'Draenai Female'/'DRAENEIFemale00.skin','out':'DraeneiFemale',
   # Lower than the old hard lock, but reference-mass threshold below prevents belly movement.
   # This allows the actual under-breast to fill instead of chopping it off into a point.
   'chest_low':0.625,'chest_high':0.972,'mass_gamma':0.52,'mass_scale':0.98,'y_sample_scale':0.86,
   'vertical_spread':0.045,'max_forward_delta':0.160,'max_pullback':0.025,'side_gain_torso':0.032,
   'hip_widen':0.190,'butt_back_torso':0.110,'butt_sz_stature':0.092,'butt_power':0.47,'thigh_full':0.103},
 'Scourge':{
   'm2':ROOT/'Scourge Female'/'ScourgeFemale.m2','skin':ROOT/'Scourge Female'/'ScourgeFemale00.skin','out':'ScourgeFemale',
   'chest_low':0.595,'chest_high':0.962,'mass_gamma':0.47,'mass_scale':0.98,'y_sample_scale':0.84,
   'vertical_spread':0.052,'max_forward_delta':0.220,'max_pullback':0.030,'side_gain_torso':0.032,
   'hip_widen':0.148,'butt_back_torso':0.152,'butt_sz_stature':0.096,'butt_power':0.47,'thigh_full':0.095},
}

def sha(b): return hashlib.sha256(b).hexdigest()

def target_mass(ref_profile, peak, yn, zn, cfg):
    # Compress normalized Y toward the centre: the Blood Elf ALE lobe is sampled over
    # a wider target width instead of concentrating mass at the middle/front.
    yq=max(v9.Y0,min(v9.Y1,yn*cfg['y_sample_scale']))
    spread=cfg['vertical_spread']
    # Morphological vertical widening of the real ALE profile. A nearby high ALE value
    # contributes almost as much, filling upper/lower breast instead of sharpening tip.
    a=0.0
    for dz,decay in ((0.0,1.00),(-spread,0.93),(spread,0.93),(-spread*.5,0.97),(spread*.5,0.97)):
        a=max(a,v9.sample_grid(ref_profile['aug'],yq,zn+dz)*decay)
    if a <= peak*0.035:
        return 0.0
    r=max(0.0,min(1.0,a/peak))
    # gamma < 1 raises low/mid augmentation much more than the peak. This is the
    # anti-cone operation: same ALE peak family, far more surrounding mass.
    mass=peak*(r**cfg['mass_gamma'])*cfg['mass_scale']
    # Gentle fades at the chest limits. The mass threshold above keeps the belly fixed.
    lo=v9.smoothstep(cfg['chest_low'],cfg['chest_low']+0.050,zn)
    hi=v9.smoothstep(cfg['chest_high'],cfg['chest_high']-0.045,zn)
    return mass*lo*hi

def patch_race(race,cfg,ref_profile,ref_peak):
    m=v9.load_model(cfg['m2'],cfg['skin'])
    src=m['bytes']; data=bytearray(src); before=v9.build_profile(m)
    root=m['root']; torso=m['torso']; stature=m['stature']; arm_y=m['arm_y']; leg=m['leg']
    hip_z=root[2]-.055*stature
    hip_sz=max(.07,.095*stature)
    butt_sz=max(.07,cfg['butt_sz_stature']*stature)
    thigh_z=root[2]-.24*leg; thigh_sz=max(.09,.19*leg); thigh_y=.52*arm_y
    bb=cfg['butt_back_torso']*torso

    changed=0; breast_changed=0; breast_below_low=0
    maxd=0.0; max_breast_dx=0.0; max_breast_dy=0.0
    breast_zn_min=None; breast_zn_max=None

    for i in m['eligible']:
        x,y,z=m['pos'][i]
        zn=(z-root[2])/torso; yn=abs(y)/max(1e-6,arm_y); xn=(x-m['cx'](z))/torso
        nx,ny=x,y

        # MASS-ROUND ALE chest transfer. Breast edits are X/Y only; Z never changes.
        if cfg['chest_low'] < zn < cfg['chest_high'] and yn <= 1.08:
            target=target_mass(ref_profile,ref_peak,yn,zn,cfg)
            if target > ref_peak*0.055:
                cur_aug=v9.sample_grid(before['aug'],min(v9.Y1,yn),zn)
                cur_surface=v9.sample_grid(before['front'],min(v9.Y1,yn),zn)
                # Move toward the broadened ALE target augmentation. Permit small pullback
                # at an over-projected tip, but give much more room to fill surrounding mass.
                delta_n=target-cur_aug
                delta_n=max(-cfg['max_pullback'],min(cfg['max_forward_delta'],delta_n))

                # v9 used a thin front shell. v10 deliberately uses a thicker surface band
                # so neighbouring chest vertices move with the tip instead of forming a cone.
                frontness=v9.smoothstep(cur_surface-0.185,cur_surface-0.035,xn)
                # Never touch deep torso/back vertices.
                if xn < cur_surface-0.205:
                    frontness=0.0

                # Wider lateral fade than v9. Actual Y expansion is still modest and only
                # applied to vertices already participating in the ALE chest lobe.
                side_fade=v9.smoothstep(1.08,0.94,yn)
                w=frontness*side_fade
                dx=delta_n*torso*w

                # Side fullness peaks off-centre and fades toward sternum/outer edge.
                side_lobe=math.exp(-0.5*((yn-0.53)/0.31)**2)
                mass_strength=max(0.0,min(1.0,target/ref_peak))
                dy=(1.0 if y>=0 else -1.0)*cfg['side_gain_torso']*torso*side_lobe*mass_strength*w

                if abs(dx)>1e-7 or abs(dy)>1e-7:
                    nx += dx; ny += dy
                    breast_changed += 1
                    max_breast_dx=max(max_breast_dx,abs(dx)); max_breast_dy=max(max_breast_dy,abs(dy))
                    breast_zn_min=zn if breast_zn_min is None else min(breast_zn_min,zn)
                    breast_zn_max=zn if breast_zn_max is None else max(breast_zn_max,zn)
                    if zn <= cfg['chest_low']: breast_below_low += 1

        # Stable lower body; only Draenei thighs are slightly reduced from v9.
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
        tx=root[0]
        nx=tx+(nx-tx)*(1+cfg['thigh_full']*wt)
        ny=ty+(ny-ty)*(1+cfg['thigh_full']*wt)

        d=math.hypot(nx-x,ny-y)
        if d>1e-7:
            v9.put3(data,m['vo']+i*48,(nx,ny,z)); changed+=1; maxd=max(maxd,d)

    # QA: no headers, bones, normals, UVs, weights or Z coordinates may change.
    allowed=bytearray(len(src))
    for i in range(m['n']):
        allowed[m['vo']+i*48:m['vo']+i*48+8]=b'\x01'*8
    illegal=[k for k,(a,b) in enumerate(zip(src,data)) if a!=b and not allowed[k]]
    if illegal: raise RuntimeError(f'{race}: illegal byte changes outside vertex X/Y: {illegal[:10]}')
    if breast_below_low: raise RuntimeError(f'{race}: chest edit leaked below chest_low')
    if breast_changed < 60: raise RuntimeError(f'{race}: too few breast vertices changed: {breast_changed}')

    outdir=ROOT/'generated_v10_mass_round'/'Character'/race/'Female'; outdir.mkdir(parents=True,exist_ok=True)
    outm=outdir/(cfg['out']+'.m2'); outs=outdir/(cfg['out']+'00.skin')
    outm.write_bytes(data); shutil.copy2(cfg['skin'],outs)
    return {
      'race':race,'method':'BloodElf ALE mass-round profile transfer',
      'changed_vertices':changed,'breast_changed_vertices':breast_changed,
      'breast_below_chest_low':breast_below_low,'breast_zn_min':breast_zn_min,'breast_zn_max':breast_zn_max,
      'max_breast_dx':max_breast_dx,'max_breast_dy':max_breast_dy,'max_displacement_xy':maxd,
      'only_vertex_xy_changed':True,'z_unchanged':True,
      'source_sha256':sha(src),'output_sha256':sha(data),'skin_sha256':sha(cfg['skin'].read_bytes()),
      'chest':{k:cfg[k] for k in ('chest_low','chest_high','mass_gamma','mass_scale','y_sample_scale','vertical_spread','max_forward_delta','max_pullback','side_gain_torso')},
      'lower_body':{k:cfg[k] for k in ('hip_widen','butt_back_torso','butt_sz_stature','butt_power','thigh_full')}
    }

def main():
    ref_model=v9.load_model(REF_M2,REF_SKIN)
    ref_profile=v9.build_profile(ref_model)
    ref_peak=max(max(row) for row in ref_profile['aug'])
    report={'reference':{'model':str(REF_M2.relative_to(ROOT)),'peak_aug':ref_peak,'source':'A Little Extra Blood Elf'},'races':{}}
    for race,cfg in TARGETS.items():
        report['races'][race]=patch_race(race,cfg,ref_profile,ref_peak)
    (ROOT/'analysis').mkdir(exist_ok=True)
    (ROOT/'analysis'/'body_patch_v10_mass_round_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__': main()
