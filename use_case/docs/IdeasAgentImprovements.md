# Potential Data Improvements
- Add trap-type-specific logic or features, since expected temperature signatures differ by steam trap type. For example, thermodynamic traps naturally cycle open and closed and can discharge condensate near steam temperature, so their downstream temperature patterns may look different from other trap types even when healthy.
    > Potentially lookup and feed into user message automatically (so we don't need to have a dictionary of trap types and their expected behavior)
- Replace or augment raw temperature delta with normalized temperature-difference features that account for the absolute operating temperature of the system. This is important because expected inlet/outlet temperature relationships change as steam-side pressure changes, since saturation temperature varies with pressure. A normalized feature is therefore more representative of trap state and less sensitive to shifts in overall system operating level.
    > normalized delta = (inlet_temp - outlet_temp) / inlet_temp
    > outlet-to-inlet ratio = outlet_temp / inlet_temp
- do we look at adjacent traps based on nearby 'id'?
- Wait 'n' hours after FDE triggers alarm and see if that increases the accuracy of the classification
- Remove all pumping traps, these should not be analyzed

## Few Shot Examples w/ Tools (e.g. text and/or graphs)
*General Idea: Allow an agent to use tools for confusing cases / particular cases where they need additional information or context.*
- Control Modulation Behavior. 
- Neighboring traps using 'tag'

# Potential Prompt Improvements
- Handling control modulation behavior (especially for closed failure v healthy behavior)
     > If after modulation the temperature decreases but stabilized with a 10C+ differential, it's not a failure
     > Closed failure behavior = after a step change downward, the temperatures are driving downward (even if there are oscillations, look at the rolling average of the temperatures)
     > Failure behavior (unknown type w/ low confidence) = after a step change downward, there are noisy temperature oscillations (as opposed to repeated patterns) with the condensate side becoming higher than the steam side on occasion
     > Difference b/w failure patterns and healthy patterns. A tricky example is `260000596` which has a downward steam temp trend but shows sawtooth patterns and themal coupling...Do modulations have an ~median steam trap temp after the step change?
     > AFter the step change downward, does the temperatures have a ~steady state mean value or are they driving downward `250005404`?
- Replace the term "chattering" / "sticky" with more precise and physcially meaningful terms.
- Clarify how to compare with previous patterns.
- Closed failures = steam trap closed and/or blocked by debris (so it doesn't label as unknown)
- Repeat critical rules (Test this)


# Potential AI Agent System Improvements
- Have a state/history for each steam trap analyzed. (e.g. putting borderline traps on a 'watch list' to be reviewed periodically). 
     > Test this by analyzing units that are put on the 'watch list' a few days later to see the impact. (e.g. 250004579 is showing early signs of a failure that continue to emerge)
- Subagents that handle particularly difficult cases such as control modulation behavior
- Implement skills using the newest version of Pydantic AI --- to separate some key logic (as oppoesd to putting behind tools)

# Ideas for Improving Agent Output; Reliant on Spirax Changes
- Pics of trap at install time
- Require isntaller to have correct metadata at install time
- Installer hand written notes on installation
- Allow end customer to add notes about site, system, and/or individual traps
- Keeping persistent history of AI Agent outputs / decisions / feedback from SMEs
