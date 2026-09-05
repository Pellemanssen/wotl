#!/usr/bin/env python3
import json, struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
models=[
('Human','Human/Female/HumanFemale.m2'),
('Orc','Orc Female/OrcFemale.m2'),
('Draenei','Draenai Female/DRAENEIFemale.m2'),
('Scourge','Scourge Female/ScourgeFemale.m2'),
('BloodElf','bloodelf/BloodElfFemale.m2'),
('NightElf','nightelf/NightElfFemale.m2'),
('Troll','troll/TrollFemale.m2'),
]
roles={0:'ArmL',1:'ArmR',2:'ShoulderL',3:'ShoulderR',4:'SpineLow',5:'Waist',6:'Head',7:'Jaw',26:'Root'}
def u32(b,o): return struct.unpack_from('<I',b,o)[0]
def i16(b,o): return struct.unpack_from('<h',b,o)[0]
def i32(b,o): return struct.unpack_from('<i',b,o)[0]
def f3(b,o): return struct.unpack_from('<3f',b,o)
def parse(path):
 b=path.read_bytes(); version=u32(b,4)
 nb,ob=u32(b,0x2c),u32(b,0x30); nk,ok=u32(b,0x34),u32(b,0x38)
 stride=88 if version>=264 else None
 if stride is None: raise ValueError(version)
 bones=[]
 for i in range(nb):
  o=ob+i*stride
  bones.append({'index':i,'key_id':i32(b,o),'parent':i16(b,o+8),'pivot':f3(b,o+76)})
 lookup=[i16(b,ok+i*2) for i in range(nk)]
 key={}
 for slot,name in roles.items():
  if slot<len(lookup) and 0<=lookup[slot]<len(bones): key[name]=bones[lookup[slot]]
 return {'version':version,'bone_count':nb,'key_lookup_count':nk,'key':key}
out={}
for name,rel in models:
 p=ROOT/rel
 if p.exists():
  try: out[name]=parse(p)
  except Exception as e: out[name]={'error':repr(e)}
(ROOT/'analysis').mkdir(exist_ok=True)
(ROOT/'analysis'/'m2_bones.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps(out,indent=2))
