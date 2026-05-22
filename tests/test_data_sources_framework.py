from __future__ import annotations

import json

from variant_pathogenicity_rater.data_sources.cache import DiskCache
from variant_pathogenicity_rater.data_sources.config import (
    DataSourceConfig,
    ProviderMode,
    load_data_sources_config,
)
from variant_pathogenicity_rater.data_sources.providers import (
    build_clinvar_provider,
    build_population_provider,
)
from variant_pathogenicity_rater.evidence.clinvar import ClinVarQuery
from variant_pathogenicity_rater.pipeline.rate_variant import rate_variant


def test_provider_mode_switching_and_env_override() -> None:
    config = load_data_sources_config(
        overrides={
            "sources": {
                "clinvar": {"mode": "local_file", "local_file": "clinvar.json"},
                "population": {"mode": "online_disabled"},
            }
        },
        env={"VPR_CLINVAR_MODE": "mock"},
    )

    assert config.source("clinvar").mode == ProviderMode.MOCK
    assert config.source("population").mode == ProviderMode.ONLINE_DISABLED
    assert build_clinvar_provider(config.source("clinvar")).__class__.__name__ == "MockClinVarProvider"
    assert (
        build_population_provider(config.source("population")).__class__.__name__
        == "OnlineDisabledPopulationFrequencyProvider"
    )


def test_clinvar_online_env_requires_both_mode_and_enabled() -> None:
    disabled = load_data_sources_config(
        env={"VPR_CLINVAR_MODE": "online"},
    )
    assert disabled.source("clinvar").mode == ProviderMode.ONLINE
    assert disabled.source("clinvar").online_enabled is False

    enabled = load_data_sources_config(
        env={
            "VPR_CLINVAR_MODE": "future_online",
            "VPR_CLINVAR_ONLINE_ENABLED": "true",
            "VPR_CLINVAR_TIMEOUT_SECONDS": "3.5",
            "VPR_CLINVAR_EMAIL": "curator@example.org",
            "VPR_CLINVAR_USER_AGENT": "vpr-test",
        },
    )
    source = enabled.source("clinvar")
    assert source.mode == ProviderMode.FUTURE_ONLINE
    assert source.online_enabled is True
    assert source.timeout_seconds == 3.5
    assert source.email == "curator@example.org"
    assert source.user_agent == "vpr-test"


def test_disk_cache_hit_miss_and_key_design(tmp_path) -> None:
    cache = DiskCache(tmp_path, ttl_seconds=3600)
    query = {"variant_id": "GRCh38-1-123-A-G"}

    key = DiskCache.cache_key(
        provider="clinvar",
        mode="local_file",
        source_version="snapshot-v1",
        query=query,
    )
    assert cache.get(key) is None

    entry, hit = cache.get_or_set(
        provider="clinvar",
        mode="local_file",
        source_version="snapshot-v1",
        query=query,
        loader=lambda: [{"variation_id": "1"}],
    )
    assert hit is False
    assert entry.key == key
    assert entry.raw_record_hash

    cached_entry, hit = cache.get_or_set(
        provider="clinvar",
        mode="local_file",
        source_version="snapshot-v1",
        query=query,
        loader=lambda: [{"variation_id": "should-not-load"}],
    )
    assert hit is True
    assert cached_entry.payload == [{"variation_id": "1"}]


def test_local_file_clinvar_attaches_provenance(tmp_path) -> None:
    local_file = tmp_path / "clinvar.json"
    local_file.write_text(
        json.dumps(
            [
                {
                    "variation_id": "55555",
                    "gene": "GENE1",
                    "hgvs_c": "NM_000001.1:c.76A>G",
                    "clinical_significance": "Likely benign",
                    "review_status": "criteria provided, single submitter",
                    "conditions": ["not specified"],
                    "genomic": {
                        "genome_build": "GRCh38",
                        "chromosome": "1",
                        "position": 123,
                        "ref": "A",
                        "alt": "G",
                    },
                }
            ]
        ),
        encoding="utf-8",
    )
    provider = build_clinvar_provider(
        DataSourceConfig(
            name="clinvar",
            mode="local_file",
            source_version="local-snapshot-v1",
            parser_version="clinvar-parser-test",
            cache_dir=str(tmp_path / "cache"),
            local_file=str(local_file),
        )
    )

    result = provider.query(
        ClinVarQuery(
            gene="GENE1",
            hgvs_c="NM_000001.1:c.76A>G",
            chromosome="1",
            position=123,
            ref="A",
            alt="G",
            genome_build="GRCh38",
        )
    )

    assert result.records
    provenance = result.records[0].source.provenance
    assert provenance.data_source == "clinvar"
    assert provenance.source_version == "local-snapshot-v1"
    assert provenance.query["gene"] == "GENE1"
    assert provenance.retrieved_at
    assert provenance.raw_record_hash
    assert provenance.parser_version == "clinvar-parser-test"
    assert provenance.confidence == 0.6
    assert provenance.limitations


def test_external_provider_failure_becomes_limitation() -> None:
    result = rate_variant(
        {
            "gene": "BRCA1",
            "transcript": "NM_007294.4",
            "hgvs_c": "NM_007294.4:c.68_69delAG",
            "hgvs_p": "NP_009225.1:p.Glu23ValfsTer17",
            "chromosome": "17",
            "position": 43124027,
            "ref": "AG",
            "alt": "A",
            "disease": "Hereditary breast and ovarian cancer",
            "options": {
                "data_sources": {
                    "sources": {
                        "clinvar": {"mode": "online_disabled"},
                    }
                }
            },
        }
    )

    assert result["status"] == "ok"
    assert any(limitation.startswith("query_clinvar failed:") for limitation in result["limitations"])
