<!-- SPEC TEMPLATE — every docs/<feature>.md follows this shape so the set reads
consistently. Delete this comment in real specs. Keep sections in this order;
omit a section only if it genuinely does not apply (say so in one line rather
than dropping the heading silently). Ground every claim in the actual FFL
docstrings / handler code / _lib science — do not invent behaviour. -->

# <Feature Name>

**Namespace(s):** `cancer.<ns>` · **FFL:** `src/cancer/ffl/cancer.ffl` ·
**Handler:** `src/cancer/handlers/cancer_handlers.py` (`_h_<name>`) ·
**Science:** `src/cancer/_lib.py` (`<function>`)

## Overview
One or two paragraphs: what this evidence branch (or stage) is for, the question
it answers, and where it sits in the graph (source → per-gene score → merge →
render). Name the open public dataset it pulls from.

## How it works
The algorithm / data flow, step by step. Name the concrete `_lib` function and
the shape of the data at each hop (GDC STAR-Counts matrix → per-gene table →
parquet path → scalar). Note that every branch writes its per-gene table to
object storage and returns the PATH — the workflow graph carries only paths +
scalars, so the graph itself is the explanation.

## Fan-out
Does it fan out across the fleet? The domain fans the *whole* evidence graph
per cancer type via `PrioritizeGenes`'s `foreach ct in $.cancer_types`; within a
branch, say whether it is a single distributed task per type (it is) and what
the per-type work looks like.

## Data & fields
Which dataset it queries (GDC `/files` + `/data`, GDC `/ssm_occurrences`, GDC
`/analysis/survival`, GTEx bulk GCT, intOGen Compendium zip), the filters
(TCGA project id, sample type `Primary Tumor` / `Solid Tissue Normal`, STAR-Counts
workflow), and the real per-gene fields it produces (`log2fc`, `specificity`,
`mutation_freq`, `logrank_p`, `driver_role`, `composite_score`, …).

## External libraries / binaries
Every non-stdlib dependency this feature relies on and what for — `requests`
(HTTP to GDC/GTEx/intOGen), `pandas`/`numpy`, `scipy.stats` (Welch t-test),
`lifelines` (log-rank), `pyarrow` (parquet). All **pip** deps; there are no
binary dependencies in this domain.

## Facets & workflows
The event facet(s), with signature and the one-line purpose from the FFL
docstring. All facets here are **event** facets (need a handler). Note the
`Effect`/`Cost`/`Timeout` mixins from the FFL.

## Cache / output
The object-store layout via `src/cancer/storage.py`: cached intermediates under
`$FW_DATA_ROOT/cache/cancer/<project>/<name>.parquet` (remote) or
`<root>/cancer-cache/...` (local); rendered HTML under `.../cache/cancer/maps/<slug>/index.html`.
Name the concrete artifact(s) and format (parquet table / HTML page).

## Gotchas & notes
Known pitfalls, cross-cohort caveats, rate/size limits, or non-obvious
constraints (worth capturing anything a future maintainer would trip on).

## Related specs
Links to the specs this feature composes with or depends on.
