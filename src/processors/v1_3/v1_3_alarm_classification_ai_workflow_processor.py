"""AI workflow processor for v1_3 Pulse alarm classification from chart images."""
# ruff: noqa: F541

from __future__ import annotations

from mi.ai import AIProcessorConfig, AIWorkflowMixin, UserMessage
from mi.core.processors import BaseProcessor

from src.objects.process_object import PulseFailureAnalysisProcessObject
from src.processors.common.structured_outputs import PulseFailureAnalysisResult


class V1_3AlarmClassificationAIWorkflowProcessorConfig(AIProcessorConfig):
    """Configure the v1_3 AI workflow processor."""

    name: str | None = "v1_3_alarm_classification_ai_workflow_processor"
    window_days_list: list[int] = [7, 30, 365]
    timeout: float | None = 120
    transport_retries: int = 3
    output_retries: int | None = 0


class V1_3AlarmClassificationAIWorkflowProcessor(
    AIWorkflowMixin[PulseFailureAnalysisProcessObject, PulseFailureAnalysisResult],
    BaseProcessor[PulseFailureAnalysisProcessObject],
):
    """Classify one Pulse alarm using the segmented v1_3 chart descriptions."""

    output_schema = PulseFailureAnalysisResult

    config: V1_3AlarmClassificationAIWorkflowProcessorConfig

    def __init__(
        self,
        config: V1_3AlarmClassificationAIWorkflowProcessorConfig | None = None,
    ) -> None:
        """Initialize the v1_3 AI workflow processor with typed AI settings."""
        resolved_config = config or V1_3AlarmClassificationAIWorkflowProcessorConfig()
        super().__init__(resolved_config)
        self.config = resolved_config

    def _build_system_prompt(
        self, data_object: PulseFailureAnalysisProcessObject
    ) -> str:
        """Build the system prompt for classifying one Pulse alarm."""
        return f"""
<your_task>
A rules-based Failure Detection Engine (FDE) flagged a potential steam trap failure. The FDE has a >50% false positive rate. Review the temperature charts and classify:
- Issue: "Healthy" or "Failure"
- Root cause (if Failure): "Open Failure", "Closed Failure", or "Unknown"
- Root cause (if Healthy): "N/A"

**Critical: when the evidence is ambiguous, lean toward Failure with Low confidence. A missed failure causes real harm; a false positive just gets reviewed by an SME.**
**Also critical: treat the FDE alarm as a trigger (that may be incorrect) to review the trap's health when the alarm was generated. A failure may have started well before the alarm; if that failed state persists through the broader period around the alarm, it is still a Failure.**
</your_task>

<measurement_context>
- Two exterior pipe-surface temperature sensors: one on the steam/inlet side, one on the condensate/outlet side of a steam trap. These are proxies — not exact fluid temperatures.
- Low-cost sensors transmitting every 30 minutes via LoRa. Each installation is unique in pipe thickness, insulation, sensor placement quality, and process conditions.
- The condensate discharge line is often shared across multiple traps, so nearby failures or system effects can influence condensate-side readings.
- Sensors are occasionally installed flipped (steam/condensate swapped) or moved to a new system without updating software. Evidence of a flip requires a long-standing historical reversal — a post-shutdown inversion alone is never sufficient.
</measurement_context>

<chart_reading_guide>
You receive three chart windows (365-day, 30-day, 7-day), each with two panels:
- **Top panel:** Raw temperatures — Red = Steam/Inlet, Blue = Condensate/Outlet.
- **Bottom panel:** Steam-minus-Condensate delta — Purple rolling average + raw delta.

Start with the 365-day view to establish this unit's historical baseline, then use 30-day for recent context, and 7-day for alarm-adjacent detail. Always compare the raw temperature and delta panels together within each window.
</chart_reading_guide>

<decision_framework>
Work through these questions in order. Each builds on the previous answer.

<question_1_normal_behavior>
Using the 365-day and 30-day charts, establish:
- The typical On-state temperature range and delta for this specific unit.
- The typical Off-state (ambient) temperature range.
- The typical shutdown pattern: how fast do both sensors drop? Do they drop together?
- The typical startup pattern: how does the unit return to its On-state?
- Any recurring patterns that might look abnormal in isolation but are actually normal for this unit.
</question_1_normal_behavior>

<question_2_sensor_labels>
Only suspect a sensor flip if there is a **long-standing** historical reversal where the labeled condensate side consistently behaves like the inlet/steam (higher temperature during On-states, responsive to process changes the way steam should be) and vice versa. A flip is present from the very start of available data or coincides with a clear instrumentation change (connectivity gap followed by a step change into a new durable regime). If the temperatures started with a normal relationship and then **trended** to a reversed state over time, that is a failure — not a sensor flip. If flipped, mentally swap the labels for the entire analysis and re-evaluate all patterns with corrected identities.
</question_2_sensor_labels>

<question_3_operating_phase>
- **On-state:** Elevated temperatures with a sustained delta.
- **Off-state:** Both temperatures converged near ambient.
- **Shutdown:** Both temperatures dropping from On toward Off. In a healthy shutdown, both sensors must begin their drop within 30 minutes (1 data point) of each other. A multi-hour lag where one sensor stays elevated while the other drops is a failure signal (likely Closed Failure), but only if the steam side drops to ambient while the condensate side remains at full operating temperature for an extended period. If both sensors drop but one simply lags slightly due to thermal mass, it is still a healthy shutdown.
- **Startup:** Both temperatures rising from Off toward On. Healthy startup is recognized by returning to a previously observed healthy On-state pattern.
- **Control modulation / low-load:** Steam pressure/temperature reduced by the control system. Both sensors move in the same direction (thermal coupling). Delta may shrink substantially, especially below ~100C — this is normal. A common healthy pattern is a **step change downward**: a rapid drop in temperatures followed by a new, lower-temperature operating regime. Because this is a process shift, it will not have the leading degradation trends of a failure. To verify it is healthy modulation, look at the pattern *during* the new regime: it may be noisy or sawtooth, but it must maintain a **stable horizontal average** and the sensors should remain thermally coupled. The delta will naturally shrink at lower temperatures—this is normal thermodynamics, not a failure. However, a step-change downward is ONLY healthy if the new state maintains a clear, positive delta. If the delta collapses to near-zero or inverts during the new regime, it is a failure, regardless of thermal coupling. If the steam side shows movement but the condensate side stays flat near its prior baseline, that is evidence *against* healthy modulation.
</question_3_operating_phase>

<question_4_abnormality_vs_history>
This is the most important question. Compare the alarm-adjacent behavior against the baselines you established in Question 1.
- You are using the alarm as an opportunity to assess the unit's health in the broader period around the alarm, not just the exact alarm timestamp or last datapoint. If the trap entered a sustained failure state earlier and remains in that abnormal state through the alarm-adjacent period, classify Failure.
- Do not let a final shutdown, cooldown, or other transient alarm-adjacent transition override evidence that the trap had already entered and remained in a failed state across the broader period leading into the alarm.
- If the unit showed clear failure evidence for days and then only the final few datapoints look healthier, do NOT assume the trap recovered. A brief rebound or a couple hours of healthier-looking delta is not enough to call the trap Healthy; you must see the trap stabilize in a sustained healthy recovered state. Otherwise classify Failure with Low confidence.
- If this exact pattern has occurred before in the 365-day history and the unit returned to healthy operation afterward, it is likely normal for this system — classify Healthy. A prior event only counts as a healthy precedent if it was similar in depth and duration and clearly recovered to the unit's normal baseline. A shorter, shallower, self-resolving dip does not excuse a longer, deeper, or unrecovered steam-side collapse.
- If the pattern is new, persistent, and clearly deviates from this unit's established healthy behavior, it is a failure signal.
- A persistent, unexplained reduction in temperature delta during a confirmed On-state is a failure indicator — even if the remaining delta is still substantial. The trend (shrinking over time) matters more than the absolute value at any point.
- After a shutdown/restart, compare the first stabilized elevated plateau against the pre-shutdown healthy On-state baseline. If the restarted On-state settles into a clearly lower-delta, unprecedented regime for this unit, classify Failure even if the chart's right edge later cools down again.
- For root cause, identify the **earliest sustained departure from baseline** before the end-state fully collapses. Decide whether the condensate side clearly rose toward steam first (Open) or the steam side clearly degraded first (Closed). If the earliest break is already fully formed or directionally ambiguous, use Unknown.
</question_4_abnormality_vs_history>

<question_5_issue_classification>

**First, check these strong healthy signals — they support Healthy unless contradicted by a preceding or following sustained abnormal regime elsewhere in the broader alarm-adjacent period:**
- **Expanding or stable delta:** If the temperature delta has expanded or remained stable through the relevant operating period, this is strong Healthy evidence against both open and closed failure. However, this only applies when that expanded/stable delta represents a stabilized operating regime. A brief right-edge rebound, a few datapoints of recovery, or the first part of a restart/warmup does NOT erase days of prior failure evidence. You must see sustained stabilization in a healthy recovered state before classifying Healthy.
- **Simultaneous rapid drop:** If both sensors begin their drop within 30 minutes (1 data point) of each other, treat that drop itself as a shutdown — not a closed failure. This is true even if the steam side reaches a lower temperature than condensate afterward (shared condensate lines retain heat). A multi-hour lag where one sensor stays elevated while the other drops is a failure signal, but only if the steam side drops to ambient while the condensate side remains at full operating temperature for an extended period. Do not let a final simultaneous shutdown erase evidence that the unit had already entered a sustained failed state beforehand.
- **Sensor flip correction:** If you identified a long-standing sensor flip in Question 2, re-evaluate with corrected labels. If the corrected pattern is consistent with healthy behavior, classify Healthy.
- **Recurring historical pattern:** If this exact pattern has occurred before in the 365-day history and the unit returned to healthy operation, classify Healthy — even if the pattern looks abnormal in isolation.
- **Post-shutdown partial startup:** After a shutdown, if the steam side warms (e.g. to ~60C) but condensate stays cold while the unit is still far below its normal On-state (~130C+), the system simply hasn't produced condensate yet. The expanded delta is not a failure — it is expected during partial warmup. Do NOT compare the current absolute steam temperature to the historical On-state baseline and call the low steam temp "degradation" — the unit is not in an On-state, it is partially warming up. Look at the delta panel: if the delta is expanding or positive, this is physically healthy.

**Then, classify as Healthy when** the temperature evidence supports normal operation:
- The pattern matches a prior healthy baseline (On, Off, shutdown, startup, or modulation).
- Both sensors remain thermally coupled during modulation (moving in the same direction together), and the delta is proportionally healthy for the current temperature level. Delta naturally shrinks at lower temperatures, especially below ~100C — this is thermodynamics, not failure. Control modulation can occur for the first time without historical precedent; new modulation with a healthy delta is not a failure. However, after a step change into a lower regime, the new regime should stabilize around a roughly horizontal average. If the unit instead shows a clear downward trend that ends in a materially lower, low-delta operating regime versus its prior healthy baseline, that is evidence against healthy modulation and toward Failure even if the sensors remain thermally coupled.

**Classify as Failure when** you observe a sustained deviation from this unit's healthy historical behavior that is consistent with a trap malfunction:
- **The primary failure signal is the delta panel.** Compare the current delta to this unit's historical baseline delta. If the delta has persistently collapsed relative to the historical baseline during a comparable operating state, that is a failure — even if the remaining delta is still substantial. A delta that is clearly and persistently shrinking over time is a failure signal. However, if the absolute steam temperature has dropped due to a process step-change, the delta is expected to shrink. A smaller but stable delta at a lower temperature is healthy; a true failure delta collapses to near-zero or inverts while the steam side is trying to operate.
- **Thermal coupling does NOT rule out failure.** Both sensors can still move together / mirror each other during a closed failure, open failure, or post-startup failure state. Do not classify Healthy just because both sensors modulate in unison — always check whether the delta has collapsed relative to the historical baseline.
- **Do not let a brief recovery erase a sustained failed regime.** If the trap spent days in a clearly abnormal low-delta state and only the last few datapoints recover toward a healthier delta, do not classify Healthy unless that recovery stabilizes into a sustained healthy operating state. Otherwise classify Failure with Low confidence.
- **Failure can still look thermally coupled.** A trap can fail into a lower stabilized operating regime. If the unit shows a clear downward trajectory/slope and then settles into a materially lower temperature band with a low or collapsed delta versus its prior healthy baseline, treat that as failure evidence even if both sensors remain thermally coupled. This is especially important for blockage/closed-failure patterns.
- **Closed failure does NOT require zero or negative delta.** If the steam side falls materially from its healthy On-state toward the condensate side's historical operating band while the condensate side stays roughly flat near its own baseline, that is strong Closed Failure evidence even if a small positive delta remains.
- **Healthy modulation changes the operating level; closed failure changes the relationship.** Do not call it healthy modulation just because both sensors are still thermally coupled. If the steam side is the side moving down toward the condensate baseline, or if the new lower-temperature regime keeps degrading rather than flattening, that is failure evidence.
- The condensate side is trending upward toward the steam side (open failure signature).
- The steam side is degrading while the condensate side holds steady or lags significantly (closed failure signature).
- After startup/restart, compare the first stabilized elevated plateau against the pre-shutdown healthy baseline. If the restarted On-state fails to establish a roughly horizontal healthy plateau and instead keeps degrading downward with materially reduced delta, that is failure evidence. Repeated restarted On-phases that each degrade into a low-delta regime are strong evidence against healthy modulation.
- Intermittent steam-side dips and partial recoveries without condensate response can indicate a sticky/chattering closed failure, but only when the pattern is new in the 365-day history and does not promptly recover to the unit's normal baseline. If similar dips recur historically and self-resolve, treat them as normal process behavior rather than a failure.

**Do not classify as Failure based solely on:** a single spike or odd reading, a changed steady-state level with maintained delta, the unit not returning to its hottest historical On-state, or an expanding/expanded delta.
</question_5_issue_classification>

<question_6_root_cause>

Before assigning Open or Closed, identify which side departed from **its own historical baseline** first and approximately when that departure began. If you cannot name both clearly in one concrete sentence, use Unknown.

<open_failure>
The valve sticks open. Live steam passes through, heating the condensate side.
- **Anchor on the earliest sustained break from baseline:** If the first clear abnormal change is the condensate side rising toward the steam side over hours, days, or even months, that is Open Failure even if the end-state later looks thermally coupled or fully converged.
- **Look for:** Condensate temperature trending upward toward steam temperature. This can be gradual or a step change. Condensate may reach or exceed steam. The steam side may drop as condensate rises.
- **Key distinction from healthy modulation:** In healthy modulation, both sensors move together driven by the control system. In an open failure, the condensate side is rising *independently* toward the steam side, departing from its historical baseline.
- **Remaining delta does not rule it out** — if the condensate trajectory is clearly and sustainably departing from its baseline, that is an open failure even with significant delta remaining.
- Open failures emerging after shutdowns or startups may appear fully formed. Compare with the pre-shutdown healthy baseline.
</open_failure>

<closed_failure>
The valve sticks closed. Condensate backs up, steam cannot pass through.
- **Physical requirement:** The delta must be **collapsing** because the steam side is degrading. If the delta is expanding or stable, it physically cannot be a closed failure — do not call it one.
- **Anchor on the earliest sustained break from baseline:** If the first clear abnormal change is the steam side gradually or abruptly degrading toward the condensate side while condensate holds near its prior level or responds later, that is Closed Failure even if the end-state later becomes thermally coupled or near ambient.
- **Look for:** Steam side temperature dropping while condensate stays near its prior level or follows much later/more slowly. The delta collapses because the steam side degrades. In severe cases, both may eventually drop to near ambient.
- Closed failure often appears as the steam side collapsing toward the condensate side's historical operating band while the condensate side stays roughly flat near its own baseline. That is strong closed-failure evidence even if the remaining delta is still positive.
- **Key distinction from a healthy shutdown:** In a shutdown, both sensors drop rapidly together in the same time window. In a closed failure, the steam side leads by hours and the condensate side lags visibly. Compare the slope, timing, and lag against this unit's prior healthy shutdowns.
- **Key distinction from control modulation:** In healthy modulation, both temps drop together and then both modulate together at the lower level — and the delta remains proportionally healthy for the temperature level. In a closed failure, the delta is persistently collapsing in an unprecedented way. If both sensors are modulating together and the delta is proportionally healthy for the current temperature, it is modulation — not a closed failure. But some closed failures do cause near-simultaneous drops; in those cases the key evidence is that the resulting persistent delta collapse is unprecedented for this unit.
- **New lower-regime closed failure:** A closed failure can present as a new, persistent lower-temperature operating regime where both sensors remain thermally coupled and the delta stays positive but materially smaller than the unit's historical On-state delta. If that new regime is unprecedented for this unit and there is no visible control-driven step-change that explains it, classify Closed Failure even though the end-state still looks coupled.
- **Additional closed failure signals:** (1) Steam-side degradation or narrowing delta in the hours/days before the main drop. (2) Temperatures stabilizing above ambient for an extended period after the drop. (3) Repeated steam-side dips with partial recovery but no condensate response (intermittent/sticky behavior). (4) Pre-alarm instability: Look for a **progressively** narrowing delta or downward-trending instability in the days leading up to a collapse. Do not confuse this with a healthy step-change into a noisy modulation regime or normal low-temperature noise; a failure trend degrades over time, whereas healthy modulation oscillates around a stable average.
- Another closed-failure pattern is when the unit shows a clear downward trend (not a standalone step change) and then stabilizes in a materially lower operating band with a low or collapsed delta relative to its prior healthy baseline. Even if the two sensors remain thermally coupled, that combination of downward trajectory plus reduced delta is evidence for blockage/closed failure rather than healthy modulation.
- Repeated restarted On-phases that each fail to establish a stable healthy plateau and instead degrade downward into a reduced-delta regime are strong closed-failure evidence, even if the final datapoints later show a temporary expanding delta.
- Closed failures cause temperatures to drop more slowly than shutdowns.
- A reversed delta at ambient temperatures (during/after shutdown) is not sufficient by itself — condensate pipes can retain heat differently.
</closed_failure>

<unknown_failure>
Use Unknown when you are confident the trap has failed but cannot determine whether it is open or closed. **This is not a last resort — it is the correct call whenever the mechanism is ambiguous.**
- Identify the earliest sustained departure from baseline. If you cannot name which side moved first and approximately when, output Unknown.
- After startup, the unit settles into a persistently abnormal elevated state with collapsed/reversed delta that doesn't match prior healthy behavior, but the direction of change is ambiguous.
- A failure emerged after a shutdown/restart and the post-restart state is clearly abnormal, but you cannot tell whether the condensate rose toward steam or the steam degraded toward condensate because the failure appeared fully formed.
- The pattern could reflect flooding, stall, or other conditions that exterior temperature data cannot separate.
- If the earliest sustained break from baseline is already ambiguous, or both sides drift toward each other without a clear leader, prefer Unknown over forcing Open or Closed.
</unknown_failure>
</question_6_root_cause>
</decision_framework>

<confidence>
**Issue classification confidence:**
- High: The operating phase is clear, the baseline is clear, and you can reasonably rule out the main alternative explanation.
- Low: The alternative explanation remains plausible, or the case is genuinely ambiguous. **Use this liberally — it escalates to SME review, which is the safe outcome.**

**Root cause confidence:**
- High: The direction of change (which side moved toward the other) is clear.
- Low: A root cause is plausible but not decisive.
- If you cannot justify open vs closed, use Unknown rather than guessing.
</confidence>

<critical_rules>
Re-check these before producing output:
- Judge the trap from the broader alarm-adjacent period, not just the final datapoint. If the right edge is a transient, classify from the most recent stabilized regime before it.
- Stable or expanding delta is Healthy evidence only when it represents a stabilized regime, not a brief rebound or early restart/warmup.
- If both sensors drop within 30 minutes, that drop itself is a shutdown/load step, not a closed failure. A closed failure can still emerge afterward.
- Thermal coupling alone does not prove Healthy. Always check whether delta and trajectory are abnormal versus the unit's own baseline.
- After restart, compare the first stabilized elevated plateau to the pre-shutdown healthy baseline. A new materially lower-delta regime can still be Failure even if thermally coupled.
- A recurring pattern is Healthy evidence only if the prior occurrence was similar in depth and duration and clearly resolved back to a sustained healthy baseline.
- If the unit shows a clear downward trend and then stabilizes in a materially lower temperature band with a low or collapsed delta versus its prior healthy baseline, treat that as failure evidence even when thermal coupling is present.
- Closed failure does not require zero or negative delta. Steam collapsing toward the condensate baseline while condensate stays roughly flat is strong closed-failure evidence even if a small positive delta remains.
- If you cannot confidently rule out failure, output Failure with Low confidence rather than Healthy with Low confidence.
</critical_rules>

<output_format>
1. Issue Classification:
    - Value: "Healthy" or "Failure".
    - Confidence: "High" or "Low".
    - Explanation: 1-2 sentences citing the specific temperature evidence and the operating phase. Name the historical baseline you compared against. Do not refer to the specific charts you used, it's more important to refer to the dates, temperatures and patterns.
2. Root Cause Classification:
    - Value: "Open Failure", "Closed Failure", "Unknown", or "N/A" (if the issue is "Healthy")
    - Confidence: "High" or "Low". 
    - Explanation: 1-2 sentences citing which side changed and the trajectory evidence. If Unknown, explain why open vs closed cannot be determined. Provide only "N/A" if the issue is "Healthy". Do not refer to the specific charts you used, it's more important to refer to the dates, temperatures and patterns.
</output_format>
"""

    def _build_user_message(
        self, data_object: PulseFailureAnalysisProcessObject
    ) -> UserMessage:
        """Build the user message that explains the v1_3 chart layout."""
        alarm_context = data_object.get_alarm_context()
        charts: dict[int, str] = {}
        for days in self.config.window_days_list:
            chart = data_object.get_temperature_chart(days)
            if chart is None:
                raise ValueError(
                    f"Required v1_3 combined pre-alarm chart for {days}-day window is missing."
                )
            charts[days] = chart

        sorted_windows = sorted(self.config.window_days_list, reverse=True)
        image_descriptions = "\n".join(
            self._build_image_description(index=i, days=days)
            for i, days in enumerate(sorted_windows, 1)
        )

        message = UserMessage().add_text(
            f"""
<user_prompt>
<alarm_context>
Steam trap type: {data_object.get_steam_trap_type() or "unknown"}
FDE generated alarm detected at: {alarm_context["selected_alarm"]["detected_at"].isoformat()}
</alarm_context>

<image_descriptions>
{image_descriptions}
</image_descriptions>

<graph_usage_instructions>
- The last datapoint on the far right of each chart is where the FDE alarm was generated.
- The shorter windows provide clarity on what occured near the alarm, and the granular relationship b/w the temperature sensors which is necessary to understand if there's a control/modulation of the steam process or a failure.
- The 365-day chart is segmented into four consecutive time slices so you can see raw historical behavior more clearly while still comparing the full year.
- In the segmented 365-day chart, read the segments from left to right in chronological order. The far-right segment contains the period closest to the alarm.
- Within each segment, compare the top raw-temperature panel and bottom delta panel together before moving to the next segment.
- The shorter 30-day and 7-day charts remain single continuous windows and should be used for the most precise alarm-adjacent timing.
- Note: In the raw temperature graphs (top panels), lines are not connected when sensors lose connectivity for more than 2.5 hours. These gaps appear as breaks in the lines.
</graph_usage_instructions>
</user_prompt>
"""
        )
        for days in sorted_windows:
            message = message.add_image(charts[days], media_type="image/png")
        return message

    def _build_image_description(self, *, index: int, days: int) -> str:
        """Build the per-image description shown in the v1_3 user message."""
        if days == 365:
            return (
                f"Image {index}: Combined analysis for the {days} days leading to the alarm.\n"
                "- Top row: Raw temperatures split into four consecutive chronological segments "
                "(Red line = Steam, Blue line = Condensate). All four segments use the same y-axis.\n"
                "- Bottom row: Steam-minus-Condensate delta for those same four segments "
                "(Purple line = 4h rolling average, Shaded purple area = area under average, "
                "faint purple line = raw delta). All four segments use the same y-axis."
            )

        return (
            f"Image {index}: Combined analysis for the {days} days leading to the alarm.\n"
            "- Top panel: Raw temperatures (Red line = Steam, Blue line = Condensate).\n"
            "- Bottom panel: Steam-minus-Condensate delta (Purple line = 4h rolling average, "
            "Shaded purple area = area under average, faint purple line = raw delta)."
        )

    def _attach_response(
        self,
        data_object: PulseFailureAnalysisProcessObject,
        response: PulseFailureAnalysisResult,
    ) -> None:
        """Store the structured AI response on the process object and artifacts."""
        data_object.set_ai_result(response.model_dump())
        super()._attach_response(data_object, response)
