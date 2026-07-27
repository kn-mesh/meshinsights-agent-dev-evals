"""Reference-project model catalog expectations."""

from workbench.models.catalog import load_model_catalog


def test_reference_catalog_defines_expected_model_choices() -> None:
    catalog = load_model_catalog()

    assert catalog.default_model == "azure:gpt-5.6-luna"
    assert catalog.get("azure:gpt-5.6-luna").api == "openai_responses"
    assert catalog.get("anthropic:claude-sonnet-4-6").api == "anthropic_messages"
    assert catalog.get("google:gemini-3.5-flash").api == "google_generate_content"
    assert (
        catalog.get("openrouter:google/gemini-3.5-flash").api
        == "openai_chat_completions"
    )
    assert catalog.get("azure:gpt-5.6-luna").pricing_key == (
        "azure:gpt-5.6-luna-standard-global"
    )
    assert (
        catalog.get("azure:claude-sonnet-4-6").pricing_key
        == "azure:claude-sonnet-4-6-foundry"
    )
    claude_pricing = catalog.get("azure:claude-sonnet-4-6").pricing
    assert claude_pricing is not None
    assert claude_pricing.billing_provider == "azure_claude"
    for model in catalog.models:
        assert model.pricing is not None
        assert model.pricing.estimator_version == 3
