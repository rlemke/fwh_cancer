# fwh_cancer — cancer gene-prioritization evidence graph (Facetwork domain)

Given one or more cancer types, fans out over open public cancer genomics
(TCGA/GDC tumor+normal expression, GTEx healthy baseline, GDC survival + somatic
mutations, intOGen drivers) and produces one **ranked, explainable evidence
table** per type — every score links back to its public dataset and the FFL
facet that computed it. Workflow: `cancer.workflows.PrioritizeGenes`.

## Feature specifications

Per-feature specs live in [`docs/`](docs/README.md) — one document per evidence
branch / stage, each grounded in the FFL docstrings, handlers, and `_lib` science.

| Spec | What it covers |
|------|----------------|
| [workflow](docs/workflow.md) | `PrioritizeGenes` — the per-type `foreach` fan-out/fan-in that runs the whole evidence graph. |
| [expression](docs/expression.md) | **Flagship.** GDC tumor-vs-normal over-expression + GTEx tumor-specificity. |
| [mutation](docs/mutation.md) | Per-gene somatic-mutation frequency from open GDC SSM. |
| [drivers](docs/drivers.md) | Known cancer-driver genes from the intOGen Compendium (CC0). |
| [survival](docs/survival.md) | Log-rank OS association of high vs low expressors (GDC clinical). |
| [ranking](docs/ranking.md) | `Composite` — weighted z-combination of all branches into one ranked table. |
| [report](docs/report.md) | `EvidenceTable` — provenance-linked, self-contained HTML page. |

Start at [`docs/README.md`](docs/README.md) for the full index.
