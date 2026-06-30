"""Event-facet handlers for the cancer domain — thin layer over ``_lib``.

Each evidence branch is a facet that writes its per-gene table to the MinIO cache
as parquet and returns the PATH; downstream facets read those paths. So the FFL
workflow graph carries only small paths/scalars and the heavy matrices stay in
object storage — and the graph itself is the explanation.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from .. import _lib, storage
from ..report import render_evidence_table

NS = "cancer"


def _cache(project: str, name: str) -> str:
    return storage.join(storage.cache_root(), project, name)


def _h_expression(p: dict) -> dict:
    project = p["project"]
    info = _lib.SUPPORTED.get(project, {"name": project, "gtex": "Lung"})
    res = _lib.expression_evidence(project, info["gtex"],
                                   tumor_cap=int(p.get("tumor_cap", 520)),
                                   normal_cap=int(p.get("normal_cap", 160)))
    expr_path = _cache(project, "expression.parquet")
    tum_path = _cache(project, "tumor_matrix.parquet")
    storage.write_parquet(expr_path, res.table)
    storage.write_parquet(tum_path, res.tumor_samples)
    return {"expr_path": expr_path, "tumor_matrix_path": tum_path,
            "n_tumor": res.n_tumor, "n_normal": res.n_normal,
            "candidate_count": int(res.table["candidate"].sum()),
            "gtex_tissue": info["gtex"], "project_name": info["name"]}


def _h_mutation(p: dict) -> dict:
    project = p["project"]
    df = _lib.mutation_frequency(project)
    path = _cache(project, "mutation.parquet")
    storage.write_parquet(path, df)
    return {"mutation_path": path, "n_cases": int(df.attrs.get("n_cases", 0)),
            "mutated_gene_count": len(df)}


def _h_driver(p: dict) -> dict:
    import pandas as pd
    drv = _lib.intogen_drivers()
    df = pd.DataFrame([{"gene": g, **v} for g, v in drv.items()]).set_index("gene")
    path = storage.join(storage.cache_root(), "_shared", "intogen_drivers.parquet")
    storage.write_parquet(path, df)
    return {"driver_path": path, "driver_count": len(df)}


def _h_survival(p: dict) -> dict:
    project = p["project"]
    expr = storage.read_parquet(p["expr_path"])
    tumor = storage.read_parquet(p["tumor_matrix_path"])
    cand = expr[expr["candidate"]].index.tolist()
    df = _lib.survival_evidence(project, tumor, cand)
    path = _cache(project, "survival.parquet")
    storage.write_parquet(path, df)
    return {"survival_path": path, "tested_genes": len(df)}


def _h_composite(p: dict) -> dict:
    import pandas as pd
    project = p["project"]
    expr = storage.read_parquet(p["expr_path"])
    mut = storage.read_parquet(p["mutation_path"])
    drvdf = storage.read_parquet(p["driver_path"])
    drivers = {g: {"role": r.get("role", ""), "n_cohorts": r.get("n_cohorts", 0)}
               for g, r in drvdf.iterrows()}
    surv = storage.read_parquet(p["survival_path"]) if p.get("survival_path") else pd.DataFrame(
        columns=["logrank_p", "hi_worse"]).rename_axis("gene")
    weights = {k: float(p[k]) for k in _lib.DEFAULT_WEIGHTS if p.get(k) is not None}
    ranked = _lib.composite_rank(expr, mut, drivers, surv, weights=weights or None,
                                 top_n=int(p.get("top_n", 50)))
    path = _cache(project, "ranked.parquet")
    storage.write_parquet(path, ranked)
    top = ranked.head(10).index.tolist()
    return {"ranked_path": path, "ranked_count": len(ranked), "top_genes": ",".join(map(str, top))}


def _h_report(p: dict) -> dict:
    project = p["project"]
    info = _lib.SUPPORTED.get(project, {"name": project, "gtex": "Lung"})
    ranked = storage.read_parquet(p["ranked_path"])
    weights = {k: float(p.get(k, v)) for k, v in _lib.DEFAULT_WEIGHTS.items()}
    html = render_evidence_table(
        project, p.get("project_name", info["name"]), ranked,
        int(p.get("n_tumor", 0)), int(p.get("n_normal", 0)),
        p.get("gtex_tissue", info["gtex"]), weights,
        datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    slug = project.lower().replace("tcga-", "")
    path = storage.join(storage.maps_root(), slug, "index.html")
    storage.write_text(path, html)
    return {"html_path": path, "region": slug, "gene_count": len(ranked)}


def _wrap(fn, label):
    def handler(payload: dict[str, Any]) -> dict[str, Any]:
        step_log = payload.get("_step_log")
        try:
            res = fn(payload)
            if step_log:
                step_log(f"{label}: {', '.join(f'{k}={v}' for k, v in res.items() if not str(k).endswith('path') or len(str(v)) < 60)}",
                         level="success")
            return res
        except Exception as exc:
            if step_log:
                step_log(f"{label}: {exc}", level="error")
            raise
    return handler


_DISPATCH = {
    f"{NS}.Evidence.Expression": _wrap(_h_expression, "Expression"),
    f"{NS}.Evidence.Mutation": _wrap(_h_mutation, "Mutation"),
    f"{NS}.Evidence.Driver": _wrap(_h_driver, "Driver"),
    f"{NS}.Evidence.Survival": _wrap(_h_survival, "Survival"),
    f"{NS}.Rank.Composite": _wrap(_h_composite, "Composite"),
    f"{NS}.Report.EvidenceTable": _wrap(_h_report, "EvidenceTable"),
}


def handle(payload: dict) -> dict:
    facet = payload["_facet_name"]
    h = _DISPATCH.get(facet)
    if h is None:
        raise ValueError(f"Unknown facet: {facet}")
    return h(payload)


def register_handlers(runner) -> None:
    for facet_name in _DISPATCH:
        runner.register_handler(
            facet_name=facet_name,
            module_uri=f"file://{os.path.abspath(__file__)}",
            entrypoint="handle",
        )


def register_poller(poller) -> None:
    for facet_name, handler in _DISPATCH.items():
        poller.register(facet_name, handler)
