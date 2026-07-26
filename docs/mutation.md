# Somatic-mutation Frequency

**Namespace:** `cancer.Evidence` (facet `Mutation`) ·
**FFL:** `src/cancer/ffl/cancer.ffl` ·
**Handler:** `src/cancer/handlers/cancer_handlers.py` (`_h_mutation`) ·
**Science:** `src/cancer/_lib.py` (`mutation_frequency`)

## Overview

The mutation branch answers "how often is each gene somatically mutated in this
cancer type?" from the **open** GDC simple-somatic-mutation (SSM) layer
(masked/aggregated — no controlled access). It is corroborating evidence: in the
final [ranking](ranking.md) it is a z-scored term with default weight 0.8,
lighter than the expression and driver signals.

## How it works

`mutation_frequency(project)` (`_lib.py`):

1. **Denominator** — GET `GDC /projects/<project>?fields=summary.case_count` for
   the project's case count (defaults to 1 if missing, to avoid divide-by-zero).
2. **Per-gene numerator** — POST `GDC /ssm_occurrences` with a `size:0` facet
   aggregation on `ssm.consequence.transcript.gene.symbol`; each bucket gives a
   gene symbol and a `doc_count` (~mutated occurrences ≈ mutated samples).
3. **Assemble** — build rows of `{gene (upper-cased), mutated_samples=doc_count,
   mutation_freq=doc_count/n_cases}`, index by gene, and stash
   `df.attrs["n_cases"]`.

Data shape: `GDC SSM facet buckets → per-gene mutation table (parquet path) +
n_cases + mutated_gene_count`.

## Fan-out

**One distributed task per cancer type** — no `foreach` inside the facet; the
per-type fan-out is `PrioritizeGenes` (see [workflow](workflow.md)). This is a
light branch: two GDC calls, no bulk download — hence the 20-minute timeout and
`moderate` cost.

## Data & fields

- **Source:** GDC `/projects/<project>` (case count) and GDC `/ssm_occurrences`
  (open SSM aggregation).
- **Filter:** `case.project.project_id == project`.
- **Per-gene fields produced:** `mutated_samples` (bucket `doc_count`),
  `mutation_freq` (`doc_count / n_cases`). Table carries `attrs["n_cases"]`.

## External libraries / binaries

All **pip**, no binaries:

- **`requests`** — the two GDC calls (`_req`).
- **`pandas`** — the per-gene table and `attrs`.
- **`pyarrow`** — parquet output.

## Facets & workflows

| Facet | Kind | Effect / Cost / Timeout | Purpose |
|---|---|---|---|
| `cancer.Evidence.Mutation(project)` | event | external / **moderate** / 20 min | Per-gene somatic-mutation frequency from open GDC SSM |

Returns: `mutation_path`, `n_cases`, `mutated_gene_count`.

## Cache / output

`mutation_path` → `$FW_DATA_ROOT/cache/cancer/<project>/mutation.parquet`
(remote) or `<root>/cancer-cache/<project>/mutation.parquet` (local), via
`storage.write_parquet`.

## Gotchas & notes

- **Top-mutated buckets only.** The facet aggregation returns the top-mutated gene
  buckets; genes not in a bucket fall back to `mutation_freq = 0` in the
  composite. That is acceptable because mutation is z-scored *corroborating*
  evidence, not a gate (documented in `mutation_frequency`'s docstring).
- **`doc_count` ≈ mutated samples, not exact.** It counts mutated occurrences on
  the open/aggregated SSM layer; treat it as a frequency proxy, not a precise
  mutated-case count.
- **Gene symbols are upper-cased** to match the expression/driver tables' symbol
  index on merge.

## Related specs

- [ranking.md](ranking.md) — merges `mutation_freq` / `mutated_samples`
  (`np.log1p`, weight 0.8) into the composite score.
- [workflow.md](workflow.md) — the per-type fan-out.
- [expression.md](expression.md) — the branch that supplies the candidate gene
  set the mutation column is joined onto.
