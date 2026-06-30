"""Cancer gene-prioritization evidence graph — the science behind the facets.

Every function here pulls an OPEN public dataset and produces a per-gene evidence
table; the FFL facets in ffl/cancer.ffl are thin wrappers that pass MinIO paths
between them so the workflow graph is the explanation. Validated on real
TCGA-LUAD data (CEACAM5 / MAGEA3 / proliferation markers surface as expected).

Sources (all no-auth):
  GDC   https://api.gdc.cancer.gov  — tumor/normal STAR-Counts, survival, SSM
  GTEx  bulk median-TPM GCT          — healthy-tissue baseline
  intOGen Compendium of Cancer Genes — CC0 driver list
"""
from __future__ import annotations

import gzip
import io
import tarfile
import zipfile
from dataclasses import dataclass

import numpy as np
import pandas as pd
import requests

from . import storage

GDC = "https://api.gdc.cancer.gov"
UA = {"User-Agent": "fwh-cancer/0.1 (+github.com/rlemke/facetwork)"}
GTEX_GCT = ("https://storage.googleapis.com/adult-gtex/bulk-gex/v8/rna-seq/"
            "GTEx_Analysis_2017-06-05_v8_RNASeQCv1.1.9_gene_median_tpm.gct.gz")
INTOGEN_ZIP = "https://www.intogen.org/download?file=IntOGen-Drivers-20240920.zip"

# The 9 TCGA projects with a usable (>=~40) matched-normal set, + GTEx tissue.
SUPPORTED = {
    "TCGA-BRCA": {"name": "Breast invasive carcinoma", "gtex": "Breast - Mammary Tissue"},
    "TCGA-KIRC": {"name": "Kidney renal clear cell carcinoma", "gtex": "Kidney - Cortex"},
    "TCGA-LUAD": {"name": "Lung adenocarcinoma", "gtex": "Lung"},
    "TCGA-THCA": {"name": "Thyroid carcinoma", "gtex": "Thyroid"},
    "TCGA-PRAD": {"name": "Prostate adenocarcinoma", "gtex": "Prostate"},
    "TCGA-LUSC": {"name": "Lung squamous cell carcinoma", "gtex": "Lung"},
    "TCGA-LIHC": {"name": "Liver hepatocellular carcinoma", "gtex": "Liver"},
    "TCGA-HNSC": {"name": "Head & neck squamous cell carcinoma", "gtex": "Minor Salivary Gland"},
    "TCGA-COAD": {"name": "Colon adenocarcinoma", "gtex": "Colon - Transverse"},
}

# Tunable composite weights (also surfaced as workflow inputs).
DEFAULT_WEIGHTS = {"overexpression": 1.0, "specificity": 1.0, "survival": 1.0,
                   "mutation": 0.8, "driver": 1.2}


def _req(method, url, **kw):
    kw.setdefault("headers", UA)
    kw.setdefault("timeout", 900)
    r = requests.request(method, url, **kw)
    r.raise_for_status()
    return r


# --- GDC expression ---------------------------------------------------------

def _gdc_expr_files(project, sample_type, cap):
    """[(file_id, case_submitter_id)] of open STAR-Counts files for a sample type."""
    filt = {"op": "and", "content": [
        {"op": "in", "content": {"field": "cases.project.project_id", "value": [project]}},
        {"op": "in", "content": {"field": "data_type", "value": ["Gene Expression Quantification"]}},
        {"op": "in", "content": {"field": "analysis.workflow_type", "value": ["STAR - Counts"]}},
        {"op": "in", "content": {"field": "cases.samples.sample_type", "value": [sample_type]}}]}
    body = {"filters": filt, "fields": "file_id,cases.submitter_id", "size": str(cap), "format": "json"}
    hits = _req("POST", f"{GDC}/files", json=body).json()["data"]["hits"]
    out = []
    for h in hits:
        cid = (h.get("cases") or [{}])[0].get("submitter_id") or h["file_id"]
        out.append((h["file_id"], cid))
    return out


def _parse_star_tsv(txt):
    """{gene_name: tpm_unstranded} from a STAR-Counts TSV (skip header/N_ rows)."""
    out = {}
    hdr = None
    for line in txt.splitlines():
        if not line or line.startswith("#"):
            continue
        c = line.split("\t")
        if c[0] == "gene_id":
            hdr = c
            gi, ti = c.index("gene_name"), c.index("tpm_unstranded")
            continue
        if hdr is None or c[0].startswith("N_"):
            continue
        try:
            out[c[gi]] = float(c[ti])
        except (ValueError, IndexError):
            pass
    return out


