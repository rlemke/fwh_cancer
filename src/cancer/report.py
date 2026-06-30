"""Ranked evidence-table renderer.

Not "a list of genes" — a table where every score column links back to (a) the
FFL facet that computed it and (b) the live public-dataset query, plus an
"About this data" popup (gallery parity) carrying full provenance + the
TCGA-vs-GTEx batch-effect disclosure.
"""
from __future__ import annotations

import html
import json

# column key -> (header, the FFL facet that produced it, dataset label, decimals)
COLUMNS = [
    ("rank", "#", "", "", 0),
    ("gene", "Gene", "", "", None),
    ("composite_score", "Composite", "cancer.Rank.Composite", "", 2),
    ("log2fc", "Over-expr (log2FC)", "cancer.Evidence.Expression", "GDC tumor vs normal", 2),
    ("neglog10p", "−log10 p", "cancer.Evidence.Expression", "GDC", 1),
    ("specificity", "Tumor-specificity vs GTEx", "cancer.Evidence.Expression", "GTEx healthy tissue", 2),
    ("mutation_freq", "Mutation freq", "cancer.Evidence.Mutation", "GDC SSM", 3),
    ("survival_p", "Survival p (hi-expr)", "cancer.Evidence.Survival", "GDC clinical", 4),
    ("driver_role", "Known driver", "cancer.Evidence.Driver", "intOGen", None),
]


def _ds_link(project, gene):
    """Per-(gene,project) live dataset links for the popup / cell tooltips."""
    g = html.escape(gene)
    return (f"https://portal.gdc.cancer.gov/genes/{g}",
            f"https://gtexportal.org/home/gene/{g}")


