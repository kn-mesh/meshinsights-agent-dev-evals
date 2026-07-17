# AI Smoke Tests

Two smoke tests validate the `pydantic-ai` backend end-to-end by sending real LLM requests, verifying structured output, and comparing traced inputs in Logfire.

## Providers

Each test is parametrized across three providers:

- `azure:gpt-5-mini`
- `azure:claude-sonnet-4-5`
- `google:gemini-3.1-flash-lite-preview`

## Prerequisites

1. A `.env` file in the project root with API credentials for each provider you intend to run.
2. A `.logfire` directory in the project root with valid Logfire project credentials.
3. The following environment variables (via `.env` or shell):
   - **Provider keys** for whichever providers you run (e.g. Azure OpenAI, Azure Foundry, Google Gemini).
   - **Azure Claude** (`azure:claude-*`) requires `ANTHROPIC_FOUNDRY_API_KEY` + `ANTHROPIC_FOUNDRY_RESOURCE` (or `ANTHROPIC_FOUNDRY_BASE_URL`).
   - **Google Gemini** (`google:*`) requires `GOOGLE_API_KEY` or `GEMINI_API_KEY`.
   - `LOGFIRE_READ_TOKEN` — required for post-run trace validation against Logfire.
   - `PYDANTIC_AI_REASONING_EFFORT` — optional, defaults to `low`.

## Running Tests

**All providers:**

```
uv run -m pytest tests/core/ai/workflow/test_pydantic_ai_workflow.py -s
uv run -m pytest tests/core/ai/agent/test_pydantic_ai_agent.py -s
```

**Single provider:**

```
uv run -m pytest tests/core/ai/workflow/test_pydantic_ai_workflow.py -s --pydantic-ai-provider azure:gpt-5-mini
uv run -m pytest tests/core/ai/agent/test_pydantic_ai_agent.py -s --pydantic-ai-provider azure:gpt-5-mini
```

## Workflow Test

**File:** `tests/core/ai/workflow/test_pydantic_ai_workflow.py`

Validates the `AIWorkflowMixin` (single request, no tools). A simulated one-month hourly temperature dataset is rendered to a graph image and sent as a multimodal user message. The LLM classifies the pattern shape (expected: `sine_wave`) and returns structured output. After execution the test queries Logfire to verify that the exact system prompt, user text, and user image sent to the provider match the expected values.

## Agent Test

**File:** `tests/core/ai/agent/test_pydantic_ai_agent.py`

Validates the `AIAgentMixin` (multi-turn with tools). Extends the workflow use case by adding a humidity classification task that requires the LLM to call a tool (`get_last_7_day_humidity_graph`) before responding. The tool returns a separate graph image of step-shaped humidity data. The test verifies structured output for both classifications (temperature: `sine_wave`, humidity: `step`), confirms the tool was called, and validates all traced inputs and tool images against Logfire.
