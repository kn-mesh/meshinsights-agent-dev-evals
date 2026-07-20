---
name: modulation-vs-failure
description: Determine whether a changed operating level is stable healthy modulation or a persistent degraded regime.
---

# Modulation versus failure

Use this skill when both sensors changed together or a lower-temperature regime
could be either control modulation or failure.

1. Inspect the transition and enough of the new regime to judge stabilization.
2. Healthy modulation changes operating level, remains thermally coupled, and
   settles around a roughly horizontal average with a proportionate positive delta.
3. A stable plateau is not automatically healthy: compare its delta and condensate
   level with comparable historical On states.
4. Continued downward movement, repeated inversion, or a persistently material
   deterioration from comparable On-state delta supports Failure.
5. A brief rebound does not establish recovery.

Use `inspect_modulation_regime` to generate the focused chart and context.
