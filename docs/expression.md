# Over-expression & Tumor-specificity

**Namespace:** `cancer.Evidence` (facet `Expression`) ·
**FFL:** `src/cancer/ffl/cancer.ffl` ·
**Handler:** `src/cancer/handlers/cancer_handlers.py` (`_h_expression`) ·
**Science:** `src/cancer/_lib.py` (`expression_evidence`, `_gdc_expr_files`,
`_gdc_download_matrix`, `_parse_star_tsv`, `gtex_tissue_medians`)

## Overview

The **flagship evidence branch**. It answers "which genes are turned *up* in this
tumor relative to matched healthy tissue, and how tumor-specific is that?" It is
the widest and slowest facet: it downloads two RNA-seq expression matrices from
GDC (primary tumor + matched solid-tissue normal), computes a per-gene log2
fold-change with a Welch significance test, and then adds a **tumor-specificity**
score against the GTEx healthy-tissue baseline. It also emits the per-sample tumor
matrix that the [survival](survival.md) branch consumes, so it is the root of the
per-type sub-graph — the [ranking](ranking.md) `candidate` set is drawn from
exactly the genes this facet flags.

## How it works

`expression_evidence(project, gtex_tissue, tumor_cap=520, normal_cap=160,
min_tumor_tpm=5.0, sig_p=1e-4)` (`_lib.py`):

1. **Find files** — `_gdc_expr_files(project, sample_type, cap)` POSTs to
   `GDC /files` filtering on `cases.project.project_id == project`,
   `data_type == "Gene Expression Quantification"`,
   `analysis.workflow_type == "STAR - Counts"`, and
   `cases.samples.sample_type` = `Primary Tumor` (then `Solid Tissue Normal`).
   Each hit yields `(file_id, case_submitter_id)`; the submitter id keys the
   columns so the tumor matrix doubles as survival input.
2. **Download matrices** — `_gdc_download_matrix` POSTs file-id chunks of 100 to
   `GDC /data`, opens the returned `tar.gz`, and `_parse_star_tsv` reads
   `tpm_unstranded` keyed by `gene_name` (skipping `#`, `gene_id` header, and
   `N_*` summary rows). Duplicate gene symbols are mean-collapsed
   (`groupby(index).mean()`). Result: two DataFrames of genes × samples (TPM).
3. **Fold-change + significance** — intersect the gene sets, take per-gene means,
   `log2fc = log2((tumor_mean+1)/(normal_mean+1))`, and a Welch (unequal-variance)
   t-test on `log2(TPM+1)` via `scipy.stats.ttest_ind` (`nan_policy="omit"`).
   `neglog10p = -log10(pval.clip(lower=1e-300))`.
4. **Tumor-specificity vs GTEx** — `gtex_tissue_medians(tissue)` pulls the GTEx
   bulk median-TPM GCT and `specificity = log2((tumor_tpm+1)/(gtex_tpm+1))`. This
   is a **cross-cohort** signal (different pipeline) and is disclosed as such in
   the report.
5. **Candidate flag** — `candidate = tumor_tpm >= 5.0 AND log2fc > 1 AND
   pval < 1e-4`. Only candidates flow to ranking/survival.

Data shape: `GDC STAR-Counts tar.gz → genes×samples TPM matrix → per-gene
evidence table (parquet path) + tumor matrix (parquet path) + scalars`.

## Fan-out

**One distributed task per cancer type** — no `foreach` inside the facet. The
whole evidence graph (including this branch) is fanned per type by
`cancer.workflows.PrioritizeGenes` (`foreach ct in $.cancer_types`, see
[workflow](workflow.md)). Within a type this is a single, heavy task: two bulk
matrix downloads of up to `tumor_cap`=520 + `normal_cap`=160 samples, hence the
40-minute timeout.

## Data & fields

- **Source:** GDC `/files` + `/data` (open STAR-Counts) and the GTEx v8 bulk
  median-TPM GCT (`GTEx_Analysis_2017-06-05_v8_RNASeQCv1.1.9_gene_median_tpm.gct.gz`
  from `storage.googleapis.com/adult-gtex`).
- **Filters:** TCGA `project_id`, `sample_type ∈ {Primary Tumor, Solid Tissue
  Normal}`, workflow `STAR - Counts`, `data_type = Gene Expression Quantification`.
- **Per-gene fields produced:** `tumor_tpm`, `normal_tpm`, `log2fc`, `pval`,
  `neglog10p`, `gtex_tpm`, `specificity`, `candidate` (bool).
- **GTEx tissue** is looked up per project from `_lib.SUPPORTED` (e.g. `TCGA-LUAD`
  → `Lung`, `TCGA-BRCA` → `Breast - Mammary Tissue`).

## External libraries / binaries

All **pip**, no binaries:

- **`requests`** — GDC/GTEx HTTP (`_req`, 900 s timeout, custom UA).
- **`pandas` / `numpy`** — matrices, fold-change, log transforms.
- **`scipy.stats`** — `ttest_ind` (Welch), imported lazily inside
  `expression_evidence`.
- **`pyarrow`** — parquet serialization of the two output tables (via
  `storage.write_parquet`).

## Facets & workflows

| Facet | Kind | Effect / Cost / Timeout | Purpose |
|---|---|---|---|
| `cancer.Evidence.Expression(project, tumor_cap=520, normal_cap=160)` | event | external / **expensive** / 40 min | Over-expression + tumor-specificity; emits the per-gene table + per-sample tumor matrix |

Returns: `expr_path`, `tumor_matrix_path`, `n_tumor`, `n_normal`,
`candidate_count`, `gtex_tissue`, `project_name`.

## Cache / output

Two parquet tables per project, written via `storage.write_parquet` to
`cache_root()`:

- `expr_path` → `$FW_DATA_ROOT/cache/cancer/<project>/expression.parquet`
  (remote) or `<root>/cancer-cache/<project>/expression.parquet` (local).
- `tumor_matrix_path` → `.../<project>/tumor_matrix.parquet` — the survival
  branch's input.

On the fleet these land in the shared MinIO object store; locally they fall back
to a host path (see `storage.py`).

## Gotchas & notes

- **Cross-cohort specificity, disclosed.** Tumor-vs-normal fold-change is *within*
  GDC STAR-Counts (same pipeline, no batch effect); tumor-specificity vs GTEx is a
  **different pipeline/cohort** and is shown as corroboration, not the primary
  signal. The report's "About this data" popup states this explicitly.
- **Matched-normal availability drives project choice.** `_lib.SUPPORTED` is
  curated to the 9 TCGA projects with a usable (~≥40) matched solid-tissue-normal
  set; a project with too few normals yields an unreliable fold-change.
- **Caps bound cost, not correctness.** `tumor_cap`/`normal_cap` cap the sample
  count for download size; means are over whatever is fetched.
- **Column keys are case submitter ids** so the same tumor matrix feeds
  [survival](survival.md) without re-download — the barcode prefix is truncated to
  `TCGA-XX-XXXX` there.
- **GTEx tissue must match a GCT column** — an unknown tissue returns `{}`, so
  `specificity` becomes NaN (handled downstream as 0 in the z-combination).

## Related specs

- [survival.md](survival.md) — consumes `tumor_matrix_path`; splits candidates
  high/low by expression.
- [ranking.md](ranking.md) — the `candidate`-flagged genes are the ranking set;
  `log2fc` and `specificity` are z-scored inputs.
- [workflow.md](workflow.md) — the per-type fan-out that drives this branch.
- [report.md](report.md) — surfaces `log2fc` / `neglog10p` / `specificity`
  columns, each linked back to this facet.