def _gdc_download_matrix(files):
    """files=[(file_id, label)] -> DataFrame genes x label (TPM), dup genes meaned.

    Downloads in chunks via the bulk /data tar.gz endpoint; columns keyed by the
    case submitter_id so the tumor matrix doubles as survival input.
    """
    id2label = {fid: lab for fid, lab in files}
    cols = {}
    ids = [f for f, _ in files]
    for i in range(0, len(ids), 100):
        chunk = ids[i:i + 100]
        data = _req("POST", f"{GDC}/data", json={"ids": chunk}).content
        try:
            tf = tarfile.open(fileobj=io.BytesIO(data), mode="r:*")
            for m in tf.getmembers():
                if not m.isfile() or not m.name.endswith((".tsv", ".tsv.gz")):
                    continue
                fid = m.name.split("/")[0]
                raw = tf.extractfile(m).read()
                txt = gzip.decompress(raw).decode() if m.name.endswith(".gz") else raw.decode()
                cols[id2label.get(fid, fid)] = _parse_star_tsv(txt)
        except tarfile.ReadError:  # single file (one id in chunk)
            cols[id2label.get(chunk[0], chunk[0])] = _parse_star_tsv(data.decode())
    df = pd.DataFrame(cols)
    return df.groupby(df.index).mean()


# --- GTEx baseline + intOGen drivers (cached small lookups) ------------------

def gtex_tissue_medians(tissue):
    """{gene_symbol: median TPM} for a GTEx tissue, from the bulk GCT (cached)."""
    raw = gzip.decompress(_req("GET", GTEX_GCT).content).decode()
    lines = raw.splitlines()
    hdr = lines[2].split("\t")
    if tissue not in hdr:
        return {}
    ti, gi = hdr.index(tissue), hdr.index("Description")
    out = {}
    for ln in lines[3:]:
        c = ln.split("\t")
        try:
            out[c[gi]] = float(c[ti])
        except (ValueError, IndexError):
            pass
    return out


def intogen_drivers():
    """{gene_symbol: {role, n_cohorts}} from the intOGen Compendium (CC0)."""
    z = zipfile.ZipFile(io.BytesIO(_req("GET", INTOGEN_ZIP).content))
    name = next(n for n in z.namelist() if n.endswith("Compendium_Cancer_Genes.tsv"))
    df = pd.read_csv(io.BytesIO(z.read(name)), sep="\t")
    sym = "SYMBOL" if "SYMBOL" in df.columns else df.columns[0]
    role = "ROLE" if "ROLE" in df.columns else None
    out = {}
    for _, r in df.iterrows():
        g = str(r[sym])
        out.setdefault(g, {"role": str(r[role]) if role else "", "n_cohorts": 0})
        out[g]["n_cohorts"] += 1
    return out


# --- Evidence branches ------------------------------------------------------

@dataclass
class ExprResult:
    table: pd.DataFrame          # per-gene evidence
    tumor_samples: pd.DataFrame  # genes x case (TPM) — survival input
    n_tumor: int
    n_normal: int


def expression_evidence(project, gtex_tissue, tumor_cap=520, normal_cap=160,
                        min_tumor_tpm=5.0, sig_p=1e-4):
    """Tumor-vs-normal over-expression (GDC) + tumor-specificity vs GTEx healthy
    tissue. Returns per-gene log2fc/pval + a candidate flag, plus the per-sample
    tumor matrix for the survival branch."""
    from scipy import stats
    T = _gdc_download_matrix(_gdc_expr_files(project, "Primary Tumor", tumor_cap))
    N = _gdc_download_matrix(_gdc_expr_files(project, "Solid Tissue Normal", normal_cap))
    genes = T.index.intersection(N.index)
    T, N = T.loc[genes], N.loc[genes]
    t_mean, n_mean = T.mean(axis=1), N.mean(axis=1)
    log2fc = np.log2((t_mean + 1) / (n_mean + 1))
    tl, nl = np.log2(T + 1), np.log2(N + 1)
    _, pval = stats.ttest_ind(tl, nl, axis=1, equal_var=False, nan_policy="omit")
    tab = pd.DataFrame({"tumor_tpm": t_mean, "normal_tpm": n_mean,
                        "log2fc": log2fc, "pval": pd.Series(pval, index=genes)})
    tab["neglog10p"] = -np.log10(tab["pval"].clip(lower=1e-300))
    # tumor-specificity vs GTEx healthy tissue (cross-cohort; disclosed in report)
    gtex = gtex_tissue_medians(gtex_tissue)
    tab["gtex_tpm"] = tab.index.map(lambda g: gtex.get(g, np.nan))
    tab["specificity"] = np.log2((tab["tumor_tpm"] + 1) / (tab["gtex_tpm"] + 1))
    tab["candidate"] = ((tab.tumor_tpm >= min_tumor_tpm) & (tab.log2fc > 1) & (tab.pval < sig_p))
    return ExprResult(tab, T, T.shape[1], N.shape[1])


