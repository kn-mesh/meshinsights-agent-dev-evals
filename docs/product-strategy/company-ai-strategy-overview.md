# Mesh AI Agent Offerings Strategy Overview

## Strategic Point Of View

Mesh should become the AI Agent Readiness and Continuous Improvement partner for businesses with data from commercial and industrial connected assets. Commercially, this is sold as two offers built from two phases: Agent Launch (one-time) and Agent Improvement (recurring).

The winning strategy is not to become a generic AI Agent platform, production host, or LLM infrastructure wrapper. It is to help customers turn IoT data into trusted operational decisions, prove those decisions can be automated, deploy the first agent responsibly, and keep improving it as real-world cases expose new patterns.

This is Mesh's strongest path to differentiation:

- We understand IoT data, the limits of existing analytics/alarms, and the pain of downstream workflows.
- We can identify agent opportunities valuable enough to justify the journey.
- We can define what good decisions look like — translating SME judgment into labels, benchmarks, evidence packages, action policies, and evals.
- We can build prototype agents quickly on real-world data, proving feasibility.
- We can turn pilot and production feedback into better benchmarks, better agents, and safer update recommendations.

Every reliable agent depends on one loop: define the decision, benchmark it, build the agent, learn from live results, raise the standard. Whoever runs that loop controls agent quality. Mesh should own the loop and let the platforms fight over the infrastructure.

The practical handoff from Mesh's loop into production should be a **portable agent package**: a versioned artifact that describes the trigger contract, evidence recipe, prompt/assets, model configuration, output schema, action policy, eval results, known limitations, and feedback schema. **MeshInsights Benchmark Studio** (Benchmark Studio for short) should be where the labeled evidence and benchmarks behind these packages are created, versioned, and improved; **MeshInsights Agent Workbench** (Agent Workbench for short) should develop and evaluate agent variants against them; and Microsoft Foundry, a customer platform, or another approved runtime should be where the package runs when it is time for pilot or production.

## The Strategic Opening

The AI Agent market is immature but advancing quickly (more quickly outside of IoT due to complexity). Customers are interested but often don't know where agents apply, which use cases are feasible, or what readiness is required before building.

Most connected-product businesses have useful data but lack the labeled examples, benchmarks, feedback loops, and decision standards needed to make agents reliable. This is a gap rooted in both the complexity of IoT data and immature internal capability to turn data into automated decisions.

Customers need a partner who can make agents practical in their domain without asking them to surrender control of the systems, data, runtime, and IP that may become core to their operating model. Mesh can create momentum through a guided first-agent journey while staying aligned with the customer's long-term desire to own production AI capability.

The market will keep making generic agent infrastructure easier. It will not automatically solve the customer-specific work of defining what a good connected-system decision looks like, proving it against real evidence, and improving the decision standard as new cases appear.

## Microsoft Ecosystem Strategy

Microsoft should be the first ecosystem partner Mesh actively validates, not merely one platform option. Commercially, Mesh needs more deal flow than direct sales can create, and Microsoft needs credible partners who can turn connected-asset customers (OEMs and operators) into successful agent workloads that consume the Microsoft ecosystem. Technically, Mesh should not carry the burden of building and maintaining rapidly evolving AI Agent Platform infrastructure.

The pitch is simple: many commercial and industrial customers are not ready for agents. Microsoft provides production-grade cloud, edge, data, identity, governance, model, marketplace, and agent platform capabilities — but it lacks the domain breadth and FDE capacity to do the readiness work for every connected-system use case. Mesh fills that gap: the partner that gets customers with IoT data ready for Microsoft's agent ecosystem.

The ecosystem split should stay pragmatic:

- Connected-product workflows: validate Microsoft Foundry Agent Service as the preferred agent runtime path.
- Operator and connected-operations opportunities: validate Azure IoT Operations as the first edge/OT path, connected into the broader Azure, Fabric, and Foundry ecosystem.
- Where Microsoft services aren't yet shaped for connected-system readiness, Mesh may need adapters, templates, marketplace offers, or a thin shim so our agent packages can run in pilot and production.
- Connected-product OEMs may already have IoT, data, service, and workflow platforms. Keep readiness outputs Microsoft-compatible, but don't force a Microsoft runtime when it would block a credible customer-owned production path.

