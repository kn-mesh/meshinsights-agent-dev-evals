# Development Bugs

This backlog records Eval Explorer app bugs and product gaps found during the
July 22, 2026 local app review. Repository, catalog, packaging, and
development-toolchain findings are tracked elsewhere. All findings below were
resolved and re-verified locally on July 22, 2026.

## P2 — Evidence errors remain global after leaving the Evidence tab

**Resolved:** Query failures now render only on their owning surface. Evidence
errors disappear when the reviewer leaves the Evidence tab; run, performance,
attempt-list, attempt-detail, and comparison failures likewise stay scoped.

The React shell combines every query error into one page-level banner. After an
evidence request fails, switching back to Evaluation leaves the evidence error
visible even though the Evaluation content is healthy and usable.

Desired outcome:

- render evidence-loading failures inside the Evidence tab;
- show run, attempt, and performance failures only beside the surface they
  affect; and
- clear or hide a tab-specific error when that tab is no longer active.

Add a component test that fails the evidence query, changes tabs, and confirms
that evaluation content is not presented as globally failed.

## P2 — Evidence review omits the model's 30-day and 7-day views

**Resolved:** The evidence tab now derives hash-verified 365-day, 30-day, and
7-day views from the retained Azure snapshot. The 365-day view uses four
chronological segments with shared temperature/delta scales, and every relevant
view marks the alarm edge.

The `v1_3` pipeline sends deterministic 365-day, 30-day, and 7-day temperature
views to the model, but the Eval Explorer evidence tab renders only three
charts over the full 365-day telemetry window. A reviewer therefore cannot use
the explorer to inspect the same alarm-adjacent 30-day and 7-day views that
informed the evaluated decision, despite the product requirement that evidence
visuals preserve Benchmark Studio and model-input semantics.

This reproduced on run `eval_c562a9ee02502ec11c5031eb`, example
`250000116|2026-03-04T08:01:36`: the evidence package loaded successfully from
the retained Azure snapshot, but every rendered chart was labeled `365-day
history` and no shorter-window controls or plots were available.

Desired outcome:

- render the same deterministic 365-day, 30-day, and 7-day temperature/delta
  views used by `v1_3`, including the established segmentation and alarm-edge
  semantics;
- derive all views from the exact hash-verified retained source snapshot; and
- add an evidence-display test that verifies all required windows and their
  alarm timestamp alignment.

## P2 — Attempt navigation stops at 1,000 rows despite backend pagination

**Resolved:** Attempt browsing now uses 100-row pages with previous/next
navigation, bounded offsets, and URL-persisted page state. Filter changes reset
the page, and invalid or out-of-range offsets are normalized.

The backend supports `offset` and `limit`, including result sets larger than
10,000 attempts, but the React shell always requests `limit=1000` and provides
no next-page, previous-page, or virtualized continuation UI. Attempts after the
first 1,000 are inaccessible through ordinary browsing unless a user already
knows a search term that narrows the server-side result.

Desired outcome:

- add explicit pagination or an incremental/virtualized attempt list;
- preserve page state in the URL alongside run, filter, search, and execution;
- reset or validate the page when filters change; and
- test navigation to an attempt beyond the first 1,000 matches.

## P2 — Backend explorer capabilities are not exposed in the UI

**Resolved:** Field and slice facets are now first-class attempt filters, and
the explorer lists retained comparisons and loads comparison detail. All
selections participate in URL state where applicable.

The API and query core support field facets, slice facets, and comparison
routes, but the React shell does not expose field filtering, slice filtering,
comparison selection, or comparison detail. This makes the ownership boundary
unclear: the capabilities appear implemented from the API perspective but are
not discoverable to a human reviewer.

Desired outcome:

- either add the missing UI controls/views, or explicitly mark these endpoints
  as deferred API-only capabilities;
- use the returned field and slice facets rather than silently discarding them;
  and
- add end-to-end tests for whichever surfaces are declared supported.

## P3 — Evidence charts require a very large browser chunk

**Resolved:** The chart runtime now uses Plotly's cartesian-only distribution.
The lazy chunk fell from approximately 4.84 MB minified / 1.47 MB gzip to 1.43
MB minified / 475 KB gzip. The production build enforces 1.6 MB minified and
550 KB gzip budgets.

The production build emits a Plotly chunk of approximately 4.8 MB minified and
1.47 MB gzip. It is lazy-loaded, so the initial explorer shell remains modest,
but the first Evidence-tab visit pays the full download and parse cost.

Desired outcome:

- evaluate a narrower Plotly bundle, a smaller charting dependency, or a
  project-owned build containing only required trace types; and
- set a measured evidence-tab load budget so the tradeoff is intentional.

## P2 — Frontend tests do not cover the primary explorer workflow

**Resolved:** A mocked-API component suite now covers URL restoration,
pagination beyond 1,000 attempts, field/slice filters, attempt detail,
comparison detail, review-unavailable behavior, and tab-scoped evidence errors.
Evidence-window derivation has dedicated tests, and the supported responsive
breakpoint was re-verified in the local browser without horizontal overflow.

The frontend suite currently covers the evidence schema and static performance
rendering, but not the main interactive workflow. Live browser testing found
behavior that the five existing frontend tests could not detect.

Desired outcome: add a mocked-API browser or component suite covering:

- run selection and loading states;
- state/search filtering;
- attempt selection and deep-link restoration;
- evaluation, performance, review-unavailable, evidence, and raw tabs;
- tab-scoped error recovery;
- pagination; and
- the responsive layout at the supported breakpoint.
