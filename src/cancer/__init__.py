"""Cancer domain — a reproducible gene-prioritization EVIDENCE GRAPH.

Given one or more cancer types, fan out over public cancer genomics and produce
one ranked, explainable evidence table where every score links back to the
public dataset and the FFL facet that computed it. Evidence branches (all open,
no auth):

  * Over-expression   — TCGA tumor vs TCGA matched-normal (GDC STAR-Counts)
  * Tumor-specificity — vs GTEx healthy-tissue baseline (cross-cohort, disclosed)
  * Survival          — expression high/low vs GDC clinical survival
  * Mutation          — GDC open simple-somatic-mutation frequency
  * Known driver      — intOGen Compendium of Cancer Genes (CC0)

Discovered by the Facetwork runner via the ``facetwork.domains`` entry point::

    [project.entry-points."facetwork.domains"]
    cancer = "cancer:domain"
"""
from __future__ import annotations

from pathlib import Path

from facetwork.domains import DomainPackage

from .handlers import register_all_registry_handlers

domain = DomainPackage(
    name="cancer",
    ffl_dir=Path(__file__).parent / "ffl",
    register_handlers=register_all_registry_handlers,
)
