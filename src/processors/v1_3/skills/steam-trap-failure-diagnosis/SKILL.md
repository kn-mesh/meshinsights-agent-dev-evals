---
name: steam-trap-failure-diagnosis
description: Diagnose a Pulse FDE alarm from historical inlet and outlet temperature evidence; use when deciding Healthy versus Failure and Open, Closed, or Unknown root cause.
compatibility: Requires the Pulse v1_3 evidence contract and temperature charts ending at the alarm decision point.
metadata:
  domain: connected-steam-systems
  pipeline: pulse-v1-3
---

# Steam-trap failure diagnosis

Use this runbook after reviewing the 365-day view, then the 30-day and 7-day views. Treat the FDE alarm as an unconfirmed screening signal with a historically high false-positive rate. Do not use evidence after the alarm except the single continuity point already present in a supplied chart.

## Establish the installation baseline

1. Identify this unit's normal elevated On-state, ambient Off-state, shutdown, startup, modulation, and recurring patterns.
2. Compare temperature relationships and delta within comparable operating states. Absolute temperatures differ substantially by installation.
3. Consider sensor labels flipped only when a durable historical reversal exists from the beginning of the evidence or after a clear instrumentation discontinuity. A relationship that gradually reverses is failure evidence, not a label flip.

The sensors are inexpensive exterior pipe-surface proxies transmitted about every 30 minutes. Pipe thickness, insulation, placement, load, and process conditions vary by installation. Shared condensate discharge lines can also influence outlet temperature, so judge trends and relationships rather than isolated absolute readings.

## Decide health before root cause

- Healthy On-state: inlet/steam remains warmer than outlet/condensate with a stable delta for that operating level.
- Healthy Off-state: both temperatures converge near ambient.
- Healthy shutdown: both sides begin dropping together and settle smoothly. A minor thermal lag is normal.
- Healthy startup or modulation: both sides move with the process and establish a stable positive delta. A lower operating level naturally has a smaller delta.
- Failure: a sustained, unexplained delta collapse or inversion relative to a comparable historical state. A new downward trajectory that stabilizes in a materially lower, low-delta regime remains failure evidence even when both sensors move together.
- A brief recovery, final shutdown, or a few healthier points must not erase a preceding sustained failed regime. Recovery must stabilize before it supports Healthy.
- When the evidence is genuinely ambiguous, prefer Failure with Low confidence because an SME reviews positives and a missed failure causes more harm.

Apply these distinctions carefully:

- A healthy shutdown normally starts on both sensors within one 30-minute sample. A slight thermal-mass lag is acceptable; a multi-hour lag with one side still at operating temperature is abnormal.
- A control-driven step down should settle around a stable horizontal average with both sensors coupled and a clear positive delta. A continuing downward trajectory or near-zero/inverted delta is not healthy modulation.
- A stable or expanding delta is healthy evidence only after the state stabilizes. It does not let a short right-edge rebound erase days of low-delta failure evidence.
- A prior pattern is a healthy precedent only when its depth and duration are comparable and it clearly recovered to the normal baseline. A shorter, shallower dip is not equivalent.
- Partial warmup after shutdown can show inlet warming while outlet stays cold. When the unit is still far below its normal On-state and delta is positive or expanding, do not misclassify the incomplete startup as failure.
- Do not classify Failure solely from one spike, a changed steady-state level with maintained delta, failure to regain the historically hottest temperature, or a reversed delta after both sides have reached ambient.

## Determine root cause from the earliest sustained departure

- Open Failure: the condensate/outlet side rises independently toward the steam/inlet side first. It may eventually meet or exceed steam temperature.
- Closed Failure: the steam/inlet side degrades toward the condensate side first while condensate initially holds or responds later. The delta must be collapsing; a stable or expanding delta is inconsistent with closed failure.
- Unknown: a failure is evident but the earliest directional break is unavailable, simultaneous, or otherwise cannot distinguish open from closed.
- Healthy always requires root cause N/A.

Before choosing Open or Closed, be able to state which side departed from its own baseline first, approximately when, and how the delta changed. Otherwise choose Unknown.

Closed failure does not require a zero or negative delta. Inlet temperature falling toward the outlet's historical operating band while outlet stays near its own baseline is strong closed-failure evidence even when a small positive delta remains. Severe closed failures may eventually resemble a shutdown at ambient; use the preceding trajectory, lag, and slope. Repeated inlet dips without outlet response can indicate sticky behavior only when they are new and do not promptly self-resolve.

Open failure can be gradual or abrupt. Remaining positive delta does not rule it out when the outlet has clearly and independently departed upward from its own baseline. If a post-startup failure appears fully formed and the directional change cannot be reconstructed, use Unknown.

## Confidence

- High issue confidence requires a clear operating phase, clear unit baseline, and reasonable exclusion of the main alternative explanation.
- Low issue confidence is appropriate whenever the alternative remains plausible; it deliberately escalates the case to SME review.
- High root-cause confidence requires a clear direction of change. Use Low when one mechanism is plausible but not decisive, and Unknown whenever direction cannot be justified.

## Tool discipline

Use numeric summaries to test a chart interpretation. Generate at most two targeted zoom charts: normally one recent alarm-adjacent range and optionally one historical comparison range. Avoid overlapping or speculative calls.
