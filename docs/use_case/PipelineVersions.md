# What's common between all pipelines?
- Same goal and structured ouputs from the AI models

# v0_0.ppln
- Created this after writing a few v1_x versions and noticed that gemini 3 flash was the best model for this use case, even better than gemini 3.1 pro.
- Uses the same image inputs as the v1_1.ppln pipeline, but with a much simpler prompt (describing the necessary background such as the sensors, the goal of the pipeline, and the output schema)
- *hypothesis:* the prompt was too rigid for smarter models while the smaller model simply followed the rules in the prompt...expecting that with less rigid guidance, the stronger models will perform better than the smaller models --- however, I'm not sure if this will create absolute higher performance relative to the other pipelines...

# v0_1.ppln
- Same pipeline shape and image inputs as the current v0_0.ppln pipeline.
- Slighly more detailed prompt vs v0_0.ppln, but still much simpler than the v1_x prompts.

# v1_0.ppln
- Copy/paste the UseCase.md file from late March 2026 into the system message without trying to `prompt engineer` it.

# v1_0_agent.ppln
- Same inputs as v1_0.ppln, but with a tool call for custom temperature graphs based on date ranges chosen by the agent.

# v1_2.ppln
- Generates a graphs for raw temps and temp delta for 7, 30, 365 days leading to a failure.
- Numerous rounds of prompt engineering based on evals and new learnings from Q&A with Spirax SMEs (as outlined in UseCase-v2.md)

# v1_3.ppln
- Same image inputs / user messsage but directly copied/pasted the docs/UseCase-V2.md into the system prompt w/o trying to `prompt engineer` it
