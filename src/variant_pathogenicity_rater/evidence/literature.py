from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from hashlib import sha1
from typing import Any

from pydantic import Field

from variant_pathogenicity_rater.data_sources.provenance import (
    attach_provenance_to_source,
    provenance_from_raw_record,
)
from variant_pathogenicity_rater.schemas.acmg import EvidenceCode
from variant_pathogenicity_rater.schemas.common import AuditTrail, ReviewFlag, SchemaModel
from variant_pathogenicity_rater.schemas.evidence import (
    EvidenceDirection,
    EvidenceItem,
    EvidenceSource,
    EvidenceStrength,
    LiteratureCandidateEvidenceType,
    LiteratureClaim,
    LiteratureEvidence,
    LiteratureEvidenceQuality,
    LiteratureEvidenceType,
)
from variant_pathogenicity_rater.schemas.variant import GeneDiseaseContext, Variant


LITERATURE_REVIEW_NOTE = (
    "Literature evidence is candidate-only in this phase. Do not automatically apply "
    "PS3, BS3, PS2, PM6, PP1, PS4, or PP4 without qualified human review."
)


class LiteratureQuery(SchemaModel):
    gene: str | None = None
    pmid: str | None = None
    hgvs_c: str | None = None
    hgvs_p: str | None = None
    chromosome: str | None = None
    position: int | None = Field(default=None, ge=1)
    ref: str | None = None
    alt: str | None = None
    genome_build: str | None = None
    disease_name: str | None = None
    phenotype_terms: list[str] = Field(default_factory=list)
    include_case_reports: bool = True

    @classmethod
    def from_variant(
        cls,
        variant: Variant,
        context: GeneDiseaseContext | None = None,
    ) -> "LiteratureQuery":
        return cls(
            gene=variant.gene_symbol,
            hgvs_c=variant.hgvs_c,
            hgvs_p=variant.hgvs_p,
            chromosome=variant.chrom,
            position=variant.pos,
            ref=variant.ref,
            alt=variant.alt,
            genome_build=str(variant.genome_build),
            disease_name=context.disease_name if context else None,
            phenotype_terms=context.phenotype_terms if context else [],
        )

    def normalized_keys(self) -> set[str]:
        keys: set[str] = set()
        if self.gene:
            keys.add(f"gene:{self.gene.upper()}")
        if self.pmid:
            keys.add(f"pmid:{self.pmid}")
        if self.gene and self.hgvs_c:
            keys.add(f"gene_hgvs_c:{self.gene.upper()}:{self.hgvs_c}")
        if self.gene and self.hgvs_p:
            keys.add(f"gene_hgvs_p:{self.gene.upper()}:{self.hgvs_p}")
        if self.chromosome and self.position and self.ref and self.alt:
            keys.add(
                "genomic:"
                f"{self.genome_build or 'GRCh38'}:"
                f"{self.chromosome.removeprefix('chr')}:"
                f"{self.position}:"
                f"{self.ref.upper()}:"
                f"{self.alt.upper()}"
            )
        return keys


class LiteratureQueryResult(SchemaModel):
    query: LiteratureQuery
    literature_records: list[LiteratureEvidence] = Field(default_factory=list)
    candidate_evidence_items: list[EvidenceItem] = Field(default_factory=list)
    extracted_claims: list[LiteratureClaim] = Field(default_factory=list)
    review_flags: list[ReviewFlag] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class LiteratureProvider(ABC):
    """Abstract literature retrieval adapter.

    Providers retrieve or synthesize source-specific literature records. The shared
    extractor maps records into candidate ACMG evidence so MCP tools stay orchestration-only.
    """

    @abstractmethod
    def search(self, query: LiteratureQuery) -> list[LiteratureEvidence]:
        raise NotImplementedError


class MockLiteratureProvider(LiteratureProvider):
    """Offline provider with deterministic mock records for tests and demos."""

    def __init__(self, raw_records: list[dict[str, Any]] | None = None) -> None:
        self.raw_records = raw_records or MOCK_LITERATURE_RAW_RECORDS

    def search(self, query: LiteratureQuery) -> list[LiteratureEvidence]:
        query_keys = query.normalized_keys()
        records = [
            parse_literature_record(raw, query=query)
            for raw in self.raw_records
            if query_keys.intersection(_record_keys(raw))
        ]
        return _deduplicate_records(records)


