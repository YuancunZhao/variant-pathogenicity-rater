from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha1
from typing import Any, Literal

from variant_pathogenicity_rater.schemas.acmg import EvidenceCode
from variant_pathogenicity_rater.schemas.common import AuditTrail, ReviewFlag
from variant_pathogenicity_rater.schemas.evidence import (
    EvidenceDirection,
    EvidenceItem,
    EvidenceSource,
    EvidenceStrength,
)
from variant_pathogenicity_rater.schemas.variant import (
    GeneDiseaseContext,
    Transcript,
    Variant,
    VariantType,
)


PVS1Outcome = Literal[
    "PVS1",
    "PVS1_Strong",
    "PVS1_Moderate",
    "PVS1_Supporting",
    "candidate_only",
    "not_triggered",
]

LOF_CONSEQUENCES = {
    "stop_gained",
    "nonsense",
    "frameshift_variant",
    "frameshift",
    "splice_acceptor_variant",
    "splice_donor_variant",
    "canonical_splice",
    "essential_splice_site",
    "start_lost",
    "initiator_codon_variant",
}

SMALL_INDEL_LOF_CONSEQUENCES = {
    "loss_of_function",
    "lof",
    "protein_truncating_variant",
    "feature_truncation",
    "transcript_ablation",
}


@dataclass(frozen=True)
class PVS1Evaluation:
    outcome: PVS1Outcome
    evidence_item: EvidenceItem | None
    reasoning_chain: list[str]
    downgrade_rationale: list[str]
    confidence: float
    requires_review: bool
    review_flags: list[ReviewFlag]
    predicted_consequence: str | None
    nmd_predicted: bool | None

    def model_dump(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "evidence_item": (
                self.evidence_item.model_dump(mode="json") if self.evidence_item else None
            ),
            "reasoning_chain": self.reasoning_chain,
            "downgrade_rationale": self.downgrade_rationale,
            "confidence": self.confidence,
            "requires_review": self.requires_review,
            "review_flags": [flag.model_dump(mode="json") for flag in self.review_flags],
            "predicted_consequence": self.predicted_consequence,
            "nmd_predicted": self.nmd_predicted,
        }


