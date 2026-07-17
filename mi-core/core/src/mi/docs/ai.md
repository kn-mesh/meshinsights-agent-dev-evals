# AI Integration

The `mi.ai` package provides provider-agnostic AI processors for data pipelines. It supports multiple providers (Anthropic, Azure OpenAI, Azure Foundry, OpenRouter) through a thin abstraction layer that decouples processor code from any specific SDK.

## Installation

AI support is included with the core package:

```bash
uv add mi-core
```

Set the following environment variables for your providers:

```bash
# Anthropic (direct API)
ANTHROPIC_API_KEY=""
ANTHROPIC_BASE_URL=""  # Optional: point anthropic:* models to Azure-hosted Anthropic endpoint

# Azure OpenAI (GPT models)
AZURE_OPENAI_ENDPOINT=""
AZURE_OPENAI_API_KEY=""
OPENAI_API_VERSION=2024-12-01-preview

# Azure Foundry (Claude models via Azure)
ANTHROPIC_FOUNDRY_API_KEY=""
ANTHROPIC_FOUNDRY_BASE_URL=""        # or ANTHROPIC_FOUNDRY_RESOURCE (mutually exclusive)

# OpenRouter
OPENROUTER_API_KEY=""
```

## Two Patterns: Workflows vs Agents

| Pattern | Use Case | Features |
|---------|----------|----------|
| **Workflow** | Single LLM call | Structured output, simple prompts |
| **Agent** | Multi-turn reasoning | Tool use, iterative analysis |

### When to Use Workflows

- Classification tasks
- Data extraction
- Simple analysis
- One-shot generation

### When to Use Agents

- Complex reasoning requiring multiple steps
- Tasks needing access to external data via tools
- Iterative refinement
- Decision-making with tool-based validation

## Quick Start

### Workflow Example

```python
from mi.ai import AIWorkflowMixin, AIProcessorConfig, UserMessage
from mi.core import BaseProcessor
from pydantic import BaseModel

class SentimentResult(BaseModel):
    sentiment: str  # "positive", "negative", "neutral"
    confidence: float
    reasoning: str

class SentimentAnalyzer(AIWorkflowMixin[MyDataObject, SentimentResult], BaseProcessor):
    output_schema = SentimentResult
    system_prompt = "You are a sentiment analyzer. Analyze the sentiment of the given text."

    def _build_user_message(self, data_object):
        return UserMessage().add_text(data_object.text)

# Instantiate with config
config = AIProcessorConfig(model="anthropic:claude-sonnet-4-5")
analyzer = SentimentAnalyzer(config)
```

### Agent Example

```python
from mi.ai import AIAgentMixin, AIProcessorConfig, UserMessage, ToolContext, ai_tool
from mi.core import BaseProcessor
from pydantic import BaseModel

class AnalysisResult(BaseModel):
    summary: str
    recommendations: list[str]

@ai_tool(name="get_records")
def get_records(ctx: ToolContext, limit: int = 10) -> str:
    """Get sample records from the dataset."""
    records = ctx.data_object.records[:limit]
    return str(records)

class DataAnalysisAgent(AIAgentMixin[MyDataObject, AnalysisResult], BaseProcessor):
    output_schema = AnalysisResult
    system_prompt = "You are a data analyst. Use tools to gather data and provide analysis."

    def _build_user_message(self, data_object):
        return UserMessage().add_text("Analyze the dataset.")

    def _build_tools(self, data_object):
        return [get_records]

# Instantiate with config
config = AIProcessorConfig(model="azure:gpt-5", max_turns=15)
agent = DataAnalysisAgent(config)
```

## Configuration

### AIProcessorConfig

All AI settings are provided via `AIProcessorConfig`:

```python
from mi.ai import AIProcessorConfig, ReasoningEffort

config = AIProcessorConfig(
    model="anthropic:claude-sonnet-4-5",  # Required: provider:model
    backend="auto",                        # Optional: auto (resolves to pydantic_ai)
    reasoning_effort=ReasoningEffort.MEDIUM,  # Optional, default: MEDIUM
    max_turns=10,                          # Optional, default: 10 (agents only)
    attach_usage=True,                     # Optional, default: True
    attach_response=True,                  # Optional, default: True
    timeout=120.0,                         # Optional: request timeout in seconds
    retries=3,                             # Optional, default: 3
    output_retries=None,                   # Optional: retries for output validation
    tool_timeout=30.0,                     # Optional: per-tool timeout in seconds
    provider_options={},                   # Optional: provider-specific (e.g. Azure deployment)
    backend_options={},                    # Optional: backend-specific adapter options
)
```