def extract_literature_evidence(
    variant: Variant,
    context: GeneDiseaseContext | None = None,
    provider: LiteratureProvider | None = None,
) -> LiteratureQueryResult:
    provider = provider or MockLiteratureProvider()
    query = LiteratureQuery.from_variant(variant, context)
    records = provider.search(query)
    claims = [claim for record in records for claim in record.extracted_claims]
    candidate_items = [
        item
        for record in records
        for claim in record.extracted_claims
        for item in map_literature_claim_to_candidate_evidence(record, claim, variant)
    ]
    review_flags = _review_flags(records, claims)
    return LiteratureQueryResult(
        query=query,
        literature_records=records,
        candidate_evidence_items=candidate_items,
        extracted_claims=claims,
        review_flags=review_flags,
        limitations=_limitations(records),
    )


def parse_literature_record(
    raw_record: dict[str, Any],
    query: LiteratureQuery | None = None,
) -> LiteratureEvidence:
    source_payload = raw_record.get("source") or {}
    citation = str(raw_record.get("citation") or _citation_from_identifiers(raw_record))
    study_id = str(raw_record.get("study_id") or _stable_study_id(raw_record))
    duplicate_study_group = raw_record.get("duplicate_study_group")
    source = EvidenceSource(
        name=source_payload.get("name", "mock_literature"),
        version=source_payload.get("version", "offline-fixture-v1"),
        url=source_payload.get("url"),
        database_id=raw_record.get("pmid") or raw_record.get("doi") or study_id,
        retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
        query=query.model_dump(mode="json", exclude_none=True) if query else {},
        raw_snapshot_ref=source_payload.get("raw_snapshot_ref"),
    )
    provenance = provenance_from_raw_record(
        data_source=source.name,
        source_version=source.version,
        query=query.model_dump(mode="json", exclude_none=True) if query else {},
        raw_record=raw_record,
        parser_version="literature-parser-v1",
        confidence=0.5,
        limitations=[
            "Literature-derived PS3/BS3/PP1/PS4/PS2 evidence remains candidate-only."
        ],
    )
    attach_provenance_to_source(source, provenance)
    quality = LiteratureEvidenceQuality(raw_record.get("quality", "unknown"))
    claims = [
        _parse_claim(
            raw_claim,
            study_id=study_id,
            citation=citation,
            fallback_quality=quality,
            duplicate_study_group=str(duplicate_study_group or study_id),
        )
        for raw_claim in raw_record.get("claims", [])
    ]
    return LiteratureEvidence(
        source=source,
        article_id=str(
            raw_record.get("article_id") or raw_record.get("pmid") or raw_record.get("doi") or study_id
        ),
        study_id=study_id,
        pmid=str(raw_record["pmid"]) if raw_record.get("pmid") else None,
        doi=str(raw_record["doi"]) if raw_record.get("doi") else None,
        citation=citation,
        citations=[citation],
        title=str(raw_record["title"]),
        journal=raw_record.get("journal"),
        year=raw_record.get("year"),
        finding=str(raw_record.get("finding", "")),
        relevance=raw_record.get("relevance"),
        evidence_types=sorted({claim.evidence_type for claim in claims}, key=str),
        quality=quality,
        duplicate_study_group=str(duplicate_study_group) if duplicate_study_group else None,
        requires_review=True,
        extracted_claims=claims,
        review_notes=[LITERATURE_REVIEW_NOTE],
    )


