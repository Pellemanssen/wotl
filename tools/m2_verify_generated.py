#!/usr/bin/env python3
import hashlib, json, struct
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PAIRS={
 'Orc':('Orc Female/OrcFemale.m2','Orc Female/OrcFemale00.skin','generated/Character/Orc/Female/OrcFemale.m2','generated/Character/Orc/Female/OrcFemale00.skin'),
 'Draenei':('Draenai Female/DRAENEIFemale.m2','Draenai Female/DRAENEIFemale00.skin','generated/Character/Draenei/Female/DraeneiFemale.m2','generated/Character/Draenei/Female/DraeneiFemale00.skin'),
 'Scourge':('Scourge Female/ScourgeFemale.m2','Scourge Female/ScourgeFemale00.skin','generated/Character/Scourge/Female/ScourgeFemale.m2','generated/Character/Scourge/Female/ScourgeFemale00.skin'),
}

def u32(b,o): return struct.unpack_from('<I',b,o)[0]
def sha(b): return hashlib.sha256(b).hexdigest()

def verify(name,src_m2,src_skin,out_m2,out_skin):
    s=src_m2.read_bytes(); g=out_m2.read_bytes(); ss=src_skin.read_bytes(); gs=out_skin.read_bytes()
    assert s[:4]==g[:4]==b'MD20'
    assert u32(s,4)==u32(g,4)==264
    assert len(s)==len(g), (name,'size')
    n=u32(s,0x3c); vo=u32(s,0x40)
    assert n==u32(g,0x3c) and vo==u32(g,0x40)
    vend=vo+n*48
    assert vend<=len(s)
    # Generated model may change ONLY xyz position floats (first 12 bytes of each 48-byte vertex record).
    bad=[]; changed_pos=0; max_abs_byte_ranges=0
    for off in range(len(s)):
        if s[off]==g[off]: continue
        in_vertex = vo <= off < vend
        if in_vertex:
            rel=(off-vo)%48
            allowed=rel < 12
        else:
            allowed=False
        if not allowed:
            bad.append(off)
            if len(bad)>=20: break
    assert not bad, f'{name}: changed bytes outside vertex positions: {bad}'
    for i in range(n):
        o=vo+i*48
        if s[o:o+12]!=g[o:o+12]: changed_pos+=1
        assert s[o+12:o+48]==g[o+12:o+48]
    assert ss==gs, f'{name}: SKIN differs'
    return {
      'source_m2_sha256':sha(s),'generated_m2_sha256':sha(g),
      'source_skin_sha256':sha(ss),'generated_skin_sha256':sha(gs),
      'm2_size':len(s),'skin_size':len(ss),'vertices':n,'changed_vertex_positions':changed_pos,
      'only_vertex_xyz_changed':True,'skin_bit_identical':True
    }

def main():
    out={}
    for name,(a,b,c,d) in PAIRS.items():
        out[name]=verify(name,ROOT/a,ROOT/b,ROOT/c,ROOT/d)
    (ROOT/'analysis'/'generated_verify.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
    print(json.dumps(out,indent=2))
if __name__=='__main__': main()
