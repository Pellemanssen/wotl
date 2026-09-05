#!/usr/bin/env python3
import json, math, shutil, hashlib
from pathlib import Path
import m2_body_patch_v9_ale_transfer as v9

ROOT = Path(__file__).resolve().parents[1]
REF_M2 = ROOT/'bloodelf'/'female'/'bloodelffemale.m2'
REF_SKIN = ROOT/'bloodelf'/'female'/'bloodelffemale00.skin'

# v11: build a broad rounded breast envelope from the REAL A Little Extra Blood Elf
# profile, instead of copying the reference projection cell-for-cell. The previous
# versions concentrated too much depth in the centre and visually made a cone.
#
# Chest edits remain X/Y only. Z is never modified. Draenei keeps a hard belly lock.
TARGETS = {
    'Orc': {
        'm2': ROOT/'Orc Female'/'OrcFemale.m2', 'skin': ROOT/'Orc Female'/'OrcFemale00.skin', 'out': 'OrcFemale',
        'chest_low': 0.625, 'chest_high': 0.975,
        'height_scale': 1.34, 'width_scale': 1.22, 'mass_scale': 1.06, 'round_gamma': 0.46,
        'max_forward_delta': 0.245, 'max_pullback': 0.085, 'side_gain_torso': 0.050,
        'hip_widen': 0.170, 'butt_back_torso': 0.150, 'butt_sz_stature': 0.100, 'butt_power': 0.48, 'thigh_full': 0.112,
    },
    'Draenei': {
        'm2': ROOT/'Draenai Female'/'DRAENEIFemale.m2', 'skin': ROOT/'Draenai Female'/'DRAENEIFemale00.skin', 'out': 'DraeneiFemale',
        'chest_low': 0.690, 'chest_high': 0.975,
        'height_scale': 1.30, 'width_scale': 1.20, 'mass_scale': 1.03, 'round_gamma': 0.48,
        'max_forward_delta': 0.205, 'max_pullback': 0.080, 'side_gain_torso': 0.048,
        'hip_widen': 0.188, 'butt_back_torso': 0.110, 'butt_sz_stature': 0.092, 'butt_power': 0.47, 'thigh_full': 0.100,
    },
    'Scourge': {
        'm2': ROOT/'Scourge Female'/'ScourgeFemale.m2', 'skin': ROOT/'Scourge Female'/'ScourgeFemale00.skin', 'out': 'ScourgeFemale',
        'chest_low': 0.615, 'chest_high': 0.965,
        'height_scale': 1.36, 'width_scale': 1.23, 'mass_scale': 1.05, 'round_gamma': 0.45,
        'max_forward_delta': 0.240, 'max_pullback': 0.090, 'side_gain_torso': 0.048,
        'hip_widen': 0.148, 'butt_back_torso': 0.154, 'butt_sz_stature': 0.096, 'butt_power': 0.47, 'thigh_full': 0.095,
    },
}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def fit_ale_round_reference(profile):
    peak = max(max(row) for row in profile['aug'])
    # Fit the location and footprint from meaningful ALE augmentation cells.
    pts = []
    for j in range(v9.NY):
        y = v9.y_center(j)
        for k in range(v9.NZ):
            z = v9.z_center(k)
            a = profile['aug'][j][k]
            if a >= peak * 0.12:
                # sqrt weighting gives the broad lobe more influence than only the tip.
                w = math.sqrt(max(a, 0.0) / max(peak, 1e-9))
                pts.append((y, z, a, w))
    if not pts:
        raise RuntimeError('Blood Elf ALE reference has no usable breast profile')

    sw = sum(p[3] for p in pts)
    yc = sum(y*w for y,z,a,w in pts) / sw
    zc = sum(z*w for y,z,a,w in pts) / sw

    # Use the actual ALE 12%-footprint, but keep sane minimums. These dimensions are
    # normalized to arm span (Y) and torso length (Z), then scaled per target race.
    hy = max(abs(y-yc) for y,z,a,w in pts)
    hz = max(abs(z-zc) for y,z,a,w in pts)
    hy = max(0.34, min(0.58, hy))
    hz = max(0.125, min(0.205, hz))

    # Keep the fitted centre inside the characteristic female chest band. This only
    # prevents sparse reference bins from shifting the fitted cap toward neck/belly.
    yc = max(0.30, min(0.60, yc))
    zc = max(0.775, min(0.865, zc))
    return {'peak': peak, 'yc': yc, 'zc': zc, 'hy': hy, 'hz': hz}