### Model Identifiers

Use `provider:model` format:

**Anthropic (direct API):**
- `anthropic:claude-sonnet-4-5`
- `anthropic:claude-opus-4-5`

**Azure OpenAI:**
- `azure:gpt-5`
- `azure:gpt-5-mini`

**Azure Foundry (Claude via Azure):**
- `azure:claude-sonnet-4-5`
- `azure:claude-opus-4-5`

**OpenRouter:**
- `openrouter:google/gemini-3-flash-preview`

> **Note:** Direct OpenAI API access (`openai:*`) is not supported. Use `azure:gpt-*` for GPT models via Azure OpenAI, or `openrouter:*` for OpenAI models via OpenRouter.

### Custom Providers and Models

Register custom providers and models at application startup:

```python
from mi.ai import register_provider, register_model

register_provider("my-custom-provider")
register_model("my-custom-provider:my-model")
```

### Backend and Provider Mapping

All AI execution currently routes through the `pydantic_ai` backend (selected by default via `backend="auto"`). The backend resolves each `provider:model` string to a concrete SDK client based on provider-specific rules.

#### Provider Resolution Summary

| User-facing model | Runtime resolution | Credentials |
|---|---|---|
| `anthropic:claude-*` | pydantic-ai string `"anthropic:claude-*"` | `ANTHROPIC_API_KEY` |
| `azure:gpt-*` | pydantic-ai string `"azure:<deployment>"` | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `OPENAI_API_VERSION` |
| `azure:claude-*` | `AnthropicModel` via `AsyncAnthropicFoundry` | `ANTHROPIC_FOUNDRY_API_KEY`, `ANTHROPIC_FOUNDRY_BASE_URL` or `ANTHROPIC_FOUNDRY_RESOURCE` |
| `openrouter:*` | pydantic-ai string `"openrouter:<model>"` | `OPENROUTER_API_KEY` |

#### Azure OpenAI Deployment Naming

For `azure:gpt-*` models, the backend uses the **model name as the deployment name** by default. If your Azure deployment name differs from the model name, override it with `provider_options`:

```python
config = AIProcessorConfig(
    model="azure:gpt-5",
    provider_options={"deployment": "my-custom-deployment"},
)
```

When `deployment` is provided, the backend passes `"azure:<deployment>"` to pydantic-ai instead of `"azure:<model>"`. An empty or `None` deployment value falls back to the model name.

#### Azure Foundry (Claude on Azure)

When you specify `azure:claude-*`, the backend detects the Claude model prefix and routes through Microsoft Azure AI Foundry using the Anthropic SDK's `AsyncAnthropicFoundry` client.

Credentials are resolved automatically by the `anthropic` SDK from environment variables:

- `ANTHROPIC_FOUNDRY_API_KEY` — your Foundry API key.
- `ANTHROPIC_FOUNDRY_BASE_URL` — the full endpoint URL (e.g. `https://kurt-mh0y98po-eastus2.services.ai.azure.com/anthropic`).
- `ANTHROPIC_FOUNDRY_RESOURCE` — just the resource name (e.g. `kurt-mh0y98po-eastus2`); the SDK builds the full URL.

`ANTHROPIC_FOUNDRY_RESOURCE` and `ANTHROPIC_FOUNDRY_BASE_URL` are mutually exclusive — set one or the other, not both.

The `settings_id` for reasoning spec matching preserves the `azure:claude-*` prefix, so Azure Claude models receive Anthropic-style thinking/budget settings rather than OpenAI-style effort settings.

#### Azure-hosted Anthropic via Base URL

As an alternative to the `azure:claude-*` Foundry path, you can point `anthropic:*` models at an Azure-hosted endpoint by setting `ANTHROPIC_BASE_URL`. This lets you use `anthropic:claude-sonnet-4-5` as the model identifier while routing traffic through Azure:

