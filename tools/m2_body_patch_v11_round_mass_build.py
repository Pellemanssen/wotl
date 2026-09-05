#!/usr/bin/env python3
import m2_body_patch_v11_round_mass as v11

# Final v11 tuning after QA: widen the actual participating breast footprint rather
# than increasing the centre tip. Scourge needed a slightly larger fitted envelope;
# Orc/Draenei get only small mass/width increases. Draenei hard belly lock stays 0.690.
v11.TARGETS['Orc']['width_scale'] = 1.28
v11.TARGETS['Orc']['height_scale'] = 1.38
v11.TARGETS['Orc']['mass_scale'] = 1.08
v11.TARGETS['Orc']['round_gamma'] = 0.42
v11.TARGETS['Orc']['side_gain_torso'] = 0.054

v11.TARGETS['Draenei']['width_scale'] = 1.24
v11.TARGETS['Draenei']['height_scale'] = 1.34
v11.TARGETS['Draenei']['mass_scale'] = 1.05
v11.TARGETS['Draenei']['round_gamma'] = 0.44
v11.TARGETS['Draenei']['side_gain_torso'] = 0.052

v11.TARGETS['Scourge']['width_scale'] = 1.34
v11.TARGETS['Scourge']['height_scale'] = 1.44
v11.TARGETS['Scourge']['mass_scale'] = 1.09
v11.TARGETS['Scourge']['round_gamma'] = 0.40
v11.TARGETS['Scourge']['side_gain_torso'] = 0.054

if __name__ == '__main__':
    v11.main()
