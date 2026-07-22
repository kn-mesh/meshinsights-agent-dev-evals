# Development Bugs

This backlog records unresolved Eval Explorer app bugs and product gaps found
during the July 22, 2026 local app review. Repository, catalog, packaging, and
development-toolchain findings are tracked elsewhere.

## P2 — Evidence errors remain global after leaving the Evidence tab

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

## P2 — Attempt navigation stops at 1,000 rows despite backend pagination

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

The production build emits a Plotly chunk of approximately 4.8 MB minified and
1.47 MB gzip. It is lazy-loaded, so the initial explorer shell remains modest,
but the first Evidence-tab visit pays the full download and parse cost.

Desired outcome:

- evaluate a narrower Plotly bundle, a smaller charting dependency, or a
  project-owned build containing only required trace types; and
- set a measured evidence-tab load budget so the tradeoff is intentional.

## P2 — Frontend tests do not cover the primary explorer workflow

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