The June 2026 Spirax Foundry Hosted Agent prototype supports this split. It shows that a single validated MeshInsights-style pipeline version can be translated into a compact Foundry Hosted Agent for a code-first pilot without carrying the full MeshInsights runtime. That should be treated as a credible Microsoft pilot pattern, not as a reason to make Hosted Agents the source of truth for agent design or to push the full MeshInsights Platform into Foundry.

Mesh should not compete with Microsoft on generic agent runtime, token resale, model hosting, observability, cloud infrastructure, identity, or governance. Let Azure consumption flow through the customer's Microsoft relationship while Mesh monetizes readiness work, FDE delivery, connected-system accelerators, implementation adapters, and the continuous improvement loop.

The preferred deployment motion is customer-tenant first: a marketplace (or equivalent) deploy-to-customer-tenant offer where the customer owns the Azure subscription, security posture, data boundary, infrastructure costs, and production runtime, while Mesh gets the access needed to implement, support, and improve the agent. This reduces enterprise IT objections, keeps Mesh out of hyperscaler infrastructure and token costs, and makes Microsoft's compliance posture part of the sales motion.

## The Core Strategic Choice

Mesh should concentrate differentiation in AI Agent Readiness and Continuous Improvement. That means being excellent at:

- Economic qualification of first-agent use cases.
- Evidence package generation from connected-system data.
- SME/FDE review workflows and labeling discipline.
- Benchmark creation, versioning, and expansion.
- Prototype agent development and evaluation.
- Pilot design that tests real operational value without pretending to be full production.
- Production feedback capture, failure analysis, and regression evals against growing benchmarks.
- An opinionated view of the enabling tech stack (agent platforms, harnesses, etc.).
- Portable agent packages and update packages that a customer, partner, Microsoft, or Mesh operations team can safely deploy.

Mesh should participate in pilot and production deployment where needed, especially near term — but positioned as enablement and operations support around a well-understood platform, not as a strategic claim that Mesh must host the agent.

The resulting commercial posture: **Agent Launch** takes a value-qualified use case through readiness and a piloted live launch, producing a working production agent the customer owns. **Agent Improvement** keeps it accurate, cost-effective, and aligned with changing field reality and technical advancements in LLMs and agent tooling — the recurring anchor. Readiness, piloted operation, and the improvement loop all still happen; they are folded into two phases rather than sold as separate packages.

Detailed packaging is maintained separately. This overview explains why that
shape is right.

## Where Mesh Should Not Overextend

Mesh should not center the business on areas that hyperscalers, AI labs, enterprise workflow platforms, data platforms, or customer IT organizations are likely to own:

- Proprietary production AI Agent hosting.
- Generic agent runtime, orchestration, or observability.
- LLM inference resale as cost-plus margin.
- Broad enterprise AI platform replacement.
- Customer data governance and security ownership beyond what delivery requires.
- Black-box agents customers cannot inspect, understand, or eventually operate.
- Narrow agent silos that block broader multi-agent capability.

This does not mean avoiding production responsibility — customers will often need Mesh to deploy, monitor, triage, release updates, and operate early solutions. But production hosting and operations are not packaged offers: the agent runs in the customer's environment by default, and Mesh- or partner-run production operations are a separately scoped exception, not the source of strategic control.

