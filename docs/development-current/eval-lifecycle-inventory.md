# Eval Lifecycle Inventory

## Decision

The four pre-lifecycle schema-v1 runs under
`eval_results/v1_3/phase-1-benchmark-3fb7f544/v1/runs/` remain readable as
legacy working evals. They are not automatically migrated or deleted.

They predate the complete working-run evidence-storage identity and frozen
pricing/lifecycle contract required for elevation. Supporting automatic
migration would add a generalized migration framework without proving that any
of these historical runs represents a meaningful version. A future explicit
product-owner decision may delete them or preserve selected information, but
new runs use `eval_results/working/` and only contract-complete runs may be
elevated.

## Inventory At Decision Time

| Run | Scope | Model | Accuracy | Decision |
|---|---:|---|---:|---|
| `eval_16e940b05e920f3175f7dbcd` | 210 attempts | `azure:gpt-5.6-luna` | 85.24% | Legacy working; no automatic migration |
| `eval_4be53d6e3db5f3146a3be6d7` | 1 attempt | `azure:gpt-5.6-luna` | 100% | Legacy working smoke run |
| `eval_c562a9ee02502ec11c5031eb` | 70 attempts | `azure:gpt-5.6-luna` | 78.57% | Legacy working; no automatic migration |
| `eval_eb717b7157f304fb5ea2a1d8` | 1 attempt | `azure:gpt-5.6-luna` | 100% | Legacy working smoke run |

No retained agent versions were present under `agent_versions/` at inventory
time.

## Post-Implementation Validation

`eval_c03aa8b5f6ef7319ccfe7f09` is the first full validation run written under
the supported working layout. It evaluated all 70 examples once with
`azure:gpt-5.6-terra` at low reasoning:

- 70 completed, valid, and scored attempts; no failed, invalid, cancelled, or
  missing attempts;
- 80.00% complete-evaluation accuracy (56/70);
- 675,319 total tokens, including 33,792 cached-input and 12,792 reasoning
  tokens;
- complete review capture with verified object integrity and no missing,
  orphaned, or unfinished review objects; and
- unavailable cost for all 70 units because no reviewed Terra pricing snapshot
  is configured and the provider did not report actual cost.

The run remains a working eval. It was not elevated because retention is an
explicit product-owner decision, not an automatic consequence of successful
validation.