def map_literature_claim_to_candidate_evidence(
    record: LiteratureEvidence,
    claim: LiteratureClaim,
    variant: Variant,
) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    for code in _safe_candidate_codes(claim):
        evidence_type_candidate = f"{_enum_value(code)}_candidate"
        items.append(
            EvidenceItem(
                evidence_id=_evidence_id(record, claim, code, variant),
                code=code,
                strength=EvidenceStrength.NONE,
                direction=claim.direction,
                reason=f"Candidate {_enum_value(code)} literature evidence: {claim.description}",
                source=record.source,
                confidence=_quality_confidence(claim.quality),
                requires_review=True,
                triggered_by=["literature_claim", _enum_value(claim.evidence_type)],
                supporting_data={
                    "candidate_only": True,
                    "automatic_application": False,
                    "human_review_required": True,
                    "study_id": record.study_id,
                    "article_id": record.article_id,
                    "pmid": record.pmid,
                    "doi": record.doi,
                    "title": record.title,
                    "journal": record.journal,
                    "year": record.year,
                    "citation": claim.citation,
                    "evidence_type_candidate": evidence_type_candidate,
                    "evidence_quality": _enum_value(claim.evidence_quality or claim.quality),
                    "assay_type": claim.assay_type,
                    "phenotype_match": claim.phenotype_match,
                    "condition_match": claim.condition_match,
                    "variant_match_level": claim.variant_match_level,
                    "duplicate_study_group": claim.duplicate_study_group,
                    "extraction_confidence": claim.extraction_confidence,
                    "requires_manual_review": True,
                    "literature_record": record.model_dump(
                        mode="json",
                        exclude={"extracted_claims"},
                    ),
                    "extracted_claim": claim.model_dump(mode="json"),
                    "review_note": LITERATURE_REVIEW_NOTE,
                    "limitations": [
                        "Mock literature provider only; no PubMed or LitVar lookup was performed.",
                        "Candidate evidence is not an applied ACMG criterion.",
                        (
                            "Study design, assay validity, phenotype match, and case independence "
                            "require manual review."
                        ),
                    ],
                },
                audit_trail=[
                    AuditTrail(
                        event_id=f"audit_{_evidence_id(record, claim, code, variant)}",
                        event_type="literature_candidate_extracted",
                        tool_name="search_literature_evidence",
                        query={"variant_id": variant.variant_id, "study_id": record.study_id},
                        notes=[LITERATURE_REVIEW_NOTE],
                    )
                ],
                review_flags=_claim_review_flags(claim),
            )
        )
    return items


def _parse_claim(
    raw_claim: dict[str, Any],
    *,
    study_id: str,
    citation: str,
    fallback_quality: LiteratureEvidenceQuality,
    duplicate_study_group: str,
) -> LiteratureClaim:
    evidence_type = LiteratureEvidenceType(raw_claim["evidence_type"])
    quality = LiteratureEvidenceQuality(raw_claim.get("quality", fallback_quality.value))
    raw_codes = [EvidenceCode(code) for code in raw_claim.get("candidate_codes", [])]
    return LiteratureClaim(
        claim_id=str(raw_claim.get("claim_id") or _stable_claim_id(study_id, raw_claim)),
        study_id=study_id,
        evidence_type=evidence_type,
        evidence_type_candidate=_candidate_type(raw_claim, raw_codes),
        candidate_codes=raw_codes,
        direction=EvidenceDirection(raw_claim.get("direction", "neutral")),
        description=str(raw_claim["description"]),
        quality=quality,
        evidence_quality=quality,
        assay_type=raw_claim.get("assay_type"),
        phenotype_match=raw_claim.get("phenotype_match"),
        condition_match=raw_claim.get("condition_match"),
        variant_match_level=raw_claim.get("variant_match_level"),
        duplicate_study_group=raw_claim.get("duplicate_study_group") or duplicate_study_group,
        extraction_confidence=float(raw_claim.get("extraction_confidence", 0.5)),
        citation=citation,
        extracted_from=raw_claim.get("extracted_from"),
        requires_review=True,
        review_notes=list(raw_claim.get("review_notes") or [LITERATURE_REVIEW_NOTE]),
    )


def _deduplicate_records(records: list[LiteratureEvidence]) -> list[LiteratureEvidence]:
    seen: set[str] = set()
    unique: list[LiteratureEvidence] = []
    for record in records:
        key = _record_identity(record)
        if key in seen:
            continue
        seen.add(key)
        unique.append(record)
    return unique


def _record_identity(record: LiteratureEvidence) -> str:
    if record.duplicate_study_group:
        return f"duplicate_study_group:{record.duplicate_study_group}"
    if record.pmid:
        return f"pmid:{record.pmid}"
    if record.doi:
        return f"doi:{record.doi.lower()}"
    return f"study:{record.study_id or record.title.lower()}"


