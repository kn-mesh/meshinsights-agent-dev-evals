# Use Case Overview
- Spirax has an overlay pipe temperature sensor system called "Pulse" which is installed on either side of existing steam traps in a variety of commercial and industrial processes. 
- The purpose of the Pulse solution is to use the temperature data to identify when steam traps are failing and notify technicians to repair / replace the steam trap. They have a rules based Failure Detection Engine (FDE) which uses batch processing of the historical sensor data to detect potential failures. However, the FDE has a false positive rate of >50% and requires manual review by subject matter experts (SMEs) to confirm or deny the alarm. 
- Treat the FDE alarm as a trigger (that may be incorrect) to review the trap's health when the alarm was generated. A failure may have started well before the alarm; if that failed state persists through the broader period around the alarm, it is still a Failure.


## Spirax Pulse - Steam Trap Monitoring Sensors
- **Inlet temperature (steam side):** measurement on the outside of the pipe on the steam side of the steam trap. 
- **Outlet temperature (condensate side):** measurement on the outside of the pipe on the condensate side of the steam trap
- Temperature sensors are clamped to the exterior of the pipe. Exterior pipe temperatures are a proxy for the internal steam/condensate temperature. Pipes have different thicknesses and insulation which further impacts the accuracy of the temperature measurement. 
- These are low cost temperature sensors which measure/transmit every 30 minutes over a local LoRa wireless network.
- Each steam system and piping configuration is unique, which puts the installation location / quality at the discretion of the technician installing the system.
- The sensors are installed around any steam trap type (e.g. float, inverted bucket, etc.)
- Occasionally, the sensors are mistakenly flipped during installation (condensate temp sensor installed on the steam side and vice versa), which causes the readings to be swapped. The software does not detect or remediate this issue automatically.
- Occasionally, sensors are moved to a new system or reinstalled without updating the software to reflect the new system, which can appear as an abrupt change in the temperature patterns. Signs of this include: (1) step changes in steam/condensate temperatures preceded by a clear offline phase; (2) condensate / steam temperatures abruptly flipping relative positions [e.g. condensate temp was ~120C while steam was ~100C, then the values flipped to steam at ~120C and condensate at ~100C]; (3) sensors going offline for a period of time and then coming back online with a clear change in temperature patterns.

## Pipeline AI Output
Structured output follows `PulseFailureAnalysisResult` in `src/processors/common/structured_outputs.py`:

```json
{
    "classification": {
        "value": "Healthy" | "Failure",
        "confidence": "High" | "Low",
        "explanation": "string"
    },
    "root_cause": {
        "value": "Open Failure" | "Closed Failure" | "Unknown" | "N/A",
        "confidence": "High" | "Low",
        "explanation": "string"
    }
}
```

### Classification
- Healthy = Steam trap is in a healthy state as of the time of analysis. Failure = Steam trap is experiencing a failure such as open failure, closed failure, or an unknown failure type as of the time of analysis
- When the evidence is ambiguous, lean toward Failure with Low confidence. A missed failure causes real harm; a false positive just gets reviewed by an SME.
- In the explanation highlight what was found in the data/trends leading to the classification.

## Root Cause
- When there is a failure classification, classify the failure as open, closed or unknown. Unknown failures are a catch all when there's a failure that doesn't fit into open or closed.
- In the explanation highlight what was found in the data/trends leading to the classification.


# Steam System / Steam Trap Background

## Steam System Operating States / Terminology
- Steam systems alternate between `On` (In Operation) phases, `Off` (Shutdown) phases. 
   > **On:** Steam is actively flowing through the steam pipes with elevated pressure and temperature. A healthy steam trap will create a separation in the inlet/outlet temperatures (temperature differential) as lower temperature condensate is expelled through the trap to the lower pressure condensate line.
   > **Off:** Steam is not flowing through the system. After stabilization (at steady state) both the steam and condensate side temperature sensors will approximately converge to the ambient temperature of the room (assuming the pressure in both the steam side and condensate side have similar pressures and both pipes are dry).
