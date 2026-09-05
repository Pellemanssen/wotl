#!/usr/bin/env python3
import json, struct, hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCALE = 2.0
MODELS = {
    'Orc': (
        ROOT/'Orc Female'/'OrcFemale.m2',
        ROOT/'generated'/'Character'/'Orc'/'Female'/'OrcFemale.m2',
    ),
    'Draenei': (
        ROOT/'Draenai Female'/'DRAENEIFemale.m2',
        ROOT/'generated'/'Character'/'Draenei'/'Female'/'DraeneiFemale.m2',
    ),
    'Scourge': (
        ROOT/'Scourge Female'/'ScourgeFemale.m2',
        ROOT/'generated'/'Character'/'Scourge'/'Female'/'ScourgeFemale.m2',
    ),
}

def sha(b): return hashlib.sha256(b).hexdigest()
def u32(b,o): return struct.unpack_from('<I', b, o)[0]

def main():
    report = {}
    outroot = ROOT/'generated_v2'/'Character'
    for race,(srcp,v1p) in MODELS.items():
        src = srcp.read_bytes(); v1 = v1p.read_bytes()
        if src[:4] != b'MD20' or v1[:4] != b'MD20':
            raise RuntimeError(f'{race}: invalid M2 magic')
        if len(src) != len(v1):
            raise RuntimeError(f'{race}: source/v1 size mismatch')
        nv, vo = u32(src,0x3c), u32(src,0x40)
        if (nv,vo) != (u32(v1,0x3c),u32(v1,0x40)):
            raise RuntimeError(f'{race}: vertex layout mismatch')
        out = bytearray(src)
        changed = 0; maxd1 = 0.0; maxd2 = 0.0
        for i in range(nv):
            o = vo + i*48
            s = struct.unpack_from('<3f', src, o)
            a = struct.unpack_from('<3f', v1, o)
            d = tuple(a[j]-s[j] for j in range(3))
            d1 = sum(x*x for x in d) ** 0.5
            if d1 > 1e-8:
                changed += 1
                n = tuple(s[j] + SCALE*d[j] for j in range(3))
                struct.pack_into('<3f', out, o, *n)
                maxd1 = max(maxd1,d1); maxd2 = max(maxd2,d1*SCALE)
        # Strictly assert that only vertex XYZ bytes differ from source.
        allowed = bytearray(len(src))
        for i in range(nv):
            o = vo + i*48
            allowed[o:o+12] = b'\x01'*12
        illegal = [i for i,(a,b) in enumerate(zip(src,out)) if a!=b and not allowed[i]]
        if illegal:
            raise RuntimeError(f'{race}: illegal non-XYZ modifications at {illegal[:10]}')
        race_dir = outroot/race/'Female'
        race_dir.mkdir(parents=True,exist_ok=True)
        name = f'{race}Female.m2' if race != 'Scourge' else 'ScourgeFemale.m2'
        outp = race_dir/name
        outp.write_bytes(out)
        # Preserve the already-validated 00.skin bit-for-bit.
        skin_src = ROOT/'generated'/'Character'/race/'Female'/f'{race}Female00.skin'
        skin_dst = race_dir/f'{race}Female00.skin'
        skin_dst.write_bytes(skin_src.read_bytes())
        report[race] = {
            'source': str(srcp.relative_to(ROOT)),
            'v1': str(v1p.relative_to(ROOT)),
            'v2': str(outp.relative_to(ROOT)),
            'scale_vs_v1_delta': SCALE,
            'vertex_count': nv,
            'changed_vertex_positions': changed,
            'max_displacement_v1': maxd1,
            'max_displacement_v2': maxd2,
            'source_sha256': sha(src),
            'v1_sha256': sha(v1),
            'v2_sha256': sha(out),
            'only_vertex_xyz_changed': True,
            'skin_sha256': sha(skin_src.read_bytes()),
        }
    ad = ROOT/'analysis'; ad.mkdir(exist_ok=True)
    (ad/'body_patch_v2_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__ == '__main__': main()
