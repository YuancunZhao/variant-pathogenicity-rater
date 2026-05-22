from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone

from variant_pathogenicity_rater.data_sources.provenance import (
    attach_provenance_to_source,
    provenance_from_raw_record,
)
from variant_pathogenicity_rater.schemas.evidence import EvidenceSource, PopulationFrequency
from variant_pathogenicity_rater.schemas.variant import Variant


class PopulationFrequencyProvider(ABC):
    @abstractmethod
    def query(self, variant: Variant) -> PopulationFrequency:
        raise NotImplementedError


class MockPopulationFrequencyProvider(PopulationFrequencyProvider):
    """Offline provider with deterministic fixtures for MCP development and tests."""

    def __init__(self, fixtures: dict[str, PopulationFrequency] | None = None) -> None:
        self.fixtures = fixtures or {}

    def query(self, variant: Variant) -> PopulationFrequency:
        if variant.variant_id in self.fixtures:
            return self.fixtures[variant.variant_id]

        query = {
            "variant_id": variant.variant_id,
            "genome_build": variant.genome_build,
            "chrom": variant.chrom,
            "pos": variant.pos,
            "ref": variant.ref,
            "alt": variant.alt,
        }
        source = EvidenceSource(
            name="mock_population_frequency",
            version="offline-fixture-v1",
            retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
            query=query,
        )
        provenance = provenance_from_raw_record(
            data_source=source.name,
            source_version=source.version,
            query=query,
            raw_record={"query": query, "provider": source.name},
            parser_version="population-parser-v1",
            confidence=0.5,
            limitations=["Offline mock population provider only; no network lookup was performed."],
        )
        attach_provenance_to_source(source, provenance)
        return PopulationFrequency(
            source=source,
            overall_af=None,
            max_pop_af=None,
            population_name="global",
            allele_count=None,
            allele_number=None,
            homozygote_count=0,
            hemizygote_count=0,
            data_source=source.name,
            data_version=source.version,
            is_absent=False,
        )