```bash
ANTHROPIC_API_KEY="your-azure-api-key"
ANTHROPIC_BASE_URL="https://your-resource.services.ai.azure.com/anthropic/v1"
```

With this approach the Anthropic SDK handles the connection natively — no Foundry client or `provider_options` are needed. Reasoning specs, settings, and artifact keys all resolve under the `anthropic:*` pattern as usual.

#### OpenAI Direct API

Direct OpenAI API access (`openai:*`) is **not supported** and will not be implemented. All GPT model access is through Azure OpenAI (`azure:gpt-*`). If you need to reach OpenAI-hosted models outside of Azure, use OpenRouter as the provider.

### Reasoning Effort

Controls how much "thinking" the model does:

```python
from mi.ai import ReasoningEffort

ReasoningEffort.LOW     # Quick responses, less reasoning
ReasoningEffort.MEDIUM  # Balanced (default)
ReasoningEffort.HIGH    # Deep reasoning, more tokens
```

Each model has a `ReasoningSpec` that maps effort levels to provider-native values. Built-in specs:

| Pattern | Mode | LOW | MEDIUM | HIGH |
|---------|------|-----|--------|------|
| `anthropic:*` | BUDGET | 1500 tokens | 3000 tokens | 5000 tokens |
| `azure:claude-*` | BUDGET | 1500 tokens | 3000 tokens | 5000 tokens |
| `azure:*` (GPT) | EFFORT | "low" | "medium" | "high" |
| `openrouter:*gemini*` | BUDGET | 1500 tokens | 3000 tokens | 5000 tokens |

> Pattern matching is ordered so that `azure:claude-*` matches before the generic `azure:*` wildcard. This ensures Azure Claude models receive Anthropic-style budget thinking settings, not OpenAI-style effort settings.

Override or register custom specs at startup:

```python
from mi.ai import ReasoningSpec, ReasoningMode, ReasoningEffort, register_reasoning_spec

register_reasoning_spec("azure:gpt-5", ReasoningSpec(
    mode=ReasoningMode.BUDGET,
    efforts={
        ReasoningEffort.LOW: 2000,
        ReasoningEffort.MEDIUM: 8000,
        ReasoningEffort.HIGH: 20000,
    },
    include_thoughts=True,
))
```

If a model matches no spec, reasoning is disabled (mode=NONE). If the requested effort level is missing from a spec's `efforts` dict, the backend treats it as NONE for that request.

## Workflows

Workflows are single LLM calls that return structured output.

### Class Attributes

| Attribute | Required | Description |
|-----------|----------|-------------|
| `output_schema` | Yes | Pydantic model class for structured output |
| `system_prompt` | Yes | System prompt string (or override `_build_system_prompt`) |

### Methods to Implement

| Method | Required | Description |
|--------|----------|-------------|
| `_build_user_message(data_object)` | Yes | Build the user message |
| `_build_system_prompt(data_object)` | No | Override if dynamic system prompt needed |
| `_attach_response(data_object, response)` | No | Override to customize response storage |
| `_attach_usage(data_object, usage)` | No | Override to customize usage storage |

### Basic Example

```python
from mi.ai import AIWorkflowMixin, AIProcessorConfig, UserMessage
from mi.core import BaseProcessor
from pydantic import BaseModel

class ExtractionResult(BaseModel):
    entities: list[str]
    summary: str

class EntityExtractor(AIWorkflowMixin[MyDataObject, ExtractionResult], BaseProcessor):
    output_schema = ExtractionResult
    system_prompt = "Extract named entities from the given text."

    def _build_user_message(self, data_object):
        return UserMessage().add_text(data_object.text)

# Create and use
config = AIProcessorConfig(model="anthropic:claude-sonnet-4-5")
extractor = EntityExtractor(config)
extractor.process(data_object)

# Results are automatically stored as artifacts:
# - {processor}_{model}_response: The structured output
# - {processor}_{model}_usage: Token usage metrics
```

### Multimodal (Images)

