# Current Streamlit API Notes

This reference captures the small set of current Streamlit behaviors that coding agents often get wrong.

## `st.dataframe`

- Selection is enabled with `on_select="rerun"` or a callback.
- The return value is a dictionary-like `DataframeState` when selection is enabled.
- That object supports key and attribute access, so extraction code should be defensive.
- `selection_mode="single-row"` is the correct mode for master-detail row drill-down.

Docs:
- https://docs.streamlit.io/develop/api-reference/data/st.dataframe

## Width sizing

- Prefer the `width` parameter.
- Use `width="stretch"` for responsive charts and tables.
- `use_container_width` is deprecated across multiple elements and should not be used in new code unless you are matching an existing code path that still requires it.

Docs:
- https://docs.streamlit.io/develop/api-reference/data/st.dataframe
- https://docs.streamlit.io/develop/api-reference/charts/st.plotly_chart

## Fragments

- `@st.fragment` isolates reruns to a subsection of the app.
- Use fragments for expensive drill-down or live-updating regions, not as a blanket pattern.
- `st.rerun(scope="fragment")` is only valid from inside a fragment during a fragment rerun.
- If you need periodic refresh, `run_every` is available on fragments.

Docs:
- https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment
- https://docs.streamlit.io/develop/concepts/architecture/fragments
- https://docs.streamlit.io/develop/api-reference/execution-flow/st.rerun

## Session state and callbacks

- `st.session_state` is the canonical way to persist state across reruns.
- Callbacks are often cleaner than explicit reruns for straightforward widget-driven updates.
- Session state also persists across pages in multipage apps.

Docs:
- https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state
- https://docs.streamlit.io/develop/concepts/architecture/session-state
