---
name: streamlit-app-builder
description: Build or update Streamlit apps in this repo with modern Streamlit patterns for layout, state, selection-enabled tables, fragments, charts, and review/debug workflows. Use this skill when a request involves creating, fixing, or reviewing a Streamlit app, especially when interactive table selection, fragment reruns, or responsive sizing are involved.
---

# Streamlit App Builder

Use this skill for Streamlit work in this repo. It is intentionally opinionated about app structure and current API usage because coding agents often write stale Streamlit patterns.

## Scope Of This Skill

This skill defines recommended Streamlit patterns for an AI coding agent working in this repo or a similar `mi-core` style pipeline repo.

Treat it as default implementation guidance, not as a guarantee that every existing app in the repo already follows every recommendation here.

Rules:
- Use these patterns by default when building a new app or refactoring toward a cleaner structure.
- If an existing app already uses a different but coherent pattern, preserve that local design unless the user asks to migrate it.
- Keep concrete repo references and current API details accurate.
- When guidance here conflicts with an intentional repo-specific implementation, the current repo code is the source of truth for local behavior.

Read [references/current-streamlit-api.md](references/current-streamlit-api.md) when you need exact guidance for:
- `st.dataframe(..., on_select=...)`
- `width="stretch"` vs deprecated `use_container_width`
- `@st.fragment` and fragment-scoped reruns
- `st.session_state` and callbacks

## Goals

- Optimize for fast inspection and decision-making.
- Prefer dense, predictable interfaces over decorative UI.
- Keep one clear primary interaction path per screen.
- Make desktop the primary target, but ensure narrow screens still load and navigate safely.

## Repo Vocabulary

- Use `unit` as the canonical entity term.
- In tables and labels, prefer `Unit ID`.

## App Shapes

Choose one of these patterns before coding:

### Visualization app

Use for inspecting one selected unit at a time.

Recommended structure:
1. Sidebar controls for dataset/context selectors and the run trigger.
2. Header metrics for key context.
3. Optional `st.info(...)` only when interpretation help materially improves usability.
4. Core charts.
5. Expanders for raw tables and raw JSON.

### Eval comparison app

Use for comparing multiple runs.

Recommended structure:
1. Sidebar filters for run context.
2. `Overall Results` tab with ranking table and top metrics.
3. `Run Details` tab with selected-run summary and per-unit drill-down.

### Pipeline review/debug app

Use to inspect final outputs, intermediate artifacts, and raw source data for a pipeline run.

Rules:
1. Keep `PipelineReceipt` usage lightweight.
2. Do not assume the receipt can reconstruct raw inputs.
3. Re-read or re-query original inputs only when the app already knows how to access them.
4. Use the selected unit to filter original inputs when possible.
5. Read `act_receipt.metadata` for intermediate artifacts.
6. Treat receipt-backed sections as optional and handle missing metadata defensively.

## Component Standards

### Tables

Use `st.dataframe` by default.

Rules:
1. Set `hide_index=True` unless the index is meaningful.
2. Prefer `width="stretch"` for responsive sizing.
3. Use explicit human-readable column names.
4. Put raw or debug tables in expanders.

For selectable master-detail flows, use a selection-enabled dataframe and robust row extraction:

```python
selection_state = st.dataframe(
    table_df,
    on_select="rerun",
    selection_mode="single-row",
    hide_index=True,
    width="stretch",
    key=f"table_{table_id}",
)


def extract_selected_rows(selection_state: object) -> list[int]:
    """Return selected row indices from Streamlit dataframe selection state."""

    try:
        rows = list(selection_state.selection.rows)  # type: ignore[attr-defined]
        return [int(row) for row in rows]
    except Exception:
        pass

    if isinstance(selection_state, dict):
        selection = selection_state.get("selection", {})
        rows = selection.get("rows", [])
        if isinstance(rows, list):
            return [int(row) for row in rows]

    return []
```

Do not assume a single concrete return type for selection state.

### Charts

Prefer Plotly for interactive charts.

Rules:
1. Keep chart styling consistent within one app.
2. Use explicit titles and axis labels.
3. Keep color mapping stable for the same signal.
4. Prefer `width="stretch"` unless content-sized rendering is intentional.
5. Set explicit keys in loops and dynamic views.

```python
st.plotly_chart(fig, width="stretch", key=f"chart_{entity_id}_{chart_type}")
```

### JSON and metadata

- Use `st.json(...)` for structured payloads.
- Put secondary technical detail in expanders.
- Add a short `st.info(...)` above dense JSON only when it prevents likely confusion.

## State and Reruns

Use `st.session_state` for durable UI state such as selected run ID, selected row index, or panel mode.

Rules:
1. Initialize keys once near the top of the module.
2. Keep state values small and serializable when practical.
3. Derive computed views from canonical state instead of duplicating state.
4. Prefer widget callbacks when they express the flow cleanly.
5. Use `st.rerun()` sparingly. It is valid, but callbacks or containers are often simpler.

## Fragments

Use `@st.fragment` for isolated, interactive, or expensive subregions that should not trigger a full-page rerun.

```python
@st.fragment
def details_panel() -> None:
    """Render a rerun-isolated details panel."""

    if st.button("Refresh details", key="refresh_details"):
        st.rerun(scope="fragment")
```

Rules:
1. Use fragments for expensive drill-down regions, not every section.
2. Keep shared state in `st.session_state`.
3. Keep sidebar controls outside fragments unless you explicitly want fragment-local behavior.
4. Only call `st.rerun(scope="fragment")` from inside a fragment during a fragment rerun.
5. If you need lightweight periodic refresh, consider `@st.fragment(run_every="10s")`.

## Key Hygiene

Set explicit keys when:
1. Rendering widgets or charts in loops.
2. Using selection-enabled dataframes.
3. Rendering conditional branches that mount and unmount widgets.

Poor keys are a common cause of selection loss and widget resets.

## Performance

1. Cache stable reads and parsing with `st.cache_data` where appropriate.
2. Avoid reloading large JSON, CSV, or artifact payloads on every interaction.
3. Keep expensive transforms out of layout code.
4. Recompute only the views affected by filter or selection changes.
5. For review/debug apps, cache file loads and filter after load.

## Error and Empty States

Every app should explicitly handle:
1. Missing files or directories.
2. Malformed payloads.
3. Empty filter results.
4. Missing required fields in selected rows.

Prefer actionable `st.error`, `st.warning`, and `st.info` messages instead of stack traces.

## Run Command

Include this comment near the top of each Streamlit module:

```python
# uv run python -m streamlit run src/streamlit_apps/<your_app>.py
```

## Delivery Checklist

Before finishing:
1. Confirm sidebar controls are clear and stable.
2. Separate summary views from drill-down views.
3. Verify selection tables have stable keys and defensive extraction.
4. Ensure raw payloads are accessible through expanders.
5. Check explicit empty and error states.
6. Confirm review/debug apps keep receipts lightweight and load raw source data separately.
7. Verify the page still works on a narrow screen.

## Usage Examples

- "Build a Streamlit app to compare eval runs and drill into misclassified units."
- "Fix this Streamlit app so row selection stops resetting."
- "Refactor this dashboard to use fragments for the expensive details pane."
- "Review this Streamlit module for stale API usage and layout issues."
