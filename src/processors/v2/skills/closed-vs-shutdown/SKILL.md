---
name: closed-vs-shutdown
description: Distinguish steam-side degradation from a healthy shutdown by comparing transitions and stabilization.
---

# Closed failure versus shutdown

Use this skill when steam falls toward condensate and shutdown remains a plausible
alternative.

1. Identify the candidate transition and a prior representative healthy shutdown.
2. Compare which sensor moved first, response lag, slope, convergence, and the
   temperature where each transition stabilized.
3. A rapid near-simultaneous fall toward the normal Off state supports shutdown.
4. Steam leading condensate by hours, persistent narrowing delta, or stabilization
   above the usual Off state supports closed failure.
5. Do not let the final resting temperature erase the lead-up trajectory.

Use `compare_closed_candidate_with_shutdown` when the case brief identifies a
prior shutdown. Otherwise use `inspect_closed_failure_transition` to examine the
candidate transition without inventing a historical reference.
