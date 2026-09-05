#!/usr/bin/env python3
from pathlib import Path
import m2_body_patch_v15_mass_surface as base

ROOT=Path(__file__).resolve().parents[1]
base.OUTROOT=ROOT/'generated_v15b_mass_surface'

# Orc needs real apex pullback; keep the new broad shell, lower only the target
# peak so surrounding mass grows while the old cone tip is gently brought back.
base.CFG['Orc'].update(target_peak=.495, blend=.88, pull=.60, hz=.190, hy=.400, yscale=.155)

if __name__=='__main__':
    base.main()
