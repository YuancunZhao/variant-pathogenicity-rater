from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

import pytest

from variant_pathogenicity_rater.schemas import (
    EvidenceCode,
    EvidenceDirection,
    EvidenceItem,
    EvidenceSource,
    EvidenceStrength,
    GeneDiseaseContext,
    Transcript,
    Variant,
)


ROOT = Path(__file__).resolve().parents[1]
MCP_SERVER = ROOT / "mcp-server"
if str(MCP_SERVER) not in sys.path:
    sys.path.insert(0, str(MCP_SERVER))


@pytest.fixture
def snv_variant() -> Variant:
    return Variant(
        variant_id="GRCh38-1-123-A-G",
        genome_build="GRCh38",
        variant_type="snv",
        chrom="1",
        pos=123,
        ref="A",
        alt="G",
        gene_symbol="GENE1",
        hgvs_c="NM_000001.1:c.76A>G",
        hgvs_p="NP_000001.1:p.Lys26Arg",
    )


@pytest.fixture
def lof_context() -> GeneDiseaseContext:
    return GeneDiseaseContext(
        gene_symbol="GENE1",
        disease_name="GENE1-related disorder",
        inheritance_mode="autosomal dominant",
        disease_prevalence=0.0001,
        lof_is_known_mechanism=True,
        transcript_is_biologically_relevant=True,
        nmd_prediction_available=True,
        nmd_predicted=True,
    )


@pytest.fixture
def nonsense_transcript() -> Transcript:
    return Transcript(
        accession="NM_000001",
        version="1",
        gene_symbol="GENE1",
        hgvs_c="NM_000001.1:c.76A>T",
        hgvs_p="NP_000001.1:p.Lys26Ter",
        consequence="nonsense",
        canonical=True,
    )


@pytest.fixture
def evidence_factory(
    snv_variant: Variant,
) -> Callable[..., EvidenceItem]:
    def _factory(
        code: EvidenceCode | str,
        strength: EvidenceStrength | str,
        direction: EvidenceDirection | str,
        *,
        evidence_id: str | None = None,
        source_name: str = "test_source",
        reason: str | None = None,
    ) -> EvidenceItem:
        code_value = EvidenceCode(code)
        strength_value = EvidenceStrength(strength)
        direction_value = EvidenceDirection(direction)
        return EvidenceItem(
            evidence_id=evidence_id or f"ev-{code_value.value.lower()}-{strength_value.value}",
            code=code_value,
            strength=strength_value,
            direction=direction_value,
            reason=reason or f"{code_value.value} fixture evidence.",
            source=EvidenceSource(
                name=source_name,
                version="fixture-v1",
                query={"variant_id": snv_variant.variant_id},
            ),
            confidence=0.8,
            requires_review=True,
            triggered_by=["pytest_fixture"],
        )

    return _factory
