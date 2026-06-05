from __future__ import annotations

from typing import Any

from variant_pathogenicity_rater.variant_resolution.schema import ResolvedProtein


def protein_from_vep_transcript_consequence(
    consequence: dict[str, Any],
) -> ResolvedProtein:
    """Parse VEP transcript consequence facts for resolution-only use."""

    hgvs_p = consequence.get("hgvsp")
    terms = consequence.get("consequence_terms") or []
    if isinstance(terms, list):
        consequence_label = ",".join(str(term) for term in terms if term)
    else:
        consequence_label = str(terms or "")
    return ResolvedProtein(
        hgvs_p=hgvs_p,
        protein_accession=hgvs_p.split(":", 1)[0] if isinstance(hgvs_p, str) and ":" in hgvs_p else None,
        consequence=consequence_label or None,
        confidence=0.6 if hgvs_p or consequence_label else 0.0,
        limitations=[
            "VEP transcript consequence was parsed for variant resolution only; it is not ACMG evidence."
        ],
        provenance=[{"source": "Ensembl VEP", "scope": "variant resolution only; not ACMG evidence"}],
    )
