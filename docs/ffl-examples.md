# FFL Examples — `cancer`

Every numbered scenario is a **complete, compilable FFL file**. Copy one into
`my.ffl` and run it:

```bash
fw ffl run --primary my.ffl \
  --library ~/fw_handlers/fwh_cancer/src/cancer/ffl/cancer.ffl \
  --workflow my.cancer.<WorkflowName>
```

A runner serving the `cancer` namespace must be up
(`fw runner start --domain cancer`). Every block below is compile-checked against
`src/cancer/ffl/cancer.ffl`.

New to the language? Start with the
[FFL grammar](https://github.com/rlemke/facetwork/blob/main/docs/reference/language/grammar.md)
and the [canonical examples](https://github.com/rlemke/facetwork/tree/main/examples/canonical).

---

## The facets at a glance

An evidence **graph**, not a linear pipeline: four independent evidence branches
fan in to one ranking step. That shape is what makes this domain a good FFL
teaching example — the parallelism is implied by the references, not declared.

| Declaration | Signature (abridged) | Does |
|---|---|---|
| `cancer.Evidence.Expression` | `(project, tumor_cap = 520, normal_cap = 160) => (expr_path, tumor_matrix_path, n_tumor, n_normal, candidate_count, gtex_tissue, project_name)` | GDC tumor-vs-normal over-expression + GTEx tumor-specificity |
| `cancer.Evidence.Mutation` | `(project) => (mutation_path, n_cases, mutated_gene_count)` | Per-gene somatic-mutation frequency (open GDC SSM) |
| `cancer.Evidence.Driver` | `() => (driver_path, driver_count)` | intOGen known-driver genes (shared across types) |
| `cancer.Evidence.Survival` | `(project, expr_path, tumor_matrix_path) => (survival_path, tested_genes)` | Log-rank OS association, high vs low expressors |
| `cancer.Rank.Composite` | `(project, expr_path, mutation_path, driver_path, survival_path, top_n = 50, overexpression = 1.0, specificity = 1.0, survival = 1.0, mutation = 0.8, driver = 1.2) => (ranked_path, ranked_count, top_genes)` | Weighted z-combination → one ranked table |
| `cancer.Report.EvidenceTable` | `(project, ranked_path, n_tumor, n_normal, gtex_tissue, project_name) => (html_path, region, gene_count)` | Provenance-linked HTML report |
| `cancer.workflows.PrioritizeGenes` | `(cancer_types: [String] = ["TCGA-LUAD"], top_n = 50)` | The shipped entry point — the whole graph, per type |

---

## 1. Run what ships — no FFL to write

```bash
fw ffl seed --include cancer

# default: lung adenocarcinoma
fw ffl run --primary ~/fw_handlers/fwh_cancer/src/cancer/ffl/cancer.ffl \
  --workflow cancer.workflows.PrioritizeGenes

# several types, fanned out across the fleet
fw ffl run --primary ~/fw_handlers/fwh_cancer/src/cancer/ffl/cancer.ffl \
  --workflow cancer.workflows.PrioritizeGenes \
  --inputs '{"cancer_types": ["TCGA-LUAD", "TCGA-BRCA", "TCGA-KIRC"], "top_n": 100}'
```

Write FFL when you want a different *shape* — a subset of the evidence branches,
your own ranking weights, extra error handling, or composition with another domain.

## 2. A minimal slice of the graph

Not every question needs all four branches. Here is over-expression → ranking →
report, with the mutation/driver/survival inputs left empty.

```ffl
namespace my.cancer {

    use cancer.Evidence
    use cancer.Rank
    use cancer.Report

    /** Expression-only prioritization for one cancer type. */
    workflow ExpressionOnly(project: String = "TCGA-LUAD", top_n: Long = 50) => (html_path: String, genes: Int) andThen {

        expr = cancer.Evidence.Expression(project = $.project)

        ranked = cancer.Rank.Composite(
            project = $.project,
            expr_path = expr.expr_path,
            mutation_path = "",
            driver_path = "",
            survival_path = "",
            top_n = $.top_n)

        table = cancer.Report.EvidenceTable(
            project = $.project,
            ranked_path = ranked.ranked_path,
            n_tumor = expr.n_tumor,
            n_normal = expr.n_normal,
            gtex_tissue = expr.gtex_tissue,
            project_name = expr.project_name)

        yield ExpressionOnly(html_path = table.html_path, genes = table.gene_count)
    }
}
```

Rules visible above: `=>` sits on the **same line** as the closing `)`; references
are always `step.field`; `$.project` reads the workflow's own parameter.

## 3. Parallelism is implied by the references

`Expression`, `Mutation` and `Driver` reference nothing from each other, so the
runtime dispatches them **concurrently** — three runners can work at once.
`Survival` references `expr`, so it waits for it; `Composite` references all four,
so it is the fan-in.

```ffl
namespace my.cancer {

    use cancer.Evidence
    use cancer.Rank
    use cancer.Report

    /** The full evidence graph for one type: 3 branches in parallel → fan-in. */
    workflow FullGraph(project: String = "TCGA-LUAD", top_n: Long = 50) => (html_path: String, genes: Int) andThen {

        expr = cancer.Evidence.Expression(project = $.project)   // runs in parallel
        mut = cancer.Evidence.Mutation(project = $.project)      // runs in parallel
        drv = cancer.Evidence.Driver()                           // runs in parallel

        // waits on expr, because it references it
        surv = cancer.Evidence.Survival(
            project = $.project,
            expr_path = expr.expr_path,
            tumor_matrix_path = expr.tumor_matrix_path)

        // fan-in: references all four branches
        ranked = cancer.Rank.Composite(
            project = $.project,
            expr_path = expr.expr_path,
            mutation_path = mut.mutation_path,
            driver_path = drv.driver_path,
            survival_path = surv.survival_path,
            top_n = $.top_n)

        table = cancer.Report.EvidenceTable(
            project = $.project,
            ranked_path = ranked.ranked_path,
            n_tumor = expr.n_tumor,
            n_normal = expr.n_normal,
            gtex_tissue = expr.gtex_tissue,
            project_name = expr.project_name)

        yield FullGraph(html_path = table.html_path, genes = table.gene_count)
    }
}
```

You never write "run these in parallel" — you write the data dependencies and the
runtime derives the schedule.

## 4. Fan out over cancer types — `foreach`

`andThen foreach v in <list>` runs the entire block once per element, each as its
own set of runtime steps that the fleet claims in parallel. Here the `foreach`
hangs off the **workflow**, so the loop body's container *is* the workflow: the
loop variable and the workflow's parameters are both reached with a single `$`
(`$.ct`, `$.top_n`). Only when a `foreach` hangs off a *step* does `$$` come into
play — see the `catch` and `when` examples below.

```ffl
namespace my.cancer {

    use cancer.Evidence
    use cancer.Rank

    /** One evidence graph per cancer type, fanned out across the fleet. */
    workflow RankMany(cancer_types: Json, top_n: Long = 50) => (built: [String]) andThen foreach ct in $.cancer_types {

        expr = cancer.Evidence.Expression(project = $.ct)

        ranked = cancer.Rank.Composite(
            project = $.ct,
            expr_path = expr.expr_path,
            mutation_path = "",
            driver_path = "",
            survival_path = "",
            top_n = $.top_n)

        yield RankMany(built = [ranked.ranked_path])
    }
}
```

```bash
fw ffl run --primary my.ffl --library …/cancer.ffl --workflow my.cancer.RankMany \
  --inputs '{"cancer_types": ["TCGA-LUAD", "TCGA-BRCA"], "top_n": 100}'
```

## 5. Tune the ranking weights

`Composite`'s weights are ordinary parameters — re-weighting the evidence is a
config change at the call site, not a code change.

```ffl
namespace my.cancer {

    use cancer.Evidence
    use cancer.Rank

    /** Weight survival evidence heavily and ignore mutation frequency. */
    workflow SurvivalWeighted(project: String = "TCGA-LUAD") => (ranked_path: String, count: Int) andThen {

        expr = cancer.Evidence.Expression(project = $.project)

        surv = cancer.Evidence.Survival(
            project = $.project,
            expr_path = expr.expr_path,
            tumor_matrix_path = expr.tumor_matrix_path)

        ranked = cancer.Rank.Composite(
            project = $.project,
            expr_path = expr.expr_path,
            mutation_path = "",
            driver_path = "",
            survival_path = surv.survival_path,
            overexpression = 0.5,
            specificity = 0.5,
            survival = 3.0,
            mutation = 0.0,
            driver = 1.0,
            top_n = 100)

        yield SurvivalWeighted(ranked_path = ranked.ranked_path, count = ranked.ranked_count)
    }
}
```

## 6. Call-time mixins — timeouts and retries

`Expression` ships `with Timeout(minutes = 40)` and `with Cost(tier =
"expensive")`. The **call site** can override for one particular use — useful for
the large TCGA projects.

```ffl
namespace my.cancer {

    use cancer.Evidence

    /** BRCA is big: more time, and retry GDC hiccups. */
    workflow PatientExpression(project: String = "TCGA-BRCA") => (candidates: Int) andThen {

        expr = cancer.Evidence.Expression(project = $.project, tumor_cap = 1000) with Timeout(minutes = 120) with Retry(maxAttempts = 3, backoffSeconds = 120)

        yield PatientExpression(candidates = expr.candidate_count)
    }
}
```

## 7. Degrade instead of failing — `catch`

`catch` fires when its step errors after retries are exhausted. Because the
branches are independent, catching one lets the rest of the graph finish.

```ffl
namespace my.cancer {

    use cancer.Evidence
    use cancer.Rank

    /** If the survival branch fails, still produce a ranking without it. */
    workflow SurvivalOptional(project: String = "TCGA-LUAD") => (ranked_path: String) andThen {

        expr = cancer.Evidence.Expression(project = $.project)

        surv = cancer.Evidence.Survival(
            project = $.project,
            expr_path = expr.expr_path,
            tumor_matrix_path = expr.tumor_matrix_path) catch {
            yield SurvivalOptional(ranked_path = "")
        }

        ranked = cancer.Rank.Composite(
            project = $.project,
            expr_path = expr.expr_path,
            mutation_path = "",
            driver_path = "",
            survival_path = surv.survival_path)

        yield SurvivalOptional(ranked_path = ranked.ranked_path)
    }
}
```

## 8. Branch on a result — `when`

A `when` block hangs off the step it inspects: inside a case `$` is that step and
`$$` reaches the workflow. Every `when` needs a default case, last.

```ffl
namespace my.cancer {

    use cancer.Evidence
    use cancer.Rank

    /** Only rank when the tumor/normal cohort is big enough to mean anything. */
    workflow GuardedRank(project: String = "TCGA-LUAD", min_normals: Int = 20) => (status: String, ranked_path: String) andThen {

        expr = cancer.Evidence.Expression(project = $.project) andThen when {
            case $.n_normal >= $$.min_normals => {
                ranked = cancer.Rank.Composite(
                    project = $$.project,
                    expr_path = $.expr_path,
                    mutation_path = "",
                    driver_path = "",
                    survival_path = "")
                yield GuardedRank(status = "ranked", ranked_path = ranked.ranked_path)
            }
            case _ => {
                yield GuardedRank(status = "too_few_normals", ranked_path = "")
            }
        }
    }
}
```

## 9. Reuse the shipped workflow

```ffl
namespace my.cancer {

    use cancer.workflows

    /** Wrap the shipped graph and reshape its result. */
    workflow PrioritizeWithHeadline(cancer_types: Json) => (headline: String) andThen {

        run = cancer.workflows.PrioritizeGenes(top_n = 100)

        yield PrioritizeWithHeadline(headline = "prioritization: " ++ run.status)
    }
}
```

---

## Cheat sheet

| You want to… | Write |
|---|---|
| Read a workflow/step parameter | `$.name` (`$$.name` one level out) |
| Read a previous step's result | `stepname.field` |
| Run steps in parallel | write them with no reference between them |
| Force an order | reference a field of the first from the second |
| Fan out over a list | `workflow W(items: Json) … andThen foreach i in $.items { … }` |
| More time / retries for one call | `… with Timeout(minutes = 120) with Retry(maxAttempts = 3, backoffSeconds = 120)` |
| Handle a step failure | `step = Facet(…) catch { yield … }` |
| Branch | `step = Facet(…) andThen when { case <bool> => { … } case _ => { … } }` |
| Concatenate strings | `a ++ b` |

**Validate before you run:** `fw ffl compile --check --primary my.ffl --library <this domain's .ffl>` or MCP `fw_validate`. Every error
carries a `rule_id` — fetch `fw://docs/rules/{rule_id}` for a wrong/right pair.

## See also

- [`docs/README.md`](README.md) — per-feature specs (one per evidence branch)
- [`docs/workflow.md`](workflow.md) — what `PrioritizeGenes` does, step by step
- [FFL grammar](https://github.com/rlemke/facetwork/blob/main/docs/reference/language/grammar.md) ·
  [canonical examples](https://github.com/rlemke/facetwork/tree/main/examples/canonical) ·
  [relative `$`-scoping](https://github.com/rlemke/facetwork/blob/main/docs/architecture/ffl-relative-scoping.md)
- `src/cancer/ffl/cancer.ffl` — the source of truth for every signature above
