from __future__ import annotations

from typing import Iterable

from variant_pathogenicity_rater.literature_agent.schema import (
    LiteratureSearchInput,
    LiteratureSearchQuery,
)


DEFAULT_CRITERIA = [
    "PS3_BS3",
    "PS2_PM6",
    "PP1",
    "PS4",
    "PM3",
    "PP4",
    "PS1_PM5",
    "PM1",
    "PVS1",
]

CRITERION_KEYWORDS = {
    "PS3_BS3": [
        "functional assay",
        "activity assay",
        "loss of function",
        "normal function",
        "validated assay controls",
    ],
    "PS2_PM6": ["de novo", "trio sequencing", "parentage confirmed", "proband parents"],
    "PP1": ["segregation", "pedigree", "cosegregation", "informative meioses"],
    "PS4": ["case control", "case series", "unrelated cases", "enrichment"],
    "PM3": ["compound heterozygous", "in trans", "biallelic", "phase confirmed"],
    "PP4": ["phenotype specificity", "specific phenotype", "clinical features"],
    "PS1_PM5": ["same amino acid", "same residue", "different missense", "pathogenic"],
    "PM1": ["hotspot", "critical domain", "mutational domain", "functional domain"],
    "PVS1": ["loss of function mechanism", "NMD", "nonsense mediated decay", "haploinsufficiency"],
}


def criteria_for_request(request: LiteratureSearchInput) -> list[str]:
    requested = [item.strip().upper() for item in request.criteria if item.strip()]
    if not requested:
        return list(DEFAULT_CRITERIA)
    aliases = {
        "PS3": "PS3_BS3",
        "BS3": "PS3_BS3",
        "PS2": "PS2_PM6",
        "PM6": "PS2_PM6",
        "PS1": "PS1_PM5",
        "PM5": "PS1_PM5",
    }
    normalized = [aliases.get(item, item) for item in requested]
    return list(dict.fromkeys(normalized))


def variant_aliases(request: LiteratureSearchInput) -> list[str]:
    aliases = [
        request.variant,
        *(request.variant_aliases or []),
    ]
    if request.transcript and request.variant and not request.variant.startswith(request.transcript):
        aliases.append(f"{request.transcript}:{request.variant}")
    return _unique(alias for alias in aliases if alias)


def build_query_plan(request: LiteratureSearchInput) -> list[LiteratureSearchQuery]:
    aliases = variant_aliases(request)
    criteria = criteria_for_request(request)
    plan: list[LiteratureSearchQuery] = []

    if request.search_query:
        plan.append(
            LiteratureSearchQuery(
                source="caller_supplied_query",
                query=request.search_query,
                query_type="free_text",
                aliases_used=aliases,
            )
        )

    for pmid in request.pmids:
        plan.append(
            LiteratureSearchQuery(
                source="local_fixture",
                query=f"PMID:{pmid}",
                query_type="pmid",
                aliases_used=aliases,
            )
        )

    base_terms = [request.gene, request.disease, *aliases]
    base_query = _quoted_join(base_terms)
    if base_query:
        plan.append(
            LiteratureSearchQuery(
                source="local_fixture",
                query=base_query,
                query_type="gene_variant_disease",
                aliases_used=aliases,
            )
        )

    for criterion in criteria:
        keywords = CRITERION_KEYWORDS.get(criterion, [])
        for keyword in keywords[:3]:
            terms = [request.gene, aliases[0] if aliases else request.variant, request.disease, keyword]
            query = _quoted_join(terms)
            plan.append(
                LiteratureSearchQuery(
                    source="pubmed_template",
                    query=query,
                    criterion=criterion,
                    query_type="criterion_keyword",
                    aliases_used=aliases,
                )
            )
            plan.append(
                LiteratureSearchQuery(
                    source="litvar_template",
                    query=query,
                    criterion=criterion,
                    query_type="variant_keyword",
                    aliases_used=aliases,
                )
            )
    return _deduplicate_queries(plan)


def _quoted_join(terms: Iterable[str | None]) -> str:
    return " ".join(f'"{term}"' for term in terms if term)


def _deduplicate_queries(queries: list[LiteratureSearchQuery]) -> list[LiteratureSearchQuery]:
    seen: set[tuple[str, str, str | None]] = set()
    output: list[LiteratureSearchQuery] = []
    for query in queries:
        key = (query.source, query.query, query.criterion)
        if key in seen:
            continue
        seen.add(key)
        output.append(query)
    return output


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))
