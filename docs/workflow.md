# PrioritizeGenes — the Evidence-graph Fan-out

**Namespace:** `cancer.workflows` (workflow `PrioritizeGenes`) ·
**FFL:** `src/cancer/ffl/cancer.ffl` ·
**Handlers:** none of its own — orchestrates the six event facets ·
**Entry point:** `cancer:domain` (`src/cancer/__init__.py`, `DomainPackage`)

## Overview

`PrioritizeGenes` is the domain's single entry-point workflow and the reason the
whole thing is an *evidence graph* rather than a script: it fans the entire
per-type evidence sub-graph (expression → mutation/driver/survival → rank →
report) across the fleet, one branch per requested cancer type, and `yield`s one
published evidence table per type. Because each facet returns only object-store
**paths + scalars**, the workflow DAG the runtime executes *is* the explanation of
how each gene was scored.

## How it works

```
workflow PrioritizeGenes(cancer_types: [String] = ["TCGA-LUAD"], top_n: Long = 50)
  andThen foreach ct in $.cancer_types {
     expr  = Expression(project = $.ct)
     mut   = Mutation(project = $.ct)
     drv   = Driver()
     surv  = Survival(project = $.ct, expr_path = expr.expr_path,
                      tumor_matrix_path = expr.tumor_matrix_path)
     ranked = Composite(project = $.ct, expr_path = expr.expr_path,
                        mutation_path = mut.mutation_path, driver_path = drv.driver_path,
                        survival_path = surv.survival_path, top_n = $.top_n)
     table = EvidenceTable(project = $.ct, ranked_path = ranked.ranked_path, ...)
     yield PrioritizeGenes(status = "completed", html_path = table.html_path,
                           region = table.region, gene_count = table.gene_count)
  }
```

Within each `foreach` iteration the runtime resolves the data dependencies:
`Expression`, `Mutation`, `Driver` have no cross-branch inputs and can run
concurrently; `Survival` waits on `Expression`'s two paths; `Composite` waits on
all four evidence paths; `EvidenceTable` waits on `Composite`. Data flows entirely
as parquet/HTML paths between facets.

## Fan-out

**Per cancer type** — the `foreach ct in $.cancer_types` is the fan-out unit. Each
type becomes an independent branch of tasks distributed across the fleet, so N
cancer types run in parallel rather than serially; default is a single type
(`["TCGA-LUAD"]`), and passing the 9 matched-normal TCGA projects runs them all.
This is a fan-out/fan-in shape: fan-out over types, and *within* a type a small
DAG that fans in at `Composite`.

## Data & fields

- **Inputs:** `cancer_types: [String]` (default `["TCGA-LUAD"]`), `top_n: Long`
  (default 50). Valid project ids are the keys of `_lib.SUPPORTED` (the 9 TCGA
  projects with a usable matched-normal set).
- **Yields (per type):** `status`, `html_path`, `region`, `gene_count`.

## External libraries / binaries

None directly — the workflow declares no `script`/`prompt` block and registers no
handler; it composes the six event facets, whose dependencies are documented in
their own specs.

## Facets & workflows

| Declaration | Kind | Purpose |
|---|---|---|
| `cancer.workflows.PrioritizeGenes(cancer_types=["TCGA-LUAD"], top_n=50)` | workflow | Fan the evidence graph per cancer type; yield one published evidence table each |

Composes: `cancer.Evidence.Expression` / `.Mutation` / `.Driver` / `.Survival`,
`cancer.Rank.Composite`, `cancer.Report.EvidenceTable`. The FFL `use`s
`cancer.Evidence`, `cancer.Rank`, `cancer.Report`.

## Cache / output

No cache of its own; the terminal `EvidenceTable` writes the published HTML under
`$FW_DATA_ROOT/cache/cancer/maps/<slug>/index.html` (see [report](report.md)), and
the intermediate parquet tables live under `.../cache/cancer/<project>/` (see the
branch specs). Backend selection is via `src/cancer/storage.py`
(`FW_DATA_ROOT` / `FW_STORAGE`): shared MinIO on the fleet, host path locally.

## Gotchas & notes

- **Runs against real live endpoints.** Every branch hits GDC/GTEx/intOGen at
  execution time; there is no bundled fixture, so a run needs network egress and is
  gated by the branch timeouts (Expression is the long pole at 40 min).
- **`region` is a project slug** in the yielded result (e.g. `luad`), reusing the
  map-domain workflow return shape — it is not a geography.
- **Handler discovery** is via the `facetwork.domains` entry point
  (`cancer = "cancer:domain"`), which registers the six facets through
  `register_all_registry_handlers`; `cancer.workflows.PrioritizeGenes` itself has
  no handler.
- **Concurrency within a type is data-driven** — do not assume ordering beyond the
  path dependencies; only `Survival`→`Composite`→`EvidenceTable` are forced serial.

## Related specs

- [expression.md](expression.md) — the root branch (and `Survival`'s input).
- [mutation.md](mutation.md), [drivers.md](drivers.md),
  [survival.md](survival.md) — the parallel evidence branches.
- [ranking.md](ranking.md) — the per-type fan-in.
- [report.md](report.md) — the terminal node whose outputs are `yield`ed.