def _review_flags(
    records: list[LiteratureEvidence],
    claims: list[LiteratureClaim],
) -> list[ReviewFlag]:
    flags = [
        ReviewFlag(
            code="LITERATURE_MOCK_PROVIDER",
            message=(
                "Literature evidence came from the offline mock provider; no network search "
                "was performed."
            ),
            severity="info",
            blocking=False,
        ),
        ReviewFlag(
            code="LITERATURE_HUMAN_REVIEW_REQUIRED",
            message="All literature-derived ACMG codes are candidate review notes only.",
            severity="warning",
            blocking=True,
        ),
    ]
    if not records:
        flags.append(
            ReviewFlag(
                code="LITERATURE_NO_MOCK_MATCH",
                message="No mock literature records matched the supplied variant query.",
                severity="info",
                blocking=False,
            )
        )
    low_quality_values = {LiteratureEvidenceQuality.LOW, LiteratureEvidenceQuality.VERY_LOW}
    if any(claim.quality in low_quality_values for claim in claims):
        flags.append(
            ReviewFlag(
                code="LITERATURE_LOW_QUALITY_EVIDENCE",
                message=(
                    "At least one extracted claim is low or very-low quality and should not "
                    "be applied without review."
                ),
                severity="warning",
                blocking=True,
            )
        )
    if any(_claim_needs_review_for_match_or_confidence(claim) for claim in claims):
        flags.append(
            ReviewFlag(
                code="LITERATURE_MATCH_OR_CONFIDENCE_REVIEW",
                message=(
                    "At least one literature claim has variant mismatch, condition mismatch, "
                    "phenotype mismatch, or low extraction confidence."
                ),
                severity="warning",
                blocking=True,
            )
        )
    return flags


def _claim_review_flags(claim: LiteratureClaim) -> list[ReviewFlag]:
    flags = [
        ReviewFlag(
            code="LITERATURE_CANDIDATE_ONLY",
            message=(
                "This literature claim is a candidate ACMG evidence note, not an applied "
                "criterion."
            ),
            severity="warning",
            blocking=True,
        )
    ]
    if claim.quality in {LiteratureEvidenceQuality.LOW, LiteratureEvidenceQuality.VERY_LOW}:
        flags.append(
            ReviewFlag(
                code="LITERATURE_LOW_QUALITY_CLAIM",
                message="Claim quality is low; manual appraisal is required before use.",
                severity="warning",
                blocking=True,
            )
        )
    if claim.condition_match is False:
        flags.append(
            ReviewFlag(
                code="LITERATURE_CONDITION_MISMATCH",
                message="The reported condition does not match the queried gene-disease context.",
                severity="warning",
                blocking=True,
            )
        )
    if claim.phenotype_match is False:
        flags.append(
            ReviewFlag(
                code="LITERATURE_PHENOTYPE_MISMATCH",
                message="The reported phenotype does not match the queried phenotype context.",
                severity="warning",
                blocking=True,
            )
        )
    if claim.variant_match_level and claim.variant_match_level not in {"exact", "same_variant"}:
        flags.append(
            ReviewFlag(
                code="LITERATURE_VARIANT_MISMATCH",
                message="The literature claim is not an exact variant match.",
                severity="warning",
                blocking=True,
            )
        )
    if claim.extraction_confidence < 0.7:
        flags.append(
            ReviewFlag(
                code="LITERATURE_LOW_EXTRACTION_CONFIDENCE",
                message="Extraction confidence is below the automatic safety review threshold.",
                severity="warning",
                blocking=True,
            )
        )
    return flags


def _safe_candidate_codes(claim: LiteratureClaim) -> list[EvidenceCode]:
    allowed = {
        LiteratureEvidenceType.FUNCTIONAL: {EvidenceCode.PS3, EvidenceCode.BS3},
        LiteratureEvidenceType.SEGREGATION: {EvidenceCode.PP1},
        LiteratureEvidenceType.DE_NOVO: {EvidenceCode.PS2, EvidenceCode.PM6},
        LiteratureEvidenceType.CASE_REPORT: {EvidenceCode.PS4},
        LiteratureEvidenceType.PHENOTYPE_SPECIFICITY: {EvidenceCode.PP4},
    }[claim.evidence_type]
    return [code for code in claim.candidate_codes if code in allowed]


def _candidate_type(
    raw_claim: dict[str, Any],
    raw_codes: list[EvidenceCode],
) -> LiteratureCandidateEvidenceType | None:
    if raw_claim.get("evidence_type_candidate"):
        return LiteratureCandidateEvidenceType(raw_claim["evidence_type_candidate"])
    if not raw_codes:
        return None
    return LiteratureCandidateEvidenceType(f"{_enum_value(raw_codes[0])}_candidate")