def evaluate_pvs1(
    variant: Variant,
    transcript: Transcript | None,
    gene_disease_context: GeneDiseaseContext,
) -> PVS1Evaluation:
    transcript = transcript or variant.transcript or gene_disease_context.transcript
    reasoning: list[str] = []
    downgrades: list[str] = []
    flags: list[ReviewFlag] = []

    if variant.variant_type not in {
        VariantType.SNV,
        VariantType.SMALL_INSERTION,
        VariantType.SMALL_DELETION,
        VariantType.SMALL_DELINS,
    }:
        return _not_triggered(
            variant,
            reasoning,
            downgrades,
            flags,
            "Variant type is outside phase-1 SNV/small indel scope.",
            transcript,
        )

    consequence = _predicted_consequence(variant, transcript)
    if consequence is None:
        return _not_triggered(
            variant,
            reasoning,
            downgrades,
            flags,
            "Variant consequence does not match a supported LoF trigger.",
            transcript,
        )
    reasoning.append(f"Predicted LoF consequence detected: {consequence}.")

    if gene_disease_context.disease_name.strip().lower() in {
        "not provided",
        "unknown",
        "unspecified",
        "not specified",
    }:
        flags.append(
            ReviewFlag(
                code="MISSING_DISEASE_CONTEXT",
                message=(
                    "Disease context is missing; PVS1 confidence must not be elevated "
                    "from gene/transcript information alone."
                ),
                blocking=True,
            )
        )
        return _not_triggered(
            variant,
            reasoning,
            downgrades,
            flags,
            "PVS1 is not applied without disease context.",
            transcript,
            consequence=consequence,
        )

    if gene_disease_context.lof_is_known_mechanism is not True:
        flags.append(
            ReviewFlag(
                code="LOF_MECHANISM_NOT_CONFIRMED",
                message=(
                    "LoF is not confirmed as a known disease mechanism "
                    "for this gene-disease pair."
                ),
                blocking=True,
            )
        )
        return _not_triggered(
            variant,
            reasoning,
            downgrades,
            flags,
            "PVS1 is not applied unless LoF is a known disease mechanism.",
            transcript,
            consequence=consequence,
        )
    reasoning.append("LoF is provided as a known disease mechanism.")

    if gene_disease_context.transcript_is_biologically_relevant is not True:
        flags.append(
            ReviewFlag(
                code="TRANSCRIPT_RELEVANCE_NOT_CONFIRMED",
                message="Transcript clinical or biological relevance is not confirmed.",
                blocking=True,
            )
        )
        return _not_triggered(
            variant,
            reasoning,
            downgrades,
            flags,
            "PVS1 is not applied without a clinically relevant transcript.",
            transcript,
            consequence=consequence,
        )
    reasoning.append("Transcript is provided as biologically or clinically relevant.")

    if consequence == "start_loss":
        flags.append(
            ReviewFlag(
                code="START_LOSS_REVIEW",
                message=(
                    "Start-loss PVS1 assessment requires manual review for alternate "
                    "start codons and rescue."
                ),
                severity="warning",
                blocking=False,
            )
        )
        downgrades.append("Start-loss is candidate-only pending alternate-start and rescue review.")
        return _candidate_only(
            variant,
            transcript,
            gene_disease_context,
            reasoning + ["Start-loss is treated separately and flagged for review."],
            downgrades,
            flags,
            reason="Start-loss PVS1 is candidate-only unless context explicitly supports LoF.",
            consequence=consequence,
            nmd_predicted=None,
        )

    nmd_predicted = _nmd_prediction(gene_disease_context)
    if nmd_predicted is True:
        reasoning.append("Variant is predicted to result in NMD.")
    elif nmd_predicted is False:
        downgrades.append(
            "Variant is not predicted to result in NMD or is in a terminal NMD-escape region."
        )
    else:
        downgrades.append("NMD prediction is unavailable; strength is capped pending review.")
        flags.append(
            ReviewFlag(
                code="NMD_PREDICTION_UNAVAILABLE",
                message=(
                    "NMD prediction is unavailable or could not be inferred "
                    "from last-exon context."
                ),
                severity="warning",
            )
        )

    if _possible_in_frame_rescue(variant, transcript, consequence):
        downgrades.append("Variant consequence or allele length suggests possible in-frame rescue.")
        flags.append(
            ReviewFlag(
                code="POSSIBLE_IN_FRAME_RESCUE",
                message=(
                    "Assess whether the variant may preserve the reading frame "
                    "or rescue protein function."
                ),
                severity="warning",
            )
        )

    if _terminal_region(gene_disease_context):
        downgrades.append("Variant is in the last exon or terminal region where NMD may not occur.")
        if gene_disease_context.last_exon_information:
            if gene_disease_context.last_exon_information.affects_critical_region is True:
                reasoning.append(
                    "Terminal variant is reported to affect a critical protein region."
                )
            elif gene_disease_context.last_exon_information.affects_critical_region is False:
                downgrades.append(
                    "Terminal variant is not reported to affect a known critical protein region."
                )

    outcome, strength = _strength_from_context(
        consequence,
        nmd_predicted,
        downgrades,
        _terminal_critical_region(gene_disease_context),
    )
    confidence = _confidence(outcome, flags, nmd_predicted)
    return _triggered(
        variant,
        transcript,
        gene_disease_context,
        outcome,
        strength,
        reasoning,
        downgrades,
        flags,
        confidence=confidence,
        consequence=consequence,
        nmd_predicted=nmd_predicted,
    )


def _predicted_consequence(variant: Variant, transcript: Transcript | None) -> str | None:
    text = " ".join(
        value
        for value in [
            transcript.consequence if transcript else None,
            transcript.hgvs_c if transcript else None,
            transcript.hgvs_p if transcript else None,
            variant.hgvs_c,
            variant.hgvs_p,
        ]
        if value
    ).lower()

    if "start_lost" in text or "initiator_codon" in text or re.search(r"p\.\(?met1", text):
        return "start_loss"
    if "splice_acceptor" in text or "splice_donor" in text or "essential_splice" in text:
        return "canonical_splice"
    if _canonical_splice_hgvs(text):
        return "canonical_splice"
    if "frameshift" in text or re.search(r"fs(?:ter|\*)", text):
        return "frameshift"
    if "stop_gained" in text or "nonsense" in text or re.search(r"p\.[a-z]{3}\d+(?:ter|\*)", text):
        return "nonsense"
    if variant.variant_type in {
        VariantType.SMALL_INSERTION,
        VariantType.SMALL_DELETION,
        VariantType.SMALL_DELINS,
    } and any(term in text for term in SMALL_INDEL_LOF_CONSEQUENCES):
        return "small_indel_lof"
    if variant.variant_type in {
        VariantType.SMALL_INSERTION,
        VariantType.SMALL_DELETION,
        VariantType.SMALL_DELINS,
    } and _allele_length_delta(variant) % 3 != 0:
        return "frameshift"
    return None


def _canonical_splice_hgvs(text: str) -> bool:
    return bool(re.search(r"c\.[\w*+-]+(?:\+|-)[12](?:[a-z]>[a-z]|del|ins|dup)", text))