- **Temperature Stabilization** Refers to the average measure temperatures over a period of time. For instance, a consistent steam temperature of 140C and a steam temperature that oscillates between ~130-150C for many hours/days are both *stable*. Stable temperatures can have some noise, we're looking at the broad trend over time. A simple test is to draw a linear regression line of temperature over a given period of time, if the slope is ~flat then we have a stable system. 
- `Baseline On` / `Baseline Off` phases are shorthand for the typical historical temperature trends of a healthy functioning steam system and trap. When information, data and context is lacking the assupmtion is that the steam trap was healthy in the past (e.g. over the past year until a failure pattern emerged) 
- Transitions between `On` and `Off` states: 
    > **Shutdown:** Transition from `On` state to `Off` state, prior to system stabilizing near ambient temperature.
    > **Startup:** Transition from `Off` state to `On` state, prior to system stabilizing at elevated temperature.
- **Control Modulation:** During the `On` phase, steam systems often have a control system that regulates the steam pressure/temperature as required by the process. Control Modulation refers to a deliberate steam side change that results in a step change increase or decrease in steam/condensate temperature which stabilizes.
- **Temperature Differntial or Delta:** Shorthand for the difference between the steam and condensate side temperatures. 


## Steam System Configurations
- **Condensate Discharge Line:** The outlet line of the steam trap that is designed to divert condensate and gases out of the system. This line is often shared across a broader steam system and typically operates at a lower pressure (ideally at atmospheric pressure) than the steam inlet side of the trap, but the actual return pressure can vary significantly depending on the condensate recovery design, elevation changes, downstream restrictions, flashing behavior, and local backpressure near the trap outlet. 
- **Steam Trap Types:** The temperature sensors are installed on various types of steam traps such as `Float`, `Inverted Bucket`, `Thermostatic`, `Thermodynamic`, etc. Some installations record the trap type as metadata. 
- **Steam Trap Installations:** Steam traps are installed on various types of steam systems and in different locations such as `Steam Distribution Lines` and `Heat Exchangers`. We do not have this information for the installations.
- **Steam System Processes:** Each steam system is unique to it's process. Some systems are always on, others have frequent shutdowns as a part of their normal process. 


# General Classification Guidance

## Interpreting Raw Temperature Values
- We cannot know the precise temperature and pressure in the pipes with the current sensor system. Additionally variations are present across: steam systems, piping, ambient environment, and installation placement / quality. However, raw temperature readings provide important context when interpreted relative to the system's own historical baseline and current operating state. 
- Even with these limitations physics matter in the interpretation, for instance: higher steam temperatures create larger temperature differentials when compared with the condensate side on healthy traps (assuming that thet condensate side is at a relatively consistent pressure). 
- Spirax assumes that the temperature inside the pipe is ~10-30C higher than what is measured on the exterior of the pipe.


## Misc Guidance
- The temperature delta is one of the most important metrics to track over time when assessing the health of a steam trap. A persistent, unexplained reduction in inlet-outlet temperature differential during a confirmed 'On' state can be a useful failure indicator, especially when it represents a clear deviation from that trap's historical baseline.
- Don't trust a single temperature reading or differential in isolation to make a decision, trust the temperature trends over time. (e.g. backpressure can induce a single temperature reading spike during an off phase)
- The days leading up to the potential failure is the most critical time to focus on. However, look at the preceding months to search for longer term trends and patterns such as baseline 'On' and 'Off' states, control modulations, shutdowns and startups to identify deviations from the norm. Given that each steam system is unique to the process and the installation is unique to the system, what appears like a failure in isolation may have occured previously without any issues. In these recurring patterns assume this is a normal part of the system and not a failure.
- When determining root cause, analyze the trends leading up to the potential failure rather than focusing only on the immediate pattern around the alarm. Once the temperature delta has largely collapsed, the failure mode may be harder to distinguish than it was during the lead-up.
- Given that the condensate line is often shared, failures from nearby steam traps in the system can impact the condensate line temperature, causing patterns that appear confusing in isolation (e.g. an open failure on a nearby trap causing the condensate line temperature to rise due to the shared line).


# Identifying Healthy Steam Traps
## Healthy Steam Trap, During Baseline 'On' State/Phase
- Steam side temperature is higher than the condensate side temperature. (e.g. steam side temp hovers around 130C while the condensate side temp hovers around 110C)
- The temperature delta should be relatively consistent over time as long as the temperature of the steam side temperature is relatively consistent. When the control system lowers the steam temperature, the temperature delta will typically decrease. The delta can ~converge as the temperature of the steam approaches 100C given that the condensate discharge line is often near atomospheric pressure where the saturation temperature of water is ~100C.
- Some systems (depending on the particular steam process and trap type) have high amounts of temperature variability/noise when healthy. It's important to track the temperature trends over time and identify clear breaks in the trends / patterns.

