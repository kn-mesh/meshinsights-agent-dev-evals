# Agent Workbench Development Backlog

## Post-MVP Features



### Production Runtime Adapters

**Status:** Post-MVP.

Validate translation of the portable package into Microsoft Foundry first,
followed by other approved customer runtimes as required. Adapters should map
the package's trigger, evidence, model, tool, output, action, and feedback
contracts into the target environment without requiring Agent Workbench or the
full MeshInsights runtime to become the production host.


### Portable Agent Package

**Status:** Post-MVP; strategic handoff artifact with no implemented manifest.

Define a versioned, inspectable package that promotes a validated agent version
from Agent Workbench into a customer-owned pilot or production runtime. The
package is a deployment handoff contract, not a generic production runtime or
hosting platform.

At minimum, it should identify:

- package and agent-version identity;
- trigger contract, unit identity, decision-timestamp semantics, and example
  discriminator;
- evidence recipe and source/tool assumptions;
- prompt, skill, tool, and other agent assets with integrity hashes;
- model/runtime configuration and supported override boundaries;
- structured output schema aligned with configured evaluation fields;
- action policy, confidence/escalation behavior, and safety constraints;
- supporting published benchmark version and selected promoted eval results;
- known limitations and supported benchmark or operating slices; and
- production-feedback schema and routing contract for Benchmark Studio's
  feedback workflow.

The package should be portable across Microsoft Foundry and other approved
customer runtimes where practical. Runtime adapters may translate the package,
but must not become the source of truth for agent design.

The detailed plan must resolve manifest format, artifact layout, signing,
provenance, compatibility, embedded versus referenced assets, promotion gates,
approval history, rollback linkage, and update-package semantics.