def _nmd_prediction(context: GeneDiseaseContext) -> bool | None:
    if context.nmd_prediction_available and context.nmd_predicted is not None:
        return context.nmd_predicted
    last_exon = context.last_exon_information
    if last_exon is None:
        return None
    if last_exon.predicted_to_escape_nmd is True:
        return False
    if last_exon.is_in_last_exon is True or last_exon.within_terminal_region is True:
        return False
    if last_exon.distance_to_last_exon_junction is not None:
        return last_exon.distance_to_last_exon_junction > 50
    if last_exon.is_in_last_exon is False:
        return True
    return None


def _possible_in_frame_rescue(
    variant: Variant,
    transcript: Transcript | None,
    consequence: str,
) -> bool:
    if consequence == "canonical_splice":
        return True
    if variant.variant_type == VariantType.SNV:
        return False

    text = " ".join(
        value
        for value in [
            transcript.consequence if transcript else None,
            transcript.hgvs_c if transcript else None,
            transcript.hgvs_p if transcript else None,
            variant.hgvs_c,
            variant.hgvs_p,
        ]
        if value
    ).lower()

    if "inframe" in text or "in_frame" in text:
        return True
    if consequence in {"frameshift", "small_indel_lof"}:
        return _allele_length_delta(variant) % 3 == 0
    return False


def _allele_length_delta(variant: Variant) -> int:
    return abs(len(variant.alt) - len(variant.ref))


def _terminal_region(context: GeneDiseaseContext) -> bool:
    last_exon = context.last_exon_information
    if last_exon is None:
        return False
    return bool(last_exon.is_in_last_exon or last_exon.within_terminal_region)


def _terminal_critical_region(context: GeneDiseaseContext) -> bool:
    last_exon = context.last_exon_information
    if last_exon is None:
        return False
    return bool(_terminal_region(context) and last_exon.affects_critical_region is True)


def _strength_from_context(
    consequence: str,
    nmd_predicted: bool | None,
    downgrades: list[str],
    terminal_critical_region: bool,
) -> tuple[PVS1Outcome, EvidenceStrength]:
    if any("in-frame rescue" in item for item in downgrades):
        return "PVS1_Supporting", EvidenceStrength.SUPPORTING
    if consequence == "canonical_splice":
        return "PVS1_Supporting", EvidenceStrength.SUPPORTING
    if nmd_predicted is True:
        return "PVS1", EvidenceStrength.VERY_STRONG
    if nmd_predicted is None:
        return "PVS1_Supporting", EvidenceStrength.SUPPORTING
    if consequence == "canonical_splice" and nmd_predicted is not True:
        return "PVS1_Supporting", EvidenceStrength.SUPPORTING
    if nmd_predicted is False:
        if terminal_critical_region and consequence in {"nonsense", "frameshift", "small_indel_lof"}:
            return "PVS1_Moderate", EvidenceStrength.MODERATE
        return "PVS1_Supporting", EvidenceStrength.SUPPORTING
    return "PVS1_Supporting", EvidenceStrength.SUPPORTING


def _confidence(outcome: PVS1Outcome, flags: list[ReviewFlag], nmd_predicted: bool | None) -> float:
    if outcome == "PVS1":
        confidence = 0.86
    elif outcome == "PVS1_Strong":
        confidence = 0.74
    elif outcome == "PVS1_Moderate":
        confidence = 0.64
    elif outcome == "PVS1_Supporting":
        confidence = 0.55
    elif outcome == "candidate_only":
        confidence = 0.35
    else:
        confidence = 0.0
    if nmd_predicted is None and outcome != "PVS1_Supporting":
        confidence -= 0.08
    confidence -= 0.05 * len([flag for flag in flags if flag.severity == "warning"])
    confidence -= 0.1 * len([flag for flag in flags if flag.blocking])
    return round(max(0.0, min(1.0, confidence)), 2)