## Healthy Steam Trap, During Shutdown Transition
- During a healthy shutdown, both the steam side and condensate side temperatures typically decrease from their elevated 'On' state levels toward a much lower steady-state temperature associated with the `Off` state. 
- Typically there is a rapid decrease in both the steam and condensate temperatures in near unison with similar slopes. It's helpful to review past occurances of rapid drops in temperature from high to low (realistic ambient temps) which reached similar temps with similar slopes (rate of temperature drops). 
*Rapid is relative to the behavior of closed failures that are often confused with shutdowns.*

## Healthy Steam Trap, During Baseline 'Off' State/Phase
- The steam and condensate side temperatures have ~converged to the ambient temperature (or close to it). There can be a temperature difference between the steam and condensate side temperatures due to the difference b/w the steam pipes and the condensate line (dry v. filled with water, pressure), but it should be relatively consistent over time.
- The ambient temperature is not directly measured and some environments such as an industrial facility can be quite hot. The ~ambient temperature is inferred by a massive drop in temperature across both the steam and condensate side temps to a realistic ambient temperature. 

## Healthy Steam Trap, During Startup Transition
- During a healthy startup, both the steam side and condensate side temperatures typically increase from their lower 'Off' state levels toward the unit's historical 'On' state range. In many systems the two temperatures generally rise together, but the timing, slopes, and intermediate patterns may vary due to process ramp-up behavior, control modulation, retained heat, condensate drainage dynamics, and installation-specific sensor behavior. A healthy startup is best identified by the system returning to a previously observed healthy 'On' state pattern, including its typical temperature relationship and trend behavior.
- A startup pattern alone cannot dictate a failure classification. It's most important to analyze the stabilzed temperatures and differentials in the `On` state that emerges.

## Healthy Steam Trap, During Control System Adjustments (Control Modulation)
- At the onset of a control change, a step change in both the steam and condensate side temperatures will occur. After the initial step change stabilization will occur with some systems having oscillations (such as a repeated shark tooth pattern). 
- Once the system has stabilized there may be large oscillations to the steam side temperature (e.g. +/- 20C) which isn't a sign of an issue if there is temperature stabilization (flat trend of avg temperature over time...as opposed to a decrease in temperature over time).
- Often times there will be thermal coupling, where the steam and condensate temperatures will mirror each other. If a temperature differential is maintained, a lack of thermal coupling is ok. However, it's worth a deeper look if there is no thermal coupling paired with a temperature delta collapse.
- A situation that often causes confusion is when the steam side temperature drops from control modulation from a high temperature (e.g. 130C) where there was a meaningful temperature differential (e.g. 15C) to a steam side temperature <= 100C which induces a temperature differential collapse (e.g. 3C). This pattern in isolation isn't a closed failure given that we expect the temperature differential to decrease as the steam side temperature gets closed to the saturation temperature of the condensate line.


## False Positives (Look like failures but are healthy/normal)
- When the temperature delta increases. There is not an identifiable failure mode that is triggered by temperature delta increasing either during an `On` or `Off` state relative to the baseline.
- If a change in behavior that has emerged and persisted through the analysis timeframe, it's important to check if this pattern has occured previously. If the pattern has occured previously with similar severity (relative to a potential failure pattern) AND the issue resolved itself (e.g. temperature delta that was collapsed increased to 15C), this is a part of the process and should be classified as a healthy trap.


# Specific Failure Classification Guidance

## Open Failure
- **What Happens to the steam trap:** The valve mechanism has degraded or sticks open either partially or completely. Live steam passes through the steam trap, causing the condensate temperature to rise.
- **Temperature trends:** The general trend is that the condensate temperature rises towards the steam temperature during a sustained open failure. This trend can be rapid (step change) and/or gradual. The condensate may reach or even exceed the steam temperature during a sustained open failure. It's possible for the steam temperature to drop as the condensate temperature rises.