```python
import base64
from pathlib import Path

class ChartAnalyzer(AIWorkflowMixin[MyDataObject, ChartAnalysis], BaseProcessor):
    output_schema = ChartAnalysis
    system_prompt = "Analyze charts and extract insights."

    def _build_user_message(self, data_object):
        image_data = base64.b64encode(Path("chart.png").read_bytes()).decode()
        return (
            UserMessage()
            .add_text("Analyze this chart:")
            .add_image(image_data, media_type="image/png")
        )
```

### Using the Builder Pattern

`UserMessage.builder()` returns a `UserMessageBuilder` with a fluent API. Builders are accepted directly by `_build_user_message` — they're resolved automatically:

```python
def _build_user_message(self, data_object):
    return (
        UserMessage.builder()
        .text("Analyze this data:")
        .text(str(data_object.records))
        .image(data_object.chart_b64, media_type="image/png")
        .build()
    )
```

You can also return the builder directly (without calling `.build()`):

```python
def _build_user_message(self, data_object):
    return UserMessage.builder().text(data_object.text)
```

### Dynamic System Prompts

```python
class ContextAwareAnalyzer(AIWorkflowMixin[MyDataObject, Analysis], BaseProcessor):
    output_schema = Analysis

    def _build_system_prompt(self, data_object):
        return f"""You are analyzing data for {data_object.customer_name}.
        Context: {data_object.context}
        Focus on: {data_object.focus_areas}"""

    def _build_user_message(self, data_object):
        return UserMessage().add_text(data_object.text)
```

## Agents

Agents support multi-turn execution with tool use.

### Class Attributes

| Attribute | Required | Description |
|-----------|----------|-------------|
| `output_schema` | Yes | Pydantic model class for structured output |
| `system_prompt` | Yes | System prompt string (or override `_build_system_prompt`) |

### Config Options

| Option | Default | Description |
|--------|---------|-------------|
| `model` | Required | Model identifier |
| `max_turns` | 10 | Maximum agent turns (tool calls) |
| `tool_timeout` | None | Per-tool call timeout in seconds |

### Methods to Implement

| Method | Required | Description |
|--------|----------|-------------|
| `_build_user_message(data_object)` | Yes | Build the user message |
| `_build_tools(data_object)` | Yes | Return tools (list, ToolSet, or ToolSetBuilder) |
| `_build_system_prompt(data_object)` | No | Override if dynamic system prompt needed |
| `_attach_response(data_object, response)` | No | Override to customize response storage |
| `_attach_usage(data_object, usage)` | No | Override to customize usage storage |

### Defining Tools

Tools are defined using `@ai_tool`, `Tool()`, or plain functions. No pydantic-ai imports needed.

**1. Using the `@ai_tool` decorator:**

```python
from mi.ai import ai_tool, ToolContext

@ai_tool(name="get_customer_data")
def get_customer_data(ctx: ToolContext, customer_id: str) -> str:
    """Retrieve customer information by ID."""
    customer = ctx.data_object.customers.get(customer_id)
    return f"Customer {customer_id}: {customer}"
```

**2. Context-aware functions** (auto-detected via `ToolContext` annotation):

```python
from mi.ai import ToolContext

def get_customer_data(ctx: ToolContext, customer_id: str) -> str:
    """Retrieve customer information by ID."""
    customer = ctx.data_object.customers.get(customer_id)
    return f"Customer {customer_id}: {customer}"
```

**3. Plain functions** (no context needed):

```python
def get_current_time() -> str:
    """Get the current timestamp."""
    from datetime import datetime
    return datetime.now().isoformat()
```

**4. Explicit `Tool` instances** (full control):

```python
from mi.ai import Tool

def fetch_data(ctx: ToolContext, key: str) -> str:
    """Fetch data by key."""
    return str(ctx.data_object.artifacts.get(key))

fetch_tool = Tool(fetch_data, takes_ctx=True, name="fetch_artifact")
```

**5. Using `ToolSet.builder()`:**

```python
from mi.ai import ToolSet

def _build_tools(self, data_object):
    return (
        ToolSet.builder()
        .add(get_customer_data)
        .add(get_current_time)
        .add(Tool(fetch_data, name="fetch_artifact"))
        .build()
    )
```

### ToolContext

`ToolContext` is the mi.ai abstraction for tool execution context. It exposes:

| Attribute | Type | Description |
|-----------|------|-------------|
| `data_object` | `ProcessDataObject` | The pipeline data object being processed |
| `metadata` | `PipelineMetadata | None` | Pipeline metadata if available |