def rounded_target(fit, yn, zn, cfg):
    hy = fit['hy'] * cfg['width_scale']
    hz = fit['hz'] * cfg['height_scale']
    u = abs(yn - fit['yc']) / max(hy, 1e-6)
    v = abs(zn - fit['zc']) / max(hz, 1e-6)
    r2 = u*u + v*v
    if r2 >= 1.0:
        return 0.0, 0.0

    # Circular/elliptical cap, then gamma<1 deliberately fattens the shoulders and
    # under-breast relative to the centre. This is the anti-point operation.
    arc = math.sqrt(max(0.0, 1.0-r2))
    broad = arc ** cfg['round_gamma']

    # Gentle edge fades near race-specific chest limits; Draenei's hard low limit is
    # intentionally high enough that belly vertices can never participate.
    lo = v9.smoothstep(cfg['chest_low'], cfg['chest_low']+0.035, zn)
    hi = v9.smoothstep(cfg['chest_high'], cfg['chest_high']-0.035, zn)
    target = fit['peak'] * cfg['mass_scale'] * broad * lo * hi
    return target, broad


def patch_race(race, cfg, ref_profile, fit):
    m = v9.load_model(cfg['m2'], cfg['skin'])
    src = m['bytes']
    data = bytearray(src)
    before = v9.build_profile(m)

    root = m['root']; torso = m['torso']; stature = m['stature']; arm_y = m['arm_y']; leg = m['leg']
    hip_z = root[2] - .055*stature
    hip_sz = max(.07, .095*stature)
    butt_sz = max(.07, cfg['butt_sz_stature']*stature)
    thigh_z = root[2] - .24*leg
    thigh_sz = max(.09, .19*leg)
    thigh_y = .52*arm_y
    bb = cfg['butt_back_torso']*torso

    changed = 0
    breast_changed = 0
    breast_below_low = 0
    breast_forward = 0
    breast_pullback = 0
    shoulder_fill = 0
    maxd = 0.0
    max_breast_dx = 0.0
    max_breast_dy = 0.0
    breast_zn_min = None
    breast_zn_max = None

    for i in m['eligible']:
        x,y,z = m['pos'][i]
        zn = (z-root[2])/torso
        yn = abs(y)/max(1e-6, arm_y)
        xn = (x-m['cx'](z))/torso
        nx,ny = x,y

        if cfg['chest_low'] < zn < cfg['chest_high'] and yn <= 1.04:
            target, broad = rounded_target(fit, yn, zn, cfg)
            if target > fit['peak']*0.035:
                cur_aug = v9.sample_grid(before['aug'], min(v9.Y1,yn), zn)
                cur_surface = v9.sample_grid(before['front'], min(v9.Y1,yn), zn)

                # Set the entire front shell toward a broad rounded envelope. The centre is
                # allowed to come slightly BACK if native/reference projection is too pointy;
                # the surrounding upper/lower/side shell is filled much more aggressively.
                delta_n = target - cur_aug
                delta_n = max(-cfg['max_pullback'], min(cfg['max_forward_delta'], delta_n))

                # Thick shell: chest surface moves as a mass, not only the foremost tip.
                frontness = v9.smoothstep(cur_surface-0.205, cur_surface-0.030, xn)
                if xn < cur_surface-0.225:
                    frontness = 0.0

                # Avoid sternum/outer-arm contamination while retaining a wide breast base.
                inner = v9.smoothstep(0.06, 0.20, yn)
                outer = v9.smoothstep(1.04, 0.90, yn)
                w = frontness * inner * outer
                dx = delta_n * torso * w

                # Circumference/side fullness. Peak is around the breast's lateral centre,
                # but it follows the same broad cap and never touches Z.
                side_lobe = math.exp(-0.5*((yn-fit['yc'])/max(0.24, fit['hy']*0.85))**2)
                dy = (1.0 if y >= 0 else -1.0) * cfg['side_gain_torso'] * torso * side_lobe * broad * w

                if abs(dx) > 1e-7 or abs(dy) > 1e-7:
                    nx += dx; ny += dy
                    breast_changed += 1
                    if dx > 1e-7: breast_forward += 1
                    elif dx < -1e-7: breast_pullback += 1
                    # Count filling away from the centre: these are the vertices previous
                    # pointy builds did not move enough.
                    vdist = abs(zn-fit['zc'])/max(1e-6, fit['hz']*cfg['height_scale'])
                    if vdist >= 0.38 and dx > 0: shoulder_fill += 1
                    max_breast_dx = max(max_breast_dx, abs(dx))
                    max_breast_dy = max(max_breast_dy, abs(dy))
                    breast_zn_min = zn if breast_zn_min is None else min(breast_zn_min, zn)
                    breast_zn_max = zn if breast_zn_max is None else max(breast_zn_max, zn)
                    if zn <= cfg['chest_low']:
                        breast_below_low += 1

        # Stable lower body from v10. Draenei thigh fullness remains slightly reduced.
        wh = v9.gauss(z,hip_z,hip_sz) * max(0.0,1.0-(abs(ny)/(.27*stature+1e-6))**4)
        ny *= 1 + cfg['hip_widen']*wh

        tt = max(0.0,min(1.0,(z-root[2])/max(1e-6,torso)))
        cx = root[0] + tt*(m['sh'][0]-root[0])
        rear = v9.smoothstep(cx+.025*stature,cx-.035*stature,x)
        guard = v9.smoothstep(cx-.22*stature,cx-.10*stature,x)
        rawb = v9.gauss(z,hip_z,butt_sz)*rear*guard*v9.gauss(abs(ny),.50*arm_y,max(.045,.54*arm_y))
        wbut = (rawb**cfg['butt_power']) if rawb>0 else 0.0
        nx -= bb*wbut

        side = 1 if ny>=0 else -1
        ty = side*thigh_y
        wt = v9.gauss(z,thigh_z,thigh_sz)*max(0.0,1.0-(abs(ny)/(.30*stature+1e-6))**6)
        tx = root[0]
        nx = tx+(nx-tx)*(1+cfg['thigh_full']*wt)
        ny = ty+(ny-ty)*(1+cfg['thigh_full']*wt)

        d = math.hypot(nx-x, ny-y)
        if d > 1e-7:
            v9.put3(data,m['vo']+i*48,(nx,ny,z))
            changed += 1
            maxd = max(maxd,d)

    # Hard QA: only vertex X/Y bytes may differ. Z, weights, bones, normals, UVs,
    # animations and every non-vertex byte remain byte-identical.
    allowed = bytearray(len(src))
    for i in range(m['n']):
        allowed[m['vo']+i*48:m['vo']+i*48+8] = b'\x01'*8
    illegal = [k for k,(a,b) in enumerate(zip(src,data)) if a!=b and not allowed[k]]
    if illegal:
        raise RuntimeError(f'{race}: illegal byte changes outside vertex X/Y: {illegal[:10]}')
    if breast_below_low:
        raise RuntimeError(f'{race}: chest edit leaked below hard chest_low')
    if breast_changed < 80:
        raise RuntimeError(f'{race}: too few breast vertices changed: {breast_changed}')
    if shoulder_fill < 20:
        raise RuntimeError(f'{race}: insufficient upper/lower breast mass fill: {shoulder_fill}')

    outdir = ROOT/'generated_v11_round_mass'/'Character'/race/'Female'
    outdir.mkdir(parents=True,exist_ok=True)
    outm = outdir/(cfg['out']+'.m2')
    outs = outdir/(cfg['out']+'00.skin')
    outm.write_bytes(data)
    shutil.copy2(cfg['skin'],outs)

    # Rebuild the output profile for diagnostics only.
    after_model = v9.load_model(outm, outs)
    after = v9.build_profile(after_model)
    yc = fit['yc']; zc = fit['zc']; dz = min(0.10, fit['hz']*cfg['height_scale']*0.52)
    center = v9.sample_grid(after['aug'], yc, zc)
    upper = v9.sample_grid(after['aug'], yc, zc+dz)
    lower = v9.sample_grid(after['aug'], yc, zc-dz)
    broadness_ratio = ((upper+lower)/2)/max(center,1e-9)

    return {
        'race': race,
        'method': 'ALE-fitted broad rounded envelope',
        'changed_vertices': changed,
        'breast_changed_vertices': breast_changed,
        'breast_forward_vertices': breast_forward,
        'breast_pullback_vertices': breast_pullback,
        'shoulder_underbreast_fill_vertices': shoulder_fill,
        'breast_below_chest_low': breast_below_low,
        'breast_zn_min': breast_zn_min,
        'breast_zn_max': breast_zn_max,
        'max_breast_dx': max_breast_dx,
        'max_breast_dy': max_breast_dy,
        'max_displacement_xy': maxd,
        'output_profile_center': center,
        'output_profile_upper': upper,
        'output_profile_lower': lower,
        'output_broadness_ratio': broadness_ratio,
        'only_vertex_xy_changed': True,
        'z_unchanged': True,
        'source_sha256': sha(src),
        'output_sha256': sha(data),
        'skin_sha256': sha(cfg['skin'].read_bytes()),
        'chest': {k:cfg[k] for k in ('chest_low','chest_high','height_scale','width_scale','mass_scale','round_gamma','max_forward_delta','max_pullback','side_gain_torso')},
        'lower_body': {k:cfg[k] for k in ('hip_widen','butt_back_torso','butt_sz_stature','butt_power','thigh_full')},
    }


def main():
    ref_model = v9.load_model(REF_M2,REF_SKIN)
    ref_profile = v9.build_profile(ref_model)
    fit = fit_ale_round_reference(ref_profile)
    report = {
        'reference': {
            'model': str(REF_M2.relative_to(ROOT)),
            'source': 'A Little Extra Blood Elf',
            'fit': fit,
        },
        'races': {},
    }
    for race,cfg in TARGETS.items():
        report['races'][race] = patch_race(race,cfg,ref_profile,fit)

    (ROOT/'analysis').mkdir(exist_ok=True)
    (ROOT/'analysis'/'body_patch_v11_round_mass_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__ == '__main__':
    main()