def mutation_frequency(project):
    """{gene: mutated-sample fraction} from open GDC simple somatic mutations.

    Denominator = the project's case count (GDC /projects summary); the per-gene
    numerator is the count of mutated occurrences (~mutated samples). Note the
    gene facet returns the top-mutated buckets — rarely-mutated genes fall back
    to 0, which is fine for ranking (mutation is z-scored corroborating evidence).
    """
    pj = _req("GET", f"{GDC}/projects/{project}", params={"fields": "summary.case_count"}).json()
    n_cases = (pj.get("data", {}).get("summary", {}) or {}).get("case_count", 0) or 1
    body = {"filters": {"op": "in", "content": {"field": "case.project.project_id", "value": [project]}},
            "facets": "ssm.consequence.transcript.gene.symbol", "size": 0, "format": "json"}
    buckets = _req("POST", f"{GDC}/ssm_occurrences", json=body).json()[
        "data"]["aggregations"]["ssm.consequence.transcript.gene.symbol"]["buckets"]
    rows = [{"gene": b["key"].upper(), "mutated_samples": b["doc_count"],
             "mutation_freq": b["doc_count"] / n_cases} for b in buckets]
    df = pd.DataFrame(rows).set_index("gene")
    df.attrs["n_cases"] = n_cases
    return df


def survival_evidence(project, tumor_samples, genes, min_group=10):
    """Per-gene OS association: split the project's tumor cases into high/low by
    each gene's expression (median), log-rank test. GDC /analysis/survival gives
    {submitter_id, time, censored}. Returns per-gene {logrank_p, hi_worse}."""
    from lifelines.statistics import logrank_test
    surv = _req("GET", f"{GDC}/analysis/survival", params={
        "filters": '{"op":"in","content":{"field":"cases.project.project_id","value":["%s"]}}' % project
    }).json()
    donors = {}
    for d in surv.get("results", [{}])[0].get("donors", []):
        donors[d["submitter_id"]] = (float(d["time"]), 0 if d["censored"] else 1)
    # case submitter_id in tumor_samples columns may be the full TCGA barcode prefix
    cols = {c: c[:12] for c in tumor_samples.columns}  # TCGA-XX-XXXX
    rows = []
    for g in genes:
        if g not in tumor_samples.index:
            continue
        expr = tumor_samples.loc[g]
        med = expr.median()
        hi_t, hi_e, lo_t, lo_e = [], [], [], []
        for col, val in expr.items():
            cid = cols[col]
            if cid not in donors:
                continue
            t, e = donors[cid]
            (hi_t if val >= med else lo_t).append(t)
            (hi_e if val >= med else lo_e).append(e)
        if len(hi_t) < min_group or len(lo_t) < min_group:
            continue
        lr = logrank_test(hi_t, lo_t, event_observed_A=hi_e, event_observed_B=lo_e)
        # median survival direction: lower median time in hi group => high expr worse
        hi_med = np.median(hi_t)
        lo_med = np.median(lo_t)
        rows.append({"gene": g, "logrank_p": lr.p_value, "hi_worse": bool(hi_med < lo_med)})
    return pd.DataFrame(rows).set_index("gene") if rows else pd.DataFrame(
        columns=["logrank_p", "hi_worse"]).rename_axis("gene")


# --- Composite rank ---------------------------------------------------------

def _z(s):
    s = s.astype(float)
    sd = s.std(ddof=0)
    return (s - s.mean()) / sd if sd > 0 else s * 0.0


def composite_rank(expr, mut, drivers, surv, weights=None, top_n=50):
    """Merge the evidence branches into one ranked, explainable table."""
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    df = expr[expr["candidate"]].copy()
    df["mutation_freq"] = df.index.map(lambda g: float(mut["mutation_freq"].get(g, 0.0)) if g in mut.index else 0.0)
    df["mutated_samples"] = df.index.map(lambda g: int(mut["mutated_samples"].get(g, 0)) if g in mut.index else 0)
    df["driver_role"] = df.index.map(lambda g: drivers.get(g, {}).get("role", ""))
    df["is_driver"] = df.index.map(lambda g: g in drivers)
    df["survival_p"] = df.index.map(lambda g: float(surv["logrank_p"].get(g, np.nan)) if g in surv.index else np.nan)
    df["survival_hi_worse"] = df.index.map(lambda g: bool(surv["hi_worse"].get(g, False)) if g in surv.index else False)
    # signed survival score: high-expression-worse + significant => positive
    surv_score = (-np.log10(df["survival_p"].clip(lower=1e-300))).fillna(0.0)
    surv_score = surv_score * df["survival_hi_worse"].map(lambda b: 1.0 if b else -0.3)
    score = (w["overexpression"] * _z(df["log2fc"])
             + w["specificity"] * _z(df["specificity"].fillna(0.0))
             + w["survival"] * _z(surv_score)
             + w["mutation"] * _z(np.log1p(df["mutated_samples"]))
             + w["driver"] * df["is_driver"].astype(float))
    df["composite_score"] = score
    df = df.sort_values("composite_score", ascending=False)
    df.insert(0, "rank", range(1, len(df) + 1))
    return df.head(top_n)
