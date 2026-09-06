#!/usr/bin/env python3
import struct
from pathlib import Path
files=[
 Path('Orc Female/OrcFemale.m2'),
 Path('Draenai Female/DRAENEIFemale.m2'),
 Path('Scourge Female/ScourgeFemale.m2'),
]
for p in files:
    b=p.read_bytes()
    print(p, 'magic', b[:4], 'version', struct.unpack_from('<I',b,4)[0], 'nSkinProfiles@68', struct.unpack_from('<I',b,68)[0])