def _triggered(
    variant: Variant,
    transcript: Transcript | None,
    context: GeneDiseaseContext,
    outcome: PVS1Outcome,
    strength: EvidenceStrength,
    reasoning: list[str],
    downgrades: list[str],
    flags: list[ReviewFlag],
    *,
    confidence: float,
    consequence: str,
    nmd_predicted: bool | None,
) -> PVS1Evaluation:
    evidence_id = _evidence_id(variant, outcome, transcript)
    reason = _reason(outcome, reasoning, downgrades)
    item = EvidenceItem(
        evidence_id=evidence_id,
        code=EvidenceCode.PVS1,
        strength=strength,
        direction=EvidenceDirection.PATHOGENIC,
        reason=reason,
        source=EvidenceSource(
            name="PVS1Evaluator",
            version="0.1.0",
            retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
            query={
                "variant_id": variant.variant_id,
                "transcript": transcript.accession if transcript else None,
                "gene": context.gene_symbol,
                "disease": context.disease_name,
            },
        ),
        confidence=confidence,
        requires_review=True,
        triggered_by=["variant", "transcript", "gene_disease_context"],
        supporting_data={
            "applied_pvs1_level": outcome,
            "predicted_consequence": consequence,
            "nmd_predicted": nmd_predicted,
            "reasoning_chain": reasoning,
            "downgrade_rationale": downgrades,
            "limitations": [
                "SNV/small indel PVS1 only.",
                (
                    "CNV, exon-level deletion, SV, complex rearrangement, "
                    "and RNA-seq evidence are not evaluated."
                ),
                "Machine-generated PVS1 evidence requires qualified human review.",
            ],
        },
        review_flags=flags,
        audit_trail=[
            AuditTrail(
                event_id=f"audit_{evidence_id}",
                event_type="pvs1_evaluated",
                tool_name="evaluate_pvs1",
                query={"variant_id": variant.variant_id},
                notes=reasoning + downgrades,
            )
        ],
    )
    return PVS1Evaluation(
        outcome=outcome,
        evidence_item=item,
        reasoning_chain=reasoning,
        downgrade_rationale=downgrades,
        confidence=confidence,
        requires_review=True,
        review_flags=flags,
        predicted_consequence=consequence,
        nmd_predicted=nmd_predicted,
    )


def _candidate_only(
    variant: Variant,
    transcript: Transcript | None,
    context: GeneDiseaseContext,
    reasoning: list[str],
    downgrades: list[str],
    flags: list[ReviewFlag],
    *,
    reason: str,
    consequence: str,
    nmd_predicted: bool | None,
) -> PVS1Evaluation:
    flags.append(
        ReviewFlag(
            code="PVS1_CANDIDATE_ONLY",
            message="PVS1 edge-case evidence is candidate-only and requires manual review.",
            severity="warning",
            blocking=True,
        )
    )
    item = EvidenceItem(
        evidence_id=_evidence_id(variant, "candidate_only", transcript),
        code=EvidenceCode.PVS1,
        strength=EvidenceStrength.NONE,
        direction=EvidenceDirection.PATHOGENIC,
        reason=reason,
        source=EvidenceSource(
            name="PVS1Evaluator",
            version="0.1.0",
            retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
            query={
                "variant_id": variant.variant_id,
                "transcript": transcript.accession if transcript else None,
                "gene": context.gene_symbol,
                "disease": context.disease_name,
            },
        ),
        confidence=_confidence("candidate_only", flags, nmd_predicted),
        requires_review=True,
        triggered_by=["variant", "transcript", "gene_disease_context"],
        supporting_data={
            "applied_pvs1_level": None,
            "candidate_pvs1_level": "PVS1_Supporting",
            "evidence_status": "candidate",
            "candidate_only": True,
            "predicted_consequence": consequence,
            "nmd_predicted": nmd_predicted,
            "reasoning_chain": reasoning,
            "downgrade_rationale": downgrades,
        },
        review_flags=flags,
    )
    return PVS1Evaluation(
        outcome="candidate_only",
        evidence_item=item,
        reasoning_chain=reasoning,
        downgrade_rationale=downgrades,
        confidence=item.confidence,
        requires_review=True,
        review_flags=flags,
        predicted_consequence=consequence,
        nmd_predicted=nmd_predicted,
    )


def _not_triggered(
    variant: Variant,
    reasoning: list[str],
    downgrades: list[str],
    flags: list[ReviewFlag],
    reason: str,
    transcript: Transcript | None,
    *,
    consequence: str | None = None,
) -> PVS1Evaluation:
    reasoning.append(reason)
    return PVS1Evaluation(
        outcome="not_triggered",
        evidence_item=None,
        reasoning_chain=reasoning,
        downgrade_rationale=downgrades,
        confidence=_confidence("not_triggered", flags, None),
        requires_review=True,
        review_flags=flags,
        predicted_consequence=consequence,
        nmd_predicted=None,
    )


def _evidence_id(variant: Variant, outcome: str, transcript: Transcript | None) -> str:
    digest = sha1(
        f"{variant.variant_id}:{outcome}:{transcript.accession if transcript else ''}".encode()
    ).hexdigest()
    return f"ev-pvs1-{digest[:12]}"


def _reason(outcome: str, reasoning: list[str], downgrades: list[str]) -> str:
    if downgrades:
        return f"{outcome} applied with downgrades: {'; '.join(downgrades)}"
    return f"{outcome} applied. {' '.join(reasoning)}"
