# Known Cancer Drivers (intOGen)

**Namespace:** `cancer.Evidence` (facet `Driver`) ·
**FFL:** `src/cancer/ffl/cancer.ffl` ·
**Handler:** `src/cancer/handlers/cancer_handlers.py` (`_h_driver`) ·
**Science:** `src/cancer/_lib.py` (`intogen_drivers`)

## Overview

The driver branch supplies the **known cancer-driver gene list** from the intOGen
Compendium of Cancer Genes (CC0). It is the only branch that is **not** per-project
science — it is a shared lookup used across all cancer types to reward genes that
are already established drivers. In the [ranking](ranking.md) it carries the
highest default weight (1.2) and is a simple indicator (`is_driver`) plus a
`role` label.

## How it works

`intogen_drivers()` (`_lib.py`):

1. GET the intOGen Compendium zip
   (`IntOGen-Drivers-20240920.zip`), open it in memory with `zipfile`.
2. Find the member ending `Compendium_Cancer_Genes.tsv` and read it with
   `pandas.read_csv(sep="\t")`.
3. Pick the symbol column (`SYMBOL` if present, else the first column) and the
   role column (`ROLE` if present). For each row, accumulate
   `{gene: {role, n_cohorts}}`, incrementing `n_cohorts` per appearance (a gene
   listed in multiple cohorts counts up).

The handler (`_h_driver`) turns that dict into a DataFrame indexed by gene and
writes it to a **shared** parquet path (not per-project).

Data shape: `intOGen zip → Compendium TSV → {gene: {role, n_cohorts}} → shared
drivers parquet path + driver_count`.

## Fan-out

**Zero-parameter, shared across types.** The FFL declares `Driver()` with no
arguments; each `PrioritizeGenes` per-type branch calls it (`drv = Driver()`), but
the output is written to one shared path (`_shared/intogen_drivers.parquet`) — the
same driver list applies to every cancer type. Single, cheap task (`free` cost,
10-minute timeout).

## Data & fields

- **Source:** intOGen Compendium of Cancer Genes zip
  (`www.intogen.org/download?file=IntOGen-Drivers-20240920.zip`), CC0.
- **Filter:** none — the whole compendium is loaded.
- **Per-gene fields produced:** `role` (e.g. Act/LoF, from the `ROLE` column),
  `n_cohorts` (count of compendium appearances).

## External libraries / binaries

All **pip**, no binaries:

- **`requests`** — download the zip (`_req`).
- **`zipfile` / `io`** (stdlib) — in-memory extraction.
- **`pandas`** — read the TSV, build the drivers table.
- **`pyarrow`** — parquet output.

## Facets & workflows

| Facet | Kind | Effect / Cost / Timeout | Purpose |
|---|---|---|---|
| `cancer.Evidence.Driver()` | event | external / **free** / 10 min | Known cancer-driver genes from the intOGen Compendium (CC0), shared across types |

Returns: `driver_path`, `driver_count`.

## Cache / output

`driver_path` → `$FW_DATA_ROOT/cache/cancer/_shared/intogen_drivers.parquet`
(remote) or `<root>/cancer-cache/_shared/intogen_drivers.parquet` (local). Note
the `_shared` bucket (via `storage.join(cache_root(), "_shared", …)`) — distinct
from the per-`<project>` buckets the other branches use.

## Gotchas & notes

- **Pinned compendium release.** `INTOGEN_ZIP` hard-codes the `20240920` release;
  a newer compendium requires editing `_lib.INTOGEN_ZIP`.
- **Column-name resilience.** The reader tolerates schema drift by falling back to
  the first column for the symbol and emitting an empty role if `ROLE` is absent.
- **Shared, not per-type** — do not expect a project-specific driver table; the
  same list is reused everywhere, which is why it is weighted as a prior.

## Related specs

- [ranking.md](ranking.md) — `is_driver` (weight 1.2) and `driver_role` feed the
  composite; the report shows the role badge.
- [workflow.md](workflow.md) — every per-type branch calls `Driver()`.
- [report.md](report.md) — renders the "Known driver" column, sourced from this
  facet.
