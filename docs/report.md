# Evidence-table Report

**Namespace:** `cancer.Report` (facet `EvidenceTable`) ·
**FFL:** `src/cancer/ffl/cancer.ffl` ·
**Handler:** `src/cancer/handlers/cancer_handlers.py` (`_h_report`) ·
**Renderer:** `src/cancer/report.py` (`render_evidence_table`)

## Overview

The report stage renders the ranked table to a **self-contained HTML page** — the
domain's single user-facing artifact. It is deliberately "not a list of genes":
every score column header carries the FFL facet that produced it and the public
dataset it came from, gene names link to live GDC/GTEx portals, and an "About this
data" popup carries full provenance plus the TCGA-vs-GTEx cross-cohort disclosure
(gallery "About this data" parity). This is the terminal node of each per-type
branch.

## How it works

`_h_report` reads `ranked_path` (parquet) and calls
`render_evidence_table(project, project_name, ranked, n_tumor, n_normal,
gtex_tissue, weights, generated)` (`report.py`):

1. **Column map** — `COLUMNS` pairs each key with `(header, producing FFL facet,
   dataset label, decimals)`, e.g. `composite_score → cancer.Rank.Composite`,
   `specificity → cancer.Evidence.Expression / GTEx healthy tissue`,
   `driver_role → cancer.Evidence.Driver / intOGen`.
2. **Cells** — per gene: gene symbol linked to `portal.gdc.cancer.gov/genes/<g>`;
   `driver_role` as a badge; `survival_p` with a `↑worse`/`↓` arrow; numeric
   columns formatted to their declared decimals.
3. **Header tooltips** — each `<th>` `title` is `facet: <f> · source: <ds>` and a
   `<span class='src'>` shows the dataset under the header.
4. **Provenance note** — a paragraph stating the sample counts, the same-pipeline
   vs cross-cohort distinction, the survival direction convention, and the exact
   weight string, surfaced behind the "About this data" modal.
5. The handler slugs the project (`TCGA-LUAD` → `luad`) and writes
   `<maps_root>/<slug>/index.html`.

Data shape: `ranked parquet → single HTML page (path)`.

## Fan-out

**One distributed task per cancer type** — no `foreach`. Terminal node of the
per-type branch in `PrioritizeGenes`; its `html_path` / `region` / `gene_count`
are what the workflow `yield`s (see [workflow](workflow.md)). `io` effect, `free`
cost, 10-minute timeout.

## Data & fields

- **Input:** the `ranked.parquet` from [ranking](ranking.md), plus scalars from
  the expression branch (`n_tumor`, `n_normal`, `gtex_tissue`, `project_name`).
- **Rendered columns:** `rank`, `gene`, `composite_score`, `log2fc`, `neglog10p`,
  `specificity`, `mutation_freq`, `survival_p`, `driver_role` — each attributed to
  its source facet/dataset.
- **Live links:** `portal.gdc.cancer.gov/genes/<gene>` and
  `gtexportal.org/home/gene/<gene>`.

## External libraries / binaries

- **stdlib only** in the renderer — `html` (escaping) and `json`. No third-party
  charting/templating library; the HTML/CSS/JS is inlined by hand. Parquet read of
  the ranked table uses `pyarrow` via `storage.read_parquet`.

## Facets & workflows

| Facet | Kind | Effect / Cost / Timeout | Purpose |
|---|---|---|---|
| `cancer.Report.EvidenceTable(project, ranked_path, n_tumor, n_normal, gtex_tissue, project_name)` | event | io / **free** / 10 min | Render the ranked evidence table to a provenance-linked HTML page |

Returns: `html_path`, `region` (the project slug), `gene_count`.

## Cache / output

`html_path` → `$FW_DATA_ROOT/cache/cancer/maps/<slug>/index.html` (remote MinIO)
or `<root>/cancer-maps/<slug>/index.html` (local), via `storage.write_text`
(`maps_root()`). The page is fully self-contained (inline CSS/JS), so it can be
served directly from the object store or a static host.

## Gotchas & notes

- **Provenance is the product.** The value is the per-column facet+dataset
  attribution and the "About this data" disclosure, not the styling — preserve the
  `COLUMNS` facet/source mapping when editing.
- **Cross-cohort caveat is mandatory.** The note explicitly frames GTEx
  tumor-specificity as corroboration (different pipeline), matching the
  [expression](expression.md) branch's disclosure — do not drop it.
- **`region` is a slug, not a geography.** Despite the field name (shared with the
  map-domain workflow shape), `region` here is the lower-cased project id minus the
  `tcga-` prefix.
- **Renders whatever ranking produced** — no re-computation; a stale
  `ranked.parquet` renders stale numbers.

## Related specs

- [ranking.md](ranking.md) — produces the `ranked.parquet` this renders.
- [expression.md](expression.md) — source of the sample counts and the
  cross-cohort disclosure text.
- [workflow.md](workflow.md) — the terminal node whose outputs are `yield`ed.