### Closed Failure
- **What Happens to the steam trap:** The valve mechanism sticks closed, either as a partial or complete blockage. Debris buildup is also considered a closed failure. Steam is unable to pass through the trap, causing condensate to pool on the steam side of the trap (inlet to the trap), causing the steam side temperature to drop. During a complete blockage no condensate will pass through to the condensate side.
- **Temperature trends:** The general trend is that the steam side temperature decreases first while the condensate temperature stays near its normal level or responds more slowly. When a significant blockage occurs, the steam side temperature may drop rapidly until it converges (or even drops below) the condensate temperature, after which both temperatures may continue to decline together. In many closed failures, temperatures stabilize above ambient. However, in severe or complete blockages, both sensors can eventually drop to or near ambient temperature, which may resemble a shutdown at the end state. The distinguishing evidence is often in the slope leading up to the final drop, not the final resting temperature alone.
- The rate at which a closed failure occurs varies drastically from situation to situation. Some traps may have a closed failure that occurs over a period of weeks, while others may have a closed failure that occurs over many hours. In either case, closed failures do not cause temperatures to drop as rapidly as shutdown periods.
- It can be difficult to distinguish between a closed failure and a healthy shutdown. It is best to compare the potential failure pattern with a previous healthy shutdown pattern for that same unit, including the slopes, timing, degree of convergence and temperature at stabilization. This can be difficult to see without zooming into the data and comparing the patterns closely.
- **Helpful signals when distinguishing a closed failure from a healthy shutdown:** (1) the steam side temp dropping before the condensate side or the condensate showing a visible lag; (2) temperatures stabilizing above ambient [previously observed during a healthy shutdown] for an extended period after the drop; (3) meaningful deviation from prior clear shutdown patterns and (4) steam-side degradation or narrowing delta in the hours or days before the main drop without signs of a the control system causing the drop.

### Other Failures
- Not all failures fit cleanly into purely "Open Failure" or "Closed Failure" categories based on exterior temperature measurements alone. In practice, some abnormal conditions may reflect partial blockage, intermittent restriction, flooding, stall due to backpressure or insufficient differential pressure, venting problems, installation issues, or broader system effects that cannot be confidently distinguished from the available telemetry. For evaluation purposes, these cases are grouped into "Unknown" as a catch-all root cause category.
- **Example:** Prior to a shutdown, the system is healthy. After startup, both temperatures rise well above the baseline 'Off' state temperatures but stabilize with little to no temperature delta at an abnormal elevated level. In this situation there is clear evidence of abnormal behavior consistent with a failure, but the specific mechanical or system-level root cause cannot be determined confidently from the available data alone. In this example it should be classified as "Failure" with "Unknown" as the root cause.


## Complex / Confusing Situations

### 1. Temperature Sensors Flipped During Installation
- When reviewing temperature data where the condensate side temperature is persistently much higher than the steam side temperature, it is important to consider the possibility that the temperature sensors were flipped during installation or reinstallation. Review the preceding historical data to determine whether this has been a persistent pattern. If the reversal is long-standing and internally consistent, you must interpret the values labeled as steam side temperature as condensate side temperature and vice versa, while still considering other explanations such as unusual installation geometry or shared-line thermal effects.
- Do not classify as a failure just because the sensors were flipped during installation.

### 2. Potential Failure Behavior Identified, But Previous Historical Patterns Suggest it's a Normal Part of the System / Process / Control System Modulation
- Some steam systems produce temperature patterns and behavior that appear to be an open or closed failure when viewed in isolation. However, it's important to look at the previous historical patterns to see if this is a situation that has occurred previously and resulted in a return to a healthy state. It's useful to look closely and determine if it's a control system modulation. In these situations, classify as healthy.


### MISC (related to 250003694 confusing all models/pipelines)
1. If there are clear signs of a failure that have persisted for days, do not assume that a few datapoints (e.g. a couple hours) showing recovery to a healthy temperature delta represents a healthy trap. You must see stabilization at a healthy recovery state to consider this trap healthy. In this situation consider this a `Failure` with `Low Confidence`.

2. A clear sign of a failure is a steam trap that is unable to stabilize at a temperature paired with a downward trajectory/slope and low temperature delta, even if there's thermal coupling (the reason why I paired these together is that some systems have lots of ocntrol modulation that doesn't stabilize in a temperature band for long and thats perfectly fine...what's a clear failure is the downward trend w/ collapsed temperature delta as this is a classic blockage/closed failure pattern)