def render_evidence_table(project, project_name, ranked, n_tumor, n_normal,
                          gtex_tissue, weights, generated):
    rows = []
    for gene, r in ranked.iterrows():
        gdc_url, gtex_url = _ds_link(project, gene)
        cells = []
        for key, _hdr, _facet, _ds, dec in COLUMNS:
            if key == "gene":
                v = (f"<a href='{gdc_url}' target='_blank' title='GDC gene page'>{html.escape(str(gene))}</a>")
            elif key == "rank":
                v = str(int(r["rank"]))
            elif key == "driver_role":
                role = str(r.get("driver_role") or "")
                v = (f"<span class='drv'>{html.escape(role)}</span>" if role and role != "nan"
                     else ("<span class='drv'>driver</span>" if r.get("is_driver") else "—"))
            elif key == "survival_p":
                p = r.get("survival_p")
                if p is None or (isinstance(p, float) and (p != p)):
                    v = "—"
                else:
                    arrow = "↑worse" if r.get("survival_hi_worse") else "↓"
                    v = f"{p:.1e} <span class='sv'>{arrow}</span>"
            else:
                val = r.get(key)
                try:
                    v = f"{float(val):.{dec}f}" if dec is not None else html.escape(str(val))
                except (TypeError, ValueError):
                    v = "—"
            cells.append(f"<td data-k='{key}'>{v}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")

    head = "".join(
        f"<th title='facet: {f} · source: {ds}'>{html.escape(h)}"
        + (f"<span class='src'>{html.escape(ds)}</span>" if ds else "") + "</th>"
        for _k, h, f, ds, _d in COLUMNS)

    wjson = ", ".join(f"{k}={v}" for k, v in weights.items())
    note = (
        f"This is a reproducible <b>evidence graph</b>, not just a gene list: each column is one "
        f"FFL facet computing one score from one open public dataset, and every score traces back to "
        f"it. <b>Over-expression</b> = TCGA <b>{html.escape(project)}</b> primary tumors "
        f"(<b>{n_tumor}</b> samples) vs TCGA matched solid-tissue normal (<b>{n_normal}</b> samples), "
        f"GDC STAR-Counts TPM — <i>same pipeline, no batch effect</i>. <b>Tumor-specificity</b> compares "
        f"tumor TPM to <b>GTEx</b> healthy <b>{html.escape(gtex_tissue)}</b> median — this is a "
        f"<b>cross-cohort</b> signal (different pipeline) shown as corroboration, not the primary "
        f"fold-change. <b>Survival</b> = log-rank of high vs low expressors against GDC clinical OS "
        f"(↑worse = high expression predicts worse survival). <b>Mutation freq</b> = fraction of mutated "
        f"cases (GDC open SSM). <b>Known driver</b> = intOGen Compendium of Cancer Genes (CC0). "
        f"Composite = weighted z-combination ({html.escape(wjson)}). Candidates are filtered to "
        f"genes expressed in tumor, over-expressed, and significant. Generated {html.escape(generated)} "
        f"by an FFL workflow on <a href='https://github.com/rlemke/facetwork'>Facetwork</a>."
    )

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>{html.escape(project_name)} — gene evidence</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
 body{{margin:0;font:14px/1.45 system-ui,sans-serif;color:#1a1a1a;background:#f6f7f9}}
 header{{background:#fff;padding:16px 22px;box-shadow:0 1px 4px rgba(0,0,0,.12)}}
 header h1{{margin:0;font-size:19px}} header p{{margin:4px 0 0;color:#666;font-size:13px}}
 .wrap{{padding:18px 22px}}
 table{{border-collapse:collapse;width:100%;background:#fff;box-shadow:0 1px 4px rgba(0,0,0,.1);font-size:13px}}
 th,td{{padding:7px 10px;text-align:right;border-bottom:1px solid #eee;white-space:nowrap}}
 th{{position:sticky;top:0;background:#263238;color:#fff;text-align:right;font-weight:600;cursor:help;vertical-align:bottom}}
 th .src{{display:block;font-weight:400;font-size:10px;color:#9fb3bd;margin-top:2px}}
 td[data-k=gene]{{text-align:left;font-weight:600}} th:nth-child(2){{text-align:left}}
 td[data-k=gene] a{{color:#0b62c4;text-decoration:none}}
 tr:hover td{{background:#f0f6ff}}
 .drv{{background:#fde7e9;color:#b3122a;border-radius:3px;padding:1px 6px;font-size:11px}}
 .sv{{color:#b3122a;font-size:11px}}
 .infobtn{{margin-top:8px;padding:6px 11px;font-size:13px;cursor:pointer;background:#fff8e1;border:1px solid #f6c343;border-radius:4px;color:#5d4b00}}
 .modal{{position:fixed;inset:0;z-index:5;background:rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center}}
 .modalcard{{background:#fff;max-width:560px;margin:16px;padding:18px 22px 22px;border-radius:10px;box-shadow:0 4px 24px rgba(0,0,0,.4);position:relative;max-height:82vh;overflow:auto}}
 .modalcard h2{{margin:0 0 8px;font-size:17px}} .modalclose{{position:absolute;top:6px;right:12px;border:none;background:none;font-size:24px;cursor:pointer;color:#999}}
</style></head><body>
<header><h1>{html.escape(project_name)} — ranked gene evidence</h1>
<p>{html.escape(project)} · {len(ranked)} ranked genes · over-expressed in tumor, supported by survival / mutation / known-driver evidence</p>
<button id="infobtn" class="infobtn">&#8505;&#65039; About this data &amp; how to read every score</button></header>
<div class="wrap"><table><thead><tr>{head}</tr></thead><tbody>
{chr(10).join(rows)}
</tbody></table></div>
<div id="infomodal" class="modal"><div class="modalcard"><button id="infoclose" class="modalclose">&times;</button>
<h2>About this data</h2><div>{note}</div></div></div>
<script>
const _im=document.getElementById('infomodal');
const ib=document.getElementById('infobtn'),ic=document.getElementById('infoclose');
if(ib)ib.onclick=()=>{{_im.style.display='flex';}};
if(ic)ic.onclick=()=>{{_im.style.display='none';}};
_im.onclick=e=>{{if(e.target===_im)_im.style.display='none';}};
</script></body></html>"""
