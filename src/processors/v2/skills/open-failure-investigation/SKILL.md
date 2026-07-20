---
name: open-failure-investigation
description: Investigate whether condensate rose toward steam and created a sustained open-failure regime.
---

# Open-failure investigation

Use this skill when the leading explanation is that the outlet/condensate side
heated toward the inlet/steam side.

1. Inspect the suspected onset and the stabilized regime, not only the alarm edge.
2. Compare condensate with its own earlier On-state baseline.
3. Determine whether condensate moved toward steam independently or both sensors
   simply changed operating level together.
4. Treat a persistent condensate rise and delta collapse as open-failure evidence.
5. If the direction was already fully formed or remains ambiguous, do not force
   an open diagnosis; use Unknown when the trap is clearly abnormal.

Use the chart returned by `inspect_open_failure_onset` as primary evidence. Its
measurements provide orientation only.
