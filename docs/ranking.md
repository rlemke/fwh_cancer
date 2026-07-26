# Composite Ranking

**Namespace:** `cancer.Rank` (facet `Composite`) ·
**FFL:** `src/cancer/ffl/cancer.ffl` ·
**Handler:** `src/cancer/handlers/cancer_handlers.py` (`_h_composite`) ·
**Science:** `src/cancer/_lib.py` (`composite_rank`, `_z`)

## Overview

The ranking stage is the fan-**in** of the evidence graph: it reads the four
evidence-branch parquet tables (expression, mutation, drivers, survival) by path
and merges them into one ranked, explainable per-gene table. The score is a
**weighted z-combination** of the branch signals, with tunable weights surfaced as
workflow inputs. This is the pipeline's join point — every score column in the
final [report](report.md) originates in a branch and is combined here.

## How it works

`composite_rank(expr, mut, drivers, surv, weights=None, top_n=50)` (`_lib.py`):

1. **Candidate set** — start from `expr[expr["candidate"]]` (the over-expressed,
   significant genes from [expression](expression.md)).
2. **Join branch columns onto candidates** by gene symbol:
   `mutation_freq` / `mutated_samples` (0 if absent), `driver_role` / `is_driver`
   (from the intOGen dict), `survival_p` / `survival_hi_worse` (NaN/False if
   absent).
3. **Signed survival score** — `-log10(survival_p)` scaled by `+1` when
   `hi_worse` else `−0.3` (a significant *protective* gene is demoted, not
   rewarded).
4. **Weighted z-combination** — `_z` standardizes each term; the score is
   `w.overexpression·z(log2fc) + w.specificity·z(specificity) +
   w.survival·z(surv_score) + w.mutation·z(log1p(mutated_samples)) +
   w.driver·is_driver`. Defaults: `overexpression=1.0, specificity=1.0,
   survival=1.0, mutation=0.8, driver=1.2` (`_lib.DEFAULT_WEIGHTS`).
5. **Rank & truncate** — sort by `composite_score` desc, insert a 1-based `rank`
   column, return the top `top_n`.

Data shape: `four branch parquet paths → merged per-gene table → ranked parquet
path + ranked_count + top_genes (comma-joined top-10 symbols)`.

## Fan-out

**One distributed task per cancer type** — no `foreach`. It is the join node of
the per-type branch in `PrioritizeGenes`; the runtime schedules it once all four
evidence paths for that type exist (see [workflow](workflow.md)). `io` effect,
`free` cost, 10-minute timeout — it does no network I/O, only reads/writes
parquet.

## Data & fields

- **Inputs:** the parquet paths `expr_path`, `mutation_path`, `driver_path`,
  `survival_path` (read via `storage.read_parquet`).
- **Weights:** `overexpression`, `specificity`, `survival`, `mutation`, `driver`
  — FFL `Double` inputs, defaulted from `DEFAULT_WEIGHTS`; only keys the handler
  is passed are overridden.
- **Per-gene fields produced:** `rank`, plus the joined columns and
  `composite_score`. The report reads `log2fc`, `neglog10p`, `specificity`,
  `mutation_freq`, `survival_p`, `survival_hi_worse`, `driver_role`, `is_driver`,
  `composite_score`.

## External libraries / binaries

All **pip**, no binaries:

- **`pandas` / `numpy`** — merge, z-scoring (`_z`), `log1p`, sort.
- **`pyarrow`** — reads the four input parquets and writes the ranked parquet.

No network dependency — hence the `io` effect (pure object-store I/O).

## Facets & workflows

| Facet | Kind | Effect / Cost / Timeout | Purpose |
|---|---|---|---|
| `cancer.Rank.Composite(project, expr_path, mutation_path, driver_path, survival_path, top_n=50, overexpression=1.0, specificity=1.0, survival=1.0, mutation=0.8, driver=1.2)` | event | io / **free** / 10 min | Weighted z-combination of all evidence branches into one ranked table |

Returns: `ranked_path`, `ranked_count`, `top_genes`.

## Cache / output

`ranked_path` → `$FW_DATA_ROOT/cache/cancer/<project>/ranked.parquet` (remote) or
`<root>/cancer-cache/<project>/ranked.parquet` (local), via
`storage.write_parquet`. This is the single input to the [report](report.md).

## Gotchas & notes

- **Candidate-gated.** Only genes flagged `candidate` by the expression branch are
  ranked; a gene mutated or driver-listed but not over-expressed will not appear.
- **Missing evidence ⇒ neutral, not dropped.** Absent mutation/survival values
  default to 0/NaN and z-score toward the mean, so a gene is not penalized for a
  branch that had no data on it.
- **Weights are the tuning surface.** They flow FFL input → handler
  (`{k: float(p[k]) for k in DEFAULT_WEIGHTS if p.get(k) is not None}`) → `_lib`;
  changing them re-orders the table without recomputing any branch.
- **Empty survival is handled** — the handler substitutes a typed empty frame when
  `survival_path` is falsy.

## Related specs

- [expression.md](expression.md), [mutation.md](mutation.md),
  [drivers.md](drivers.md), [survival.md](survival.md) — the four branches merged
  here.
- [report.md](report.md) — renders `ranked.parquet` to HTML.
- [workflow.md](workflow.md) — the fan-in point of the per-type sub-graph.