def _claim_needs_review_for_match_or_confidence(claim: LiteratureClaim) -> bool:
    variant_mismatch = bool(
        claim.variant_match_level and claim.variant_match_level not in {"exact", "same_variant"}
    )
    return (
        claim.condition_match is False
        or claim.phenotype_match is False
        or variant_mismatch
        or claim.extraction_confidence < 0.7
    )


def _limitations(records: list[LiteratureEvidence]) -> list[str]:
    limitations = [
        (
            "Offline mock literature provider only; no PubMed, LitVar, or full-text search "
            "was performed."
        ),
        "Outputs are candidate evidence items and review notes only.",
        "PS3, BS3, PS2, PM6, PP1, PS4, and PP4 are never automatically applied by this framework.",
        "Every literature-derived item requires citation-preserving manual review.",
        "Duplicate studies are collapsed by PMID, DOI, or study_id to avoid repeated counting.",
    ]
    if not records:
        limitations.append("No mock literature record matched the supplied query.")
    return limitations


def _quality_confidence(quality: LiteratureEvidenceQuality) -> float:
    return {
        LiteratureEvidenceQuality.HIGH: 0.75,
        LiteratureEvidenceQuality.MODERATE: 0.6,
        LiteratureEvidenceQuality.LOW: 0.4,
        LiteratureEvidenceQuality.VERY_LOW: 0.25,
        LiteratureEvidenceQuality.UNKNOWN: 0.3,
    }[quality]


