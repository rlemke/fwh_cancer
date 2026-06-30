# fwh_cancer — cancer gene-prioritization evidence graph (Facetwork domain)

Given one or more cancer types, fans out over open public cancer genomics
(TCGA/GDC tumor+normal expression, GTEx healthy baseline, GDC survival + somatic
mutations, intOGen drivers) and produces one **ranked, explainable evidence
table** per type — every score links back to its public dataset and the FFL
facet that computed it. Workflow: `cancer.workflows.PrioritizeGenes`.
