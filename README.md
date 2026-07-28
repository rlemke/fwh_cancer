# fwh_cancer — cancer gene-prioritization evidence graph (Facetwork domain)

Given one or more cancer types, fans out over open public cancer genomics
(TCGA/GDC tumor+normal expression, GTEx healthy baseline, GDC survival + somatic
mutations, intOGen drivers) and produces one **ranked, explainable evidence
table** per type — every score links back to its public dataset and the FFL
facet that computed it. Workflow: `cancer.workflows.PrioritizeGenes`.

## FFL at a glance

The domain is driven from [FFL](https://github.com/rlemke/facetwork/blob/main/docs/reference/language/grammar.md),
Facetwork's workflow language. A step is `name = Facet(args)`; steps that
reference each other are ordered, steps that don't run **in parallel**:

```ffl
namespace my.cancer {

    use cancer.Evidence
    use cancer.Rank

    /** Three evidence branches in parallel, then fan in to a ranking. */
    workflow RankLung(project: String = "TCGA-LUAD") => (ranked_path: String) andThen {

        expr = cancer.Evidence.Expression(project = $.project)   // parallel
        mut = cancer.Evidence.Mutation(project = $.project)      // parallel
        drv = cancer.Evidence.Driver()                           // parallel

        ranked = cancer.Rank.Composite(                          // fan-in
            project = $.project,
            expr_path = expr.expr_path,
            mutation_path = mut.mutation_path,
            driver_path = drv.driver_path,
            survival_path = "",
            top_n = 50)

        yield RankLung(ranked_path = ranked.ranked_path)
    }
}
```

```bash
fw ffl run --primary my.ffl --library src/cancer/ffl/cancer.ffl \
  --workflow my.cancer.RankLung
```

📖 **[docs/ffl-examples.md](docs/ffl-examples.md)** — the full example gallery:
`foreach` fan-out over cancer types, tuning the ranking weights, call-time mixins
(timeout/retry), `catch` to degrade instead of fail, `when` guards, and reusing
the shipped workflow. Every snippet there is compile-checked.

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