def _evidence_id(
    record: LiteratureEvidence,
    claim: LiteratureClaim,
    code: EvidenceCode,
    variant: Variant,
) -> str:
    digest = sha1(
        f"{variant.variant_id}:{record.study_id}:{claim.claim_id}:{_enum_value(code)}".encode()
    ).hexdigest()
    return f"ev-lit-{digest[:12]}"


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _record_keys(raw_record: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    gene = raw_record.get("gene")
    if gene:
        keys.add(f"gene:{str(gene).upper()}")
    if raw_record.get("pmid"):
        keys.add(f"pmid:{raw_record['pmid']}")
    if gene and raw_record.get("hgvs_c"):
        keys.add(f"gene_hgvs_c:{str(gene).upper()}:{raw_record['hgvs_c']}")
    if gene and raw_record.get("hgvs_p"):
        keys.add(f"gene_hgvs_p:{str(gene).upper()}:{raw_record['hgvs_p']}")
    genomic = raw_record.get("genomic") or {}
    if genomic:
        keys.add(
            "genomic:"
            f"{genomic.get('genome_build', 'GRCh38')}:"
            f"{str(genomic['chromosome']).removeprefix('chr')}:"
            f"{genomic['position']}:"
            f"{str(genomic['ref']).upper()}:"
            f"{str(genomic['alt']).upper()}"
        )
    return keys


def _citation_from_identifiers(raw_record: dict[str, Any]) -> str:
    if raw_record.get("pmid"):
        return f"PMID:{raw_record['pmid']}"
    if raw_record.get("doi"):
        return f"DOI:{raw_record['doi']}"
    return str(raw_record["title"])


def _stable_study_id(raw_record: dict[str, Any]) -> str:
    digest = sha1(
        f"{raw_record.get('pmid')}:{raw_record.get('doi')}:{raw_record.get('title')}".encode()
    ).hexdigest()
    return f"study-{digest[:12]}"


def _stable_claim_id(study_id: str, raw_claim: dict[str, Any]) -> str:
    digest = sha1(
        f"{study_id}:{raw_claim.get('evidence_type')}:{raw_claim.get('description')}".encode()
    ).hexdigest()
    return f"claim-{digest[:12]}"


MOCK_LITERATURE_RAW_RECORDS: list[dict[str, Any]] = [
    {
        "study_id": "pmid-11111111",
        "pmid": "11111111",
        "citation": "PMID:11111111",
        "title": "Functional assessment of GENE1 c.76A>G in a disease model",
        "year": 2024,
        "gene": "GENE1",
        "hgvs_c": "NM_000001.1:c.76A>G",
        "hgvs_p": "NP_000001.1:p.Lys26Arg",
        "genomic": {
            "genome_build": "GRCh38",
            "chromosome": "1",
            "position": 123,
            "ref": "A",
            "alt": "G",
        },
        "finding": "Validated assay showed reduced protein activity for the variant.",
        "quality": "moderate",
        "claims": [
            {
                "claim_id": "claim-functional-gene1",
                "evidence_type": "functional",
                "candidate_codes": ["PS3"],
                "direction": "pathogenic",
                "description": (
                    "Functional assay reported reduced activity compatible with a PS3 candidate."
                ),
                "quality": "moderate",
                "extracted_from": "abstract",
            }
        ],
    },
    {
        "study_id": "pmid-22222222",
        "pmid": "22222222",
        "citation": "PMID:22222222",
        "title": "Families with GENE1-related example disorder",
        "year": 2023,
        "gene": "GENE1",
        "hgvs_c": "NM_000001.1:c.76A>G",
        "finding": (
            "Two families included de novo observations, segregation notes, and recurrent cases."
        ),
        "quality": "low",
        "claims": [
            {
                "claim_id": "claim-denovo-gene1",
                "evidence_type": "de_novo",
                "candidate_codes": ["PS2", "PM6"],
                "direction": "pathogenic",
                "description": (
                    "A proband was reported as de novo; parental confirmation details require "
                    "review."
                ),
                "quality": "low",
                "extracted_from": "case table",
            },
            {
                "claim_id": "claim-segregation-gene1",
                "evidence_type": "segregation",
                "candidate_codes": ["PP1"],
                "direction": "pathogenic",
                "description": (
                    "Variant was reported to segregate with disease in one small family."
                ),
                "quality": "low",
                "extracted_from": "pedigree description",
            },
            {
                "claim_id": "claim-cases-gene1",
                "evidence_type": "case_report",
                "candidate_codes": ["PS4"],
                "direction": "pathogenic",
                "description": (
                    "Multiple unrelated affected individuals were described, but enrichment "
                    "was not quantified."
                ),
                "quality": "low",
                "extracted_from": "case series",
            },
            {
                "claim_id": "claim-pp4-gene1",
                "evidence_type": "phenotype_specificity",
                "candidate_codes": ["PP4"],
                "direction": "pathogenic",
                "description": (
                    "Reported phenotype was described as specific for the gene-disease "
                    "association."
                ),
                "quality": "low",
                "extracted_from": "clinical summary",
            },
        ],
    },
    {
        "study_id": "pmid-22222222-duplicate",
        "pmid": "22222222",
        "citation": "PMID:22222222",
        "title": "Duplicate indexing record for families with GENE1-related example disorder",
        "year": 2023,
        "gene": "GENE1",
        "hgvs_c": "NM_000001.1:c.76A>G",
        "finding": "Duplicate indexing record that should not be counted twice.",
        "quality": "low",
        "claims": [
            {
                "claim_id": "claim-duplicate-gene1",
                "evidence_type": "case_report",
                "candidate_codes": ["PS4"],
                "direction": "pathogenic",
                "description": "Duplicate case report claim from the same PMID.",
                "quality": "low",
            }
        ],
    },
    {
        "study_id": "pmid-33333333",
        "pmid": "33333333",
        "citation": "PMID:33333333",
        "title": "Functional rescue study of BRCA1 c.68_69delAG",
        "year": 2022,
        "gene": "BRCA1",
        "hgvs_c": "NM_007294.4:c.68_69delAG",
        "hgvs_p": "NP_009225.1:p.Glu23ValfsTer17",
        "finding": "Experimental model reported abnormal DNA repair readouts.",
        "quality": "moderate",
        "claims": [
            {
                "claim_id": "claim-functional-brca1",
                "evidence_type": "functional",
                "candidate_codes": ["PS3"],
                "direction": "pathogenic",
                "description": "Functional abnormality may support PS3 after assay appraisal.",
                "quality": "moderate",
            }
        ],
    },
    {
        "study_id": "pmid-44444444",
        "pmid": "44444444",
        "citation": "PMID:44444444",
        "title": "Functional assay showing normal GENE2 activity",
        "year": 2025,
        "gene": "GENE2",
        "hgvs_c": "NM_000002.1:c.100A>G",
        "hgvs_p": "NP_000002.1:p.Lys34Arg",
        "finding": "Validated assay showed activity comparable with wild type.",
        "quality": "moderate",
        "claims": [
            {
                "claim_id": "claim-functional-gene2-bs3",
                "evidence_type": "functional",
                "candidate_codes": ["BS3"],
                "direction": "benign",
                "description": "Functional assay reported normal activity compatible with a BS3 candidate.",
                "quality": "moderate",
                "extracted_from": "abstract",
            }
        ],
    },
]