Production should generally run on a Mesh-prioritized, Microsoft, partner, or customer-developed platform, with Microsoft validated first and pragmatism when credible customers bring their own environment. MeshInsights Platform can bridge readiness, pilot, and simple early production use cases while the third-party platform path matures (short-term option only, we don't want to compete here).

## Why Agent Improvement Is Defensible

AI Agents for connected systems are never finished. Their value depends on handling new assets, operating conditions, failure modes, service policies, sensor configurations, customer expectations, and model capabilities. The first deployed agent is the beginning of a learning system, which makes Agent Improvement (the continuous improvement loop) more defensible than hosting:

- Benchmarks become customer-specific strategic assets, and feedback loops compound knowledge of the customer's assets and workflows.
- SME/FDE review turns field reality into measurable decision quality, and regression evals make improvement safe and visible.
- Customers can own the production agent and still need Mesh to keep improving it — no customer has roles, current or planned, responsible for continuous agent readiness and improvement.

Mesh should not rely on secrecy around the customer's agent as the moat. Customers should understand the agent package: trigger inputs, evidence recipe, prompts, tools, model choices, output schema, action policy, eval results, feedback schema, and known limitations. Transparency reduces customer risk and increases trust. The packaging bakes this in: the customer owns the agent, the benchmark, and the labeled data, and runs the agent in their own environment.

The center of gravity is Mesh's stewardship of benchmark operations and the agent iteration loop: the customer owns the agent and benchmark data; Mesh owns the operating discipline around them — benchmark versioning, slice design, inclusion criteria, eval harness configuration, and the continuous cycle of agent variant development and evaluation. A customer can take a transparent agent package and leave; what's hard to recreate is the R&D cycle of iterating on agents against evals with the surrounding expertise, tooling, and internal automation.

The agent technology stack is changing quickly — new models, tooling patterns, prompting methods, eval approaches, harnesses, and cost/performance techniques. Most connected-product businesses have no team dedicated to staying at that edge. Their analytics, data science, or ML teams are typically optimized for ad-hoc analysis, dashboards, alerts, predictive models, or RAG chatbots — not for automating decisions from complex multivariate sensor data.

Mesh's advantage compounds across customers and use cases: customer data, labels, and benchmarks stay customer-specific, while Mesh reuses and improves its methods for data preparation, evidence packaging, prompt and tool design, benchmark design, eval harnesses, confidence thresholds, failure-mode analysis, model selection, runtime-adapter patterns, and improvement workflows. Benchmark Studio should make benchmark operations repeatable, while Agent Workbench lets Mesh develop and test agent variants quickly, compare quality and cost, and package validated improvements back to the production owner.

Codifying this learning into automation is a core part of the FDE job, not a side project. FDEs are expected to continuously build internal agents, skills, and loops that automate today's manual work: labeling setup, benchmark expansion, eval execution, variant testing, feedback review, and update packaging. Every engagement should leave the delivery system more automated than it found it — this is how per-engagement capacity grows without linear headcount, and how Mesh stays ahead of customers and platforms internalizing the loop.

Some customers may eventually internalize mature agents or parts of the loop. Mesh's strongest long-term fit is high-value agents, expensive agents (either due to scale or per run costs), complex use cases, new agent families, changing products, new sensor/data environments, evolving workflows, and customers who want ongoing improvement without building a full internal applied-AI capability.

Agent Improvement should be sold as an operating discipline structured around change triggers, not maintenance activity. The recurring fee must be defensible even when the agent is stable — the customer pays for guaranteed response to change, not busywork. Default commitments:

- Model churn coverage: every major model release evaluated against the customer's benchmarks within a defined window, with a cost/performance recommendation.
- Regression insurance: periodic evaluation of production agents against benchmarks to catch accuracy drift.
- Feedback-to-benchmark conversion: real-world cases reviewed, labeled, and added to benchmarks at a defined volume and cadence.
- Periodic decision-standard review with the customer's SMEs to confirm label schema, action policy, and benchmark slices still reflect operational reality.

Fleet evolution coverage (new asset variants, sensor configurations, firmware changes, solution modifications) should be scoped add-on work, not a default commitment — the effort varies too much to absorb into a base fee.

## Customer Focus

Mesh should stay focused on AI Agents that rely on IoT data from commercial and industrial assets. Generic enterprise AI use cases dilute the domain advantage (e.g. building agents not dependent on IoT data is not where we differentiate or will focus)

The near-term beachhead is connected-product businesses: OEMs or product companies that sell, service, support, monitor, or monetize connected equipment in the field — where Mesh's IoT services credibility, customer context, data familiarity, and relationships are most directly relevant.

The initial agent family focus:

- **Early Warning Agents:** detect degradation, failure risk, abnormal behavior, and conditions likely to drive support, service, warranty, uptime, or customer outcome problems.
- **Service Resolution Agents:** recommend what should happen next after an alert, issue, anomaly, complaint, or service case.

These sit closest to Mesh's connected-product experience and tie agent value to service cost, expert leverage, avoided dispatches, faster resolution, warranty exposure, retention, and installed-base differentiation.

Operators of connected assets, systems, or facilities are a credible expansion segment, especially where the outcome is closer to the customer's own P&L — but near-term positioning, demos, sales material, and proof points should focus on connected-product businesses first, with the journey reusable across both groups. The Microsoft channel may pull Mesh toward operator-led opportunities faster than the beachhead suggests; that's acceptable if the economics are strong and the use case fits the same readiness-to-benchmark-to-agent-to-feedback loop.

- Centering our offering on AI Agent Readiness and Continuous Improvements with MSFT customers makes the solution delivery very similar b/w connected solutions, reducing the risk of accepting operators as customers.

Near-term targeting should prioritize opportunities with a compelling first-year value case, accessible data, available SMEs, a clear operational action, and a credible path to pilot and production ownership.

## Product Strategy

Near-term product investment should support a productized FDE practice through two connected products: **MeshInsights Benchmark Studio**, for evidence review, labeling, benchmark creation, versioning, expansion, and feedback conversion; and **MeshInsights Agent Workbench**, for agent R&D, evaluation, comparison, and packaging. Use **Benchmark Studio** and **Agent Workbench** as the short product names after their first references. Neither product owns the production agent runtime.

The broader MeshInsights platform should move away from being the default production deployment platform. Product direction should concentrate each product on what Mesh needs to own:

- Benchmark Studio: access connected-system data for evidence packages; provide usable FDE/SME review and labeling interfaces; create, version, and expand benchmarks; and capture pilot and production feedback through explicit hooks.
- Agent Workbench: run connected-product agent variants against published benchmark versions; compare model, prompt, evidence, tool, and harness choices; execute regression evals; and create portable agent package manifests and tested update packages for the production owner.
- Product integration: preserve published benchmark identity and frozen evidence as the read-only handoff from Benchmark Studio into Agent Workbench.

FDE capacity is the real constraint, and it differs by phase: during Agent Launch (readiness plus piloted live operation), an FDE can handle at most two concurrent projects (current estimate) — this work is intensive in use-case learning, labeling setup, leading SME label discussions, benchmark creation, and prototype iteration. In Agent Improvement, the burden is much lighter: five or more concurrent engagements per FDE is feasible. Launch capacity is therefore the near-term bottleneck on how many first agents move through the journey, while Agent Improvement scales with far better leverage. The two levers for growing capacity are the FDE automation mandate and a deliberate hiring pipeline; the strategy only scales if Benchmark Studio, Agent Workbench, and FDE-built automation keep reducing the manual burden.

The readiness environment should stay optimized for speed, flexibility, and measurement — deliberately separate from the production platform, as long as Mesh can package validated improvements into the selected runtime. Build integrations and adapters where they connect readiness work to production platforms; avoid overbuilding generic runtime features the market will provide.

Benchmark Studio is the benchmark-operations and eval-readiness environment; Agent Workbench is the agent R&D and eval-execution environment; the portable agent package is the handoff artifact; and the production runtime lives in the customer's Microsoft tenant or another approved customer runtime.

## Commercial Strategy

The commercial model is two named offers built from two phases. **Build & Improve** is the lead offer — Mesh launches the agent (Agent Launch, one-time fixed fee against a defined scope) and keeps it accurate and current (Agent Improvement, annual subscription per production agent); the customer operates it in their own environment. **Build & Handoff** is the exception, for customers with the team and intent to operate and improve the agent themselves after launch.

Agent Launch is the first paid step in either offer. There is no separate paid workshop or pilot — discovery and proof are folded into Launch, and qualification happens in the sales process. Qualification requires both a value floor (a use case worth $200K+ per year to the customer; we should aim for $500K+/year) and a fundable budget (roughly $150K+ to put to work), with a real business owner and serious intent to launch. The customer should understand the decision being automated, the action it influences, the rough value pool, the data and SME burden, and the cost of the full offer.

Inside Agent Launch, the agent still earns trust the way the journey phases describe: roughly a month of readiness work proves the decision is measurable and the prototype performs, then the agent is built and run in a pilot manner for roughly two to three months, with the feedback loop between agent outputs and the labeling/benchmarking platform making improvement visible from the start. Production hardening happens in the transition into Agent Improvement as the agent shifts to operating in a production manner. The agent runs on the customer's platform from launch onward, so nothing is replatformed between launch and improvement.

Production hosting and operations are not packaged. The agent runs in the customer's environment by default; Mesh- or partner-run production operations are a separately scoped exception given the vast differences in scope, skillset, and outcomes.

Long-tail revenue per agent comes from Agent Improvement, where recurring value ties to better accuracy, broader coverage, lower cost per successful run, safer updates, and higher operational impact. The per-agent rate scales down as a customer adds agent families. Per-customer growth comes from expansion: each additional agent re-enters Agent Launch with reuse lowering incremental build effort. Near-term pricing is provisional for the first ~10 customers and prioritizes traction, proof points, and learning; figures live in the MeshInsights Pricing Sheet.

The Microsoft partnership is a primary commercial experiment. Mesh needs validated customers and recommendations from Microsoft to prove credibility; Microsoft has the reach and the incentive to create LLM API consumption. Arm Microsoft sellers with a crisp story: Microsoft has the platform, Mesh has the connected-system readiness practice that gets customers to real agent workloads which drive AI spend.

## Agent Family Marketing

The customer journey is the delivery reality, but buyers need to understand production value. Mesh should market representative agent families that connect readiness work to business outcomes:

- Early Warning Agents: detect degradation, failure risk, and abnormal behavior.
- Service Resolution Agents: recommend what should happen next after an alert or issue.
- Performance Management Agents: identify waste, inefficiency, and capacity gaps.
- Aftermarket Growth Agents: surface service, parts, replacement, or upsell opportunities.
- Customer Health Agents: identify account risk, misuse, unresolved issues, or outcome gaps.

Early Warning and Service Resolution are the first marketing and delivery focus; the other families stay in the portfolio story without diluting near-term demos, discovery, proof points, or tooling focus. Pricing should not vary by agent family yet — complexity is driven by customer data, evidence requirements, SME availability, workflow design, action policy, and production ownership, not by family name.

## Strategic Guardrails

- Stay focused on IoT-data-dependent use cases / agents.
- Require value qualification before Agent Launch: a use-case value floor ($200K+/year, aim $500K+) plus a fundable budget (~$150K+), a real owner, and serious intent — no paid workshops or pilots as entry points.
- Use Benchmark Studio for evidence review, labeling, benchmark operations, feedback conversion, and eval readiness; use Agent Workbench for agent R&D, eval execution, comparison, and update packaging; use neither for production hosting.
- Validate Microsoft as the first ecosystem path (Foundry Agent Service for agent workflows; Azure IoT Operations for operator paths) while remaining customer-platform tolerant.
- No black-box agents: the agent package should explain trigger inputs, evidence recipe, prompts, tool assumptions, model choices, output schema, eval results, action policy, feedback schema, and known limitations.
- Keep production hosting and operations out of the packaged offers; Mesh- or partner-run production operations are a separately scoped exception, distinct from Agent Improvement in scope and pricing.
- Sell Agent Improvement as change-trigger commitments (model churn coverage, regression insurance, feedback-to-benchmark conversion, decision-standard review), with fleet evolution as scoped add-on work.
- Treat benchmarks and agents as living assets, and FDE-built automation of the loop as a core part of the FDE job — every engagement leaves the delivery system more automated.

## Strategic Risks

**Market education.** The market is immature (tech and customer success stories). The readiness problem may be harder and slower than customers expect — many prospects lack labels, benchmarks, or SME capacity, and budget is likely not allocated to this today. Mesh must educate without turning the entry point into unfocused consulting.

**FDE capacity may constrain growth before demand does.** The 2-project readiness/pilot cap limits how many first agents can move at once, even with CI's better leverage. Mesh needs FDE-built automation, repeatable delivery patterns, careful package scoping, and a hiring pipeline before assuming the model scales.

**The first-agent path is a significant commitment.** The qualification gate must hold so customers only enter Agent Launch when the value case and budget justify the full offer. Finding use cases that justify the launch fee plus the recurring subscription will be a challenge, especially with OEMs.

**Recurring revenue will lag** if too few agents reach production and Agent Improvement. Don't build a business model assuming rapid production-agent scale before the market is ready.

**The production platform path is unsettled.** Microsoft may become the center of gravity, but customer-developed and other third-party platforms will matter, much like the IoT platform ecosystem.

**The Microsoft partnership may not produce deal flow** Pressure-test the strategy with Microsoft quickly, especially with stakeholders who understand connected products/operations and the FDE gap behind agent deployment.

# Technical Solution Focus

The technical solution should be grounded in the full connected-system agent journey: identify candidate operational decisions, reconstruct the evidence available at the decision point, turn expert judgment into benchmarks, develop and evaluate agent variants, deploy the validated agent into the customer's runtime, and feed production outcomes back into the benchmark loop.

The common shape is **batch evaluation of a unit of analysis at a point in time**. A process chooses a unit, fixes the decision timestamp, retrieves historical context up to that point, and produces a structured decision about whether action should be taken. This is the connective tissue across readiness, evals, pilot, production, and continuous improvement.

- A `unit` is the atomic subject being evaluated: a device, asset, system, site, process line, batch, case, or another use-case-defined subject.
- A `decision_timestamp` is the as-of moment the system is simulating or acting from. It may come from an alarm, scheduled review, batch end, escalation, production run, or workflow event, and it usually becomes the default end date for retrieval.
- An `example` is the durable pairing of the unit, timestamp, and any extra discriminator needed when multiple source events share the same unit/time.

This is not just a labeling model. It is the contract that lets Mesh move the same use case through the whole lifecycle:

- Candidate discovery jobs scan alarms, scheduled workflows, source-system events, run lists, or historical data to identify units and decision timestamps worth reviewing or acting on.
- Evidence-building pipelines retrieve source data for each unit/timestamp pair, apply lookback windows and domain transforms, and produce versioned evidence packages.
- SME/FDE review converts evidence into labels, rubrics, inclusion guidance, and benchmark versions.
- Agent Workbench runners execute agent variants against the same evidence contract, comparing quality, cost, confidence, failure modes, and action policy fit across benchmark slices.
- Production decision agents run in the customer's chosen runtime, triggered by the same kinds of unit/timestamp events, using the validated evidence recipe to produce structured recommendations or actions.
- Feedback and improvement jobs ingest live outcomes, missed cases, SME overrides, user feedback, and model/runtime changes, then promote selected cases back into review and regression benchmarks.

Spirax is a useful reference example from early customer work, not the basis for the strategy: in FDE-generated steam-trap alarms, the unit is the trap/sensor installation, the timestamp is the alarm time (which currently triggers their legacy SME review workflow), evidence is historical temperature and installation context up to the alarm (1 year of data leading to the alarm), and the agent decision is failure classification plus root cause. PHD is another reference example showing the same pattern: the unit is an HVAC system, a batch run retrieves the historical window (90 days), the pipeline ingests telemetry, validates cycle quality, and produces threshold decisions for support review or update. Both cases illustrate the broader point that connected-system agent work depends on retrieving data in batches which then allows the data to be processed for both data labeling workflows and AI Agents.

The background agent/pipeline layer is therefore first-class, not incidental. Mesh should expect to build use-case-specific workers for candidate generation, source retrieval, normalization, evidence packaging, benchmark eval execution, production feedback ingestion, failure analysis, and update-package preparation.

This should shape the portable agent package. It should not just describe a prompt and model; it should describe the trigger contract, unit identity, decision timestamp semantics, evidence recipe, source/tool assumptions, output schema, action policy, benchmark results, known limitations, and feedback schema. Production systems should be able to trigger the same kind of example that Mesh used during readiness and evals.

The implementation guardrail is simple: if a feature cannot be explained as helping Mesh discover, reconstruct, label, evaluate, deploy, monitor, or improve decisions about units at decision points, it is probably outside the solution focus. If code starts treating examples as generic objects, evals as disconnected prompt tests, or production agents as isolated chat workflows, it is drifting away from the product Mesh needs.
