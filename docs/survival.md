# Survival Association (log-rank)

**Namespace:** `cancer.Evidence` (facet `Survival`) ·
**FFL:** `src/cancer/ffl/cancer.ffl` ·
**Handler:** `src/cancer/handlers/cancer_handlers.py` (`_h_survival`) ·
**Science:** `src/cancer/_lib.py` (`survival_evidence`)

## Overview

The survival branch answers "does high expression of a candidate gene track with
worse patient outcome?" It splits the project's tumor cases high/low by each
candidate gene's expression and runs a log-rank test against GDC clinical overall
survival. It is the one evidence branch that **depends on another** — it consumes
the `expr_path` and `tumor_matrix_path` emitted by [expression](expression.md),
so in the graph it is a downstream node, not a root.

## How it works

`survival_evidence(project, tumor_samples, genes, min_group=10)` (`_lib.py`):

1. **Candidate genes** — the handler (`_h_survival`) reads the expression table,
   takes `expr[expr["candidate"]].index` as the gene set to test, and reads the
   per-sample `tumor_matrix` parquet.
2. **Survival endpoints** — GET `GDC /analysis/survival` filtered to the project;
   each donor gives `{submitter_id: (time, censored→event)}`.
3. **Per-gene log-rank** — for each candidate gene present in the tumor matrix,
   split cases at the gene's **median** expression into high/low groups. Tumor
   matrix columns (case submitter ids) are truncated to the `TCGA-XX-XXXX`
   barcode prefix to match the survival donor ids. Require ≥`min_group`=10 per
   arm, then `lifelines.statistics.logrank_test` on the two arms.
4. **Direction** — compare median follow-up time; `hi_worse = median(hi) <
   median(lo)` (shorter time in the high-expression arm ⇒ high expression is
   worse).

Data shape: `expression candidate set + tumor matrix + GDC survival donors →
per-gene {logrank_p, hi_worse} (parquet path) + tested_genes`.

## Fan-out

**One distributed task per cancer type** — no `foreach` inside the facet. Because
it consumes `expr.expr_path` / `expr.tumor_matrix_path`, the runtime schedules it
*after* `Expression` within the same per-type branch of
`PrioritizeGenes` (see [workflow](workflow.md)). Moderate cost, 25-minute timeout.

## Data & fields

- **Source:** GDC `/analysis/survival` (clinical overall survival) + the tumor
  matrix parquet from the expression branch.
- **Filter:** `cases.project.project_id == project`; genes limited to the
  expression `candidate` set; arms require ≥10 cases each.
- **Per-gene fields produced:** `logrank_p` (log-rank p-value), `hi_worse` (bool —
  high expression associated with worse survival). Empty frame (typed columns) when
  no gene has enough cases.

## External libraries / binaries

All **pip**, no binaries:

- **`requests`** — GDC survival call.
- **`lifelines`** (`lifelines.statistics.logrank_test`) — the survival test,
  imported lazily.
- **`pandas` / `numpy`** — grouping, medians, table assembly.
- **`pyarrow`** — parquet output.

## Facets & workflows

| Facet | Kind | Effect / Cost / Timeout | Purpose |
|---|---|---|---|
| `cancer.Evidence.Survival(project, expr_path, tumor_matrix_path)` | event | external / **moderate** / 25 min | Log-rank OS association of high vs low expressors, per candidate gene |

Returns: `survival_path`, `tested_genes`.

## Cache / output

`survival_path` → `$FW_DATA_ROOT/cache/cancer/<project>/survival.parquet`
(remote) or `<root>/cancer-cache/<project>/survival.parquet` (local), via
`storage.write_parquet`.

## Gotchas & notes

- **Barcode-prefix join is load-bearing.** Tumor matrix columns are case submitter
  ids; only the `TCGA-XX-XXXX` prefix matches the survival donor ids. A change to
  how the expression branch labels columns would silently drop the join.
- **Small-cohort genes are skipped, not failed.** Genes without ≥10 cases per arm
  are omitted; the frame can legitimately come back empty, and
  [ranking](ranking.md) treats a missing gene as `survival_p = NaN` (scored 0).
- **Direction, not just significance.** `hi_worse` carries the sign; the composite
  penalizes a significant-but-protective gene (`hi_worse=False` ⇒ ×−0.3) so a low-p
  protective gene is not rewarded like a low-p harmful one.
- **Depends on `Expression`** — it cannot run standalone; both `expr_path` and
  `tumor_matrix_path` must exist.

## Related specs

- [expression.md](expression.md) — supplies the candidate set and the tumor
  matrix this branch reads.
- [ranking.md](ranking.md) — turns `logrank_p` + `hi_worse` into the signed
  survival term (weight 1.0).
- [workflow.md](workflow.md) — orders `Survival` after `Expression` per type.