No backend internals (like pydantic-ai's `RunContext`) are exposed to tool functions.

### Tool Output

Tools can return:

- `str` — auto-wrapped to `TextContent`
- `ContentBlock` — `TextContent`, `ImageContent`, or `MediaContent`
- `list[ContentBlock]` — multiple content blocks

Backends normalize tool output to text where needed.

### Agent Example

```python
from mi.ai import AIAgentMixin, AIProcessorConfig, UserMessage, ToolContext, ai_tool
from mi.core import BaseProcessor
from pydantic import BaseModel

class RiskAssessment(BaseModel):
    risk_level: str
    factors: list[str]
    recommendations: list[str]

@ai_tool()
def get_transaction_history(ctx: ToolContext, days: int = 30) -> str:
    """Get recent transaction history."""
    txns = ctx.data_object.get_transactions(days=days)
    return f"Found {len(txns)} transactions: {txns[:5]}..."

@ai_tool()
def get_account_balance(ctx: ToolContext) -> str:
    """Get current account balance."""
    return f"Balance: ${ctx.data_object.balance}"

class RiskAnalysisAgent(AIAgentMixin[AccountData, RiskAssessment], BaseProcessor):
    output_schema = RiskAssessment
    system_prompt = """You are a risk analyst. Use the available tools to:
    1. Review transaction history
    2. Check account balances
    3. Identify risk factors
    Provide a comprehensive risk assessment."""

    def _build_user_message(self, data_object):
        return UserMessage().add_text(f"Assess risk for account {data_object.account_id}")

    def _build_tools(self, data_object):
        return [get_transaction_history, get_account_balance]

# Create with config
config = AIProcessorConfig(
    model="azure:gpt-5",
    max_turns=15,
    reasoning_effort=ReasoningEffort.HIGH,
)
agent = RiskAnalysisAgent(config)
```

## Default Artifact Storage

Both workflows and agents automatically store results as artifacts:

| Artifact Key | Content |
|--------------|---------|
| `{processor}_{model}_response` | `response.model_dump()` |
| `{processor}_{model}_usage` | `{requests, input_tokens, output_tokens}` |

For example, a processor named `SentimentAnalyzer` using `claude-sonnet-4-5` would create:
- `SentimentAnalyzer_claude-sonnet-4-5_response`
- `SentimentAnalyzer_claude-sonnet-4-5_usage`

### Custom Storage

Override the default methods to customize:

```python
class MyProcessor(AIWorkflowMixin[MyData, MyResult], BaseProcessor):
    output_schema = MyResult
    system_prompt = "..."

    def _build_user_message(self, data_object):
        return UserMessage().add_text(data_object.text)

    def _attach_response(self, data_object, response):
        # Custom storage logic
        data_object.set_artifact("my_custom_key", {
            "result": response.model_dump(),
            "processed_at": datetime.now().isoformat(),
        })

    def _attach_usage(self, data_object, usage):
        # Custom usage tracking
        data_object.metrics["ai_tokens"] = usage.input_tokens + usage.output_tokens
```

## Error Handling

Errors are normalized by the mixins:

```python
try:
    processor.process(data_object)
except ValueError as e:
    # Error message format: "{ProcessorName}: {Workflow|Agent} failed: {details}"
    print(f"AI processing failed: {e}")
```

## Best Practices

1. **Start with workflows** — use agents only when tools are necessary
2. **Keep tools simple** — each tool should do one thing well
3. **Write clear docstrings** — they become tool descriptions for the LLM
4. **Use `@ai_tool`** — prefer the decorator over raw `Tool()` for cleaner code
5. **Use appropriate reasoning** — LOW for simple tasks, HIGH for complex analysis
6. **Monitor usage** — check artifact storage for token costs
7. **Set realistic max_turns** — prevent runaway agent loops
8. **Use ToolContext** — processor and tool code should not import pydantic-ai directly

---

## See Also

- [Processors](components/processors.md) — base processor patterns that AI mixins extend
- [Architecture](architecture.md) — how processors fit into the pipeline lifecycle
- [Getting Started](getting-started.md) — end-to-end pipeline setup including AI processors
