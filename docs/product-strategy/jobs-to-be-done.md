**Jobs To Be Done**
- All this is done by a Mesh FDE

# 1. Create a new project repo
- Each project / use case has it's own repo which will contain multiple versions of agents with results from their evals.
- The project always starts with the same core agent pipeline and agent workbench libraries. These are the building blocks for building and evaluating agents. 
- Each project will have a directory structure (template) where the use case specific code is written. Each 

# 2. Port Lightweight Agent Pipeline From 'Benchmark Studio' into this codebase
- A lightweight pipeline is created for the Benchmark Studio to create the evidence packages for each example in the benchmark. 
- Porting this will provide: (1) Access to azure blob storage for retrieval of evidence for each example in the benchmarks (2) Base for each ai agent pipeline that will be developed, evaluated and evolved in this codebase.

# 3. Build First Agent Version
- Build a lighweight agent making key design decision such as defining the structured output of the agent which can directly be measured against the benchmarks.

# 4. Build the evaluation harness using the core primitives
- The evaluation harness needs to run the agent against the benchmark and write the critical info/stats of the eval run to enable the agent to hill climb on the benchmarks.

# 5. Evaluate the First Agent Version
- Run the evals using a few selected models / configs to get a feel for the accuracy of the agent

# 6. Inspect the results of the evals
- Have both a mechanism for (1) AI Coding Agents (Codex) and (2) Human Developer; to review the agent results, dig into specific examples that were wrong including viewing the raw input to the model and the output.

# 7. Improve the agent version and/or try a new strategy 
- Build, evaluation, improve, repeat...

# 8. Save agent version and benchmarks
- Over time some agent versions will achieve meaningful progress and the agent version and benchmark along with the evals need to be versioned. This is how we show progress and continue to improve. 