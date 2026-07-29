---
name: complex-steam-trap-investigation
description: Use after the standard v1_3 framework leaves a material evidence-resolution problem, and always use before assigning Open or Closed when a failed regime first appears during or immediately after a shutdown, restart, or connectivity discontinuity unless one-sided degradation is already visible before that transition. Also use for visually compressed transitions or a possible durable sensor reassignment; do not use merely because a lower regime or low confidence is present.
license: Proprietary
compatibility: Requires normalized steam and condensate temperature history ending at the alarm decision time.
metadata:
  owner: meshinsights
  version: "2.0"
allowed-tools: plot_raw_temperature_range compare_temperature_ranges
---
# Complex steam-trap investigation

Use this runbook only after the standard review leaves a material ambiguity.
State the ambiguity internally before selecting evidence. Typical ambiguities are
shutdown versus closed failure, load modulation versus degradation, a durable
sensor reassignment versus open failure, a short right-edge rebound, or a failed
state whose directional onset is hidden in a dense chart.

## Investigation sequence

1. Locate the earliest plausible transition, not merely the alarm timestamp.
   Choose a narrow focus interval around that transition and a comparable
   historical interval from the same operating phase.
2. Call `plot_raw_temperature_range` for the focus interval. The plot contains
   unaggregated readings and deliberately breaks lines across connectivity gaps.
   Zoom further if the onset or lag is still visually compressed.
3. Call `compare_temperature_ranges` when exact direction or proportional change
   remains unclear. Treat its statistics as measurements, not classification
   thresholds.
4. Decide the operating phase before deciding health:
   - A near-simultaneous movement of both sensors into a stable regime with a
     maintained positive relationship supports a process/load transition.
   - A shutdown or cooldown does not become Closed Failure merely because the
     steam side finishes colder or the condensate line retains heat.
   - A partial restart with expanding positive delta is not itself failure.
     However, it does not erase a sustained abnormal regime that preceded it.
   - Repeated restarted on-phases that fail to regain a stable relationship can
     be failure evidence.
5. Distinguish a level change from a relationship change. A new lower level can
   be healthy when the two sensors remain coupled and the delta stabilizes for
   that level. Failure requires affirmative evidence of a sustained relationship
   break, progressive convergence, or one-sided departure.
6. For a possible flip or relocation, require a durable reversal beginning at
   the available-history boundary or after a clear connectivity/instrumentation
   discontinuity. A gradual convergence or reversal during continuous telemetry
   is not a flip.
7. For root cause, anchor on the earliest sustained departure from each sensor's
   own comparable baseline:
   - condensate independently rising toward steam supports Open Failure;
   - steam independently falling toward condensate supports Closed Failure;
   - before/after range medians establish magnitude, not temporal leadership.
     Never infer which side moved first merely because one side's focus median
     changed more from a historical median;
   - a consistent directional trajectory across the standard charts or targeted
     raw evidence can establish Open or Closed even when both sides eventually
     respond; do not require the other side to remain perfectly flat;
   - a slow convergence can still be directional when one sensor progressively
     departs its own comparable baseline while the other remains comparatively
     stable. Later convergence, spikes, or a restart do not erase that earlier
     one-sided evidence;
   - during startup or restart, condensate warming toward steam does not by
     itself prove Open Failure because both sides are re-entering an On-state.
     When no sustained one-sided failure evidence exists before the transition
     and the first abnormal regime forms during restart, use Unknown even if
     condensate reaches its normal On temperature before steam;
   - if an abnormal post-restart regime first appears already converged,
     inverted, or chaotic, if a gap hides the onset, if both sides move together,
     or if the leader cannot be named with an approximate time, use Unknown.

Do not inspect or infer observations after the alarm decision time. Do not force
an Open or Closed label simply because the issue classification is Failure.
