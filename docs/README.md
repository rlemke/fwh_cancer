# fwh_cancer — Feature Specifications

This directory holds one **spec per feature** of the cancer gene-prioritization
evidence graph. Each document follows a common shape
([`SPEC_TEMPLATE.md`](SPEC_TEMPLATE.md)) and states, for that feature: how it
works, whether and how it **fans out** across the fleet, the **datasets and fields**
it produces, the **external libraries** it relies on, its **facets & workflows**,
and its **cache/output**. Claims are grounded in the FFL `/** … */` docstrings
(`src/cancer/ffl/cancer.ffl`), the handler code
(`src/cancer/handlers/cancer_handlers.py`), and the science module
(`src/cancer/_lib.py`) — those remain the source of truth; these specs are the
feature-level narrative over them.

**Start here:** [**Over-expression & Tumor-specificity**](expression.md) — the
flagship evidence branch (the widest/slowest facet, root of each per-type
sub-graph), and [**PrioritizeGenes**](workflow.md) for the fan-out that ties the
graph together.

## Orchestration

| Spec | What it covers |
|------|----------------|
| [workflow.md](workflow.md) | `cancer.workflows.PrioritizeGenes` — the per-type `foreach` fan-out/fan-in that runs the whole evidence graph and yields one published table per cancer type. |

## Evidence branches

| Spec | What it covers |
|------|----------------|
| [expression.md](expression.md) | **Flagship.** `cancer.Evidence.Expression` — GDC tumor-vs-normal over-expression (log2FC + Welch) plus GTEx tumor-specificity; emits the per-gene table + the survival branch's tumor matrix. |
| [mutation.md](mutation.md) | `cancer.Evidence.Mutation` — per-gene somatic-mutation frequency from open GDC SSM aggregation. |
| [drivers.md](drivers.md) | `cancer.Evidence.Driver` — known cancer-driver genes from the intOGen Compendium (CC0); shared across types. |
| [survival.md](survival.md) | `cancer.Evidence.Survival` — log-rank OS association of high vs low expressors, per candidate gene (GDC clinical). |

## Rank & render

| Spec | What it covers |
|------|----------------|
| [ranking.md](ranking.md) | `cancer.Rank.Composite` — the fan-in: weighted z-combination of all evidence branches into one ranked, explainable table. |
| [report.md](report.md) | `cancer.Report.EvidenceTable` — renders the ranked table to a provenance-linked, self-contained HTML page (every score → its facet + dataset). |
| [ffl-examples.md](ffl-examples.md) | **Usage patterns.** A gallery of complete, compile-checked FFL examples over these facets — a minimal graph slice, implied parallelism, `foreach` over cancer types, re-weighting the ranking, mixins, `catch`, `when`. |

---

*See also the repo [`README.md`](../README.md) for the domain summary and
`src/cancer/_lib.py` for the underlying science. The live/queryable interface is
the MCP `fw_capabilities` / `fw_describe_handler` tools; all six facets carry
`Effect`/`Cost`/`Timeout` mixins visible there and in the FFL.*
