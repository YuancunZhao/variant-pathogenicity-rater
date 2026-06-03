from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from variant_pathogenicity_rater.cli import main as cli_main
from variant_pathogenicity_rater.clingen_erepo import ClinGenERepoQuery, MockClinGenERepoProvider
from variant_pathogenicity_rater.data_sources.config import DataSourceConfig, ProviderMode
from variant_pathogenicity_rater.data_sources.providers import (
    ClinVarOnlineProvider,
    LocalFileClinVarProvider,
)
from variant_pathogenicity_rater.evidence.clinvar import ClinVarQuery
from variant_pathogenicity_rater.pipeline.rate_variant import rate_variant
from variant_pathogenicity_rater.ps1_pm5 import generate_ps1_pm5_evidence
from variant_pathogenicity_rater.schemas.evidence import ClinVarRecord, EvidenceSource
from variant_pathogenicity_rater.schemas.variant import GeneDiseaseContext, Transcript, Variant


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "data" / "fixtures" / "clinvar_real_provider_validation.jsonl"
MCP_SERVER = ROOT / "mcp-server"
if str(MCP_SERVER) not in sys.path:
    sys.path.insert(0, str(MCP_SERVER))


def _provider(tmp_path: Path) -> LocalFileClinVarProvider:
    return LocalFileClinVarProvider(
        DataSourceConfig(
            name="clinvar",
            mode=ProviderMode.LOCAL_FILE,
            source_version="clinvar-validation-fixture-2026-05",
            parser_version="clinvar-parser-validation",
            local_file=str(FIXTURE),
            cache_dir=str(tmp_path),
        )
    )


def _query(variation_id: str, *, condition: str = "Example disease") -> ClinVarQuery:
    return ClinVarQuery(variation_id=variation_id, condition=condition)


def _validation_context(disease: str = "Example disease") -> GeneDiseaseContext:
    return GeneDiseaseContext(gene="GENE64", disease=disease)


def _validation_variant(
    *,
    gene: str = "GENE64",
    transcript: str = "NM_064000.1",
    protein: str | None = "NP_064000.1:p.Lys3Arg",
    hgvs_c: str = "NM_064000.1:c.9A>G",
    chrom: str = "1",
    pos: int = 640009,
    ref: str = "A",
    alt: str = "G",
) -> Variant:
    return Variant(
        variant_id=f"GRCh38-{chrom}-{pos}-{ref}-{alt}",
        genome_build="GRCh38",
        variant_type="snv",
        chrom=chrom,
        pos=pos,
        ref=ref,
        alt=alt,
        gene_symbol=gene,
        transcript=Transcript(
            accession=transcript.split(".", 1)[0],
            version=transcript.split(".", 1)[1] if "." in transcript else None,
            gene_symbol=gene,
            hgvs_c=hgvs_c,
            hgvs_p=protein,
        ),
        hgvs_c=hgvs_c,
        hgvs_p=protein,
    )


def _rate_payload(
    *,
    gene: str,
    transcript: str,
    hgvs_c: str,
    hgvs_p: str,
    chromosome: str,
    position: int,
    ref: str,
    alt: str,
    disease: str,
    tmp_path: Path,
    extra_options: dict | None = None,
) -> dict:
    return {
        "gene": gene,
        "transcript": transcript,
        "hgvs_c": hgvs_c,
        "hgvs_p": hgvs_p,
        "chromosome": chromosome,
        "position": position,
        "ref": ref,
        "alt": alt,
        "disease": disease,
        "options": {
            "include_population": False,
            "include_computational": False,
            "include_literature": False,
            "data_sources": {
                "clinvar": {
                    "mode": "local_file",
                    "local_file": str(FIXTURE),
                    "source_version": "clinvar-validation-fixture-2026-05",
                    "parser_version": "clinvar-parser-validation",
                    "cache_dir": str(tmp_path / "clinvar-cache"),
                }
            },
            **(extra_options or {}),
        },
    }


@pytest.mark.parametrize(
    ("variation_id", "expected"),
    [
        (
            "640001",
            {
                "clinical_significance": "Pathogenic",
                "review_status": "reviewed by expert panel",
                "review_stars": 3,
                "review_confidence": "high",
                "candidate_code": "PP5",
                "direction": "pathogenic",
                "flags": set(),
            },
        ),
        (
            "640002",
            {
                "clinical_significance": "Likely pathogenic",
                "review_status": "criteria provided, multiple submitters, no conflicts",
                "review_stars": 2,
                "review_confidence": "moderate",
                "candidate_code": "PP5",
                "direction": "pathogenic",
                "flags": set(),
            },
        ),
        (
            "640003",
            {
                "clinical_significance": "Pathogenic",
                "review_status": "criteria provided, single submitter",
                "review_stars": 1,
                "review_confidence": "low",
                "candidate_code": "PP5",
                "direction": "pathogenic",
                "flags": {"CLINVAR_LOW_REVIEW_CONFIDENCE"},
            },
        ),
        (
            "640004",
            {
                "clinical_significance": "Conflicting interpretations of pathogenicity",
                "review_status": "criteria provided, conflicting interpretations",
                "review_stars": 1,
                "review_confidence": "low",
                "candidate_code": "PP5",
                "direction": "conflicting",
                "flags": {
                    "CLINVAR_CONFLICTING_INTERPRETATIONS",
                    "CLINVAR_LOW_REVIEW_CONFIDENCE",
                },
            },
        ),
        (
            "640005",
            {
                "clinical_significance": "Likely benign",
                "review_status": "criteria provided, multiple submitters, no conflicts",
                "review_stars": 2,
                "review_confidence": "moderate",
                "candidate_code": "BP6",
                "direction": "benign",
                "flags": set(),
            },
        ),
    ],
)
def test_local_fixture_preserves_required_clinvar_fields_and_candidate_only_status(
    tmp_path: Path, variation_id: str, expected: dict
) -> None:
    result = _provider(tmp_path).query(_query(variation_id))

    assert len(result.records) == 1
    record = result.records[0]
    assert record.variation_id == variation_id
    assert record.gene_symbol == "GENE64"
    assert record.transcript == "NM_064000.1"
    assert record.hgvs_c
    assert record.hgvs_p
    assert record.protein_change == record.hgvs_p
    assert record.chromosome == "1"
    assert record.position is not None
    assert record.ref == "A"
    assert record.alt == "G"
    assert record.genome_build == "GRCh38"
    assert record.clinical_significance == expected["clinical_significance"]
    assert record.review_status == expected["review_status"]
    assert record.review_stars == expected["review_stars"]
    assert record.review_confidence == expected["review_confidence"]
    assert record.condition == "Example disease"
    assert record.conditions == ["Example disease"]
    assert record.germline_or_somatic == "germline"
    assert record.citations
    assert record.last_evaluated is not None
    assert record.submitter_count is not None

    provenance = record.source.provenance
    assert provenance.data_source == "clinvar"
    assert provenance.source_version == "clinvar-validation-fixture-2026-05"
    assert provenance.parser_version == "clinvar-parser-validation"
    assert provenance.query["variation_id"] == variation_id
    assert provenance.raw_record_hash
    assert record.source.raw_snapshot_ref == provenance.raw_record_hash

    assert len(result.candidate_evidence_items) == 1
    item = result.candidate_evidence_items[0]
    assert item.code == expected["candidate_code"]
    assert item.direction == expected["direction"]
    assert item.strength == "none"
    assert item.candidate_only is True
    assert item.applied is False
    assert item.supporting_data["candidate_only"] is True
    assert item.supporting_data["applied"] is False
    assert item.supporting_data["automatic_application"] is False

    flag_codes = {flag.code for flag in result.review_flags}
    assert expected["flags"].issubset(flag_codes)


def test_somatic_only_record_is_limitation_and_not_germline_candidate(tmp_path: Path) -> None:
    result = _provider(tmp_path).query(
        _query("640006", condition="Hereditary germline validation disease")
    )

    assert result.records[0].germline_or_somatic == "somatic"
    assert result.candidate_evidence_items == []
    assert "CLINVAR_NON_GERMLINE_ASSERTION" in {flag.code for flag in result.review_flags}
    assert "CLINVAR_CONDITION_MISMATCH" in {flag.code for flag in result.review_flags}
    assert any("Somatic-only" in limitation for limitation in result.limitations)


def test_local_fixture_missing_protein_condition_mismatch_and_exact_variant_block_ps1_pm5(
    tmp_path: Path,
) -> None:
    provider = _provider(tmp_path)
    missing_protein = provider.query(_query("640007")).records[0]
    condition_mismatch = provider.query(_query("640008")).records[0]
    exact_variant = provider.query(_query("640009")).records[0]

    missing_items, missing_decisions = generate_ps1_pm5_evidence(
        variant=_validation_variant(protein=None, hgvs_c="NM_064000.1:c.70A>G", pos=640099),
        context=_validation_context(),
        clinvar_records=[missing_protein],
    )
    assert missing_decisions[0].applied is False
    assert missing_decisions[0].generation.status == "candidate"
    assert all(item.applied is False and item.strength == "none" for item in missing_items)

    mismatch_items, mismatch_decisions = generate_ps1_pm5_evidence(
        variant=_validation_variant(hgvs_c="NM_064000.1:c.8A>T", pos=640098, alt="T"),
        context=_validation_context(),
        clinvar_records=[condition_mismatch],
    )
    assert mismatch_decisions[0].applied is False
    assert mismatch_decisions[0].condition_match.blocking is True
    assert mismatch_items == []

    same_items, same_decisions = generate_ps1_pm5_evidence(
        variant=_validation_variant(),
        context=_validation_context(),
        clinvar_records=[exact_variant],
    )
    assert same_decisions[0].applied is False
    assert same_decisions[0].generation.status == "blocked"
    assert "same nucleotide/genomic variant" in "; ".join(same_decisions[0].blocking_reasons)
    assert same_items == []


def test_rate_variant_applies_ps1_only_through_local_fixture_comparator_gates(
    tmp_path: Path,
) -> None:
    result = rate_variant(
        _rate_payload(
            gene="PS1G",
            transcript="NM_064001.1",
            hgvs_c="NM_064001.1:c.76A>G",
            hgvs_p="NP_064001.1:p.Lys26Arg",
            chromosome="2",
            position=641000,
            ref="A",
            alt="G",
            disease="PS1 validation disease",
            tmp_path=tmp_path,
        )
    )

    assert [item["code"] for item in result["applied_evidence"]] == ["PS1"]
    ps1_item = result["applied_evidence"][0]
    assert ps1_item["source"]["name"] == "ClinVar"
    assert ps1_item["requires_review"] is True
    assert ps1_item["supporting_data"]["not_pp5"] is True
    assert ps1_item["supporting_data"]["clinvar_comparison"]["different_nucleotide_change"] is True
    assert any(item["code"] == "PP5" for item in result["review_note_evidence"])
    assert not any(item["code"] in {"PP5", "BP6"} for item in result["applied_evidence"])
    assert "not PP5" in result["report_text"]


def test_rate_variant_applies_pm5_only_through_local_fixture_comparator_gates(
    tmp_path: Path,
) -> None:
    result = rate_variant(
        _rate_payload(
            gene="PM5G",
            transcript="NM_064002.1",
            hgvs_c="NM_064002.1:c.76A>G",
            hgvs_p="NP_064002.1:p.Lys26Arg",
            chromosome="3",
            position=642000,
            ref="A",
            alt="G",
            disease="PM5 validation disease",
            tmp_path=tmp_path,
        )
    )

    assert [item["code"] for item in result["applied_evidence"]] == ["PM5"]
    pm5_item = result["applied_evidence"][0]
    assert pm5_item["source"]["name"] == "ClinVar"
    assert pm5_item["requires_review"] is True
    assert pm5_item["supporting_data"]["amino_acid_match"]["different_missense_change"] is True
    assert pm5_item["supporting_data"]["not_pp5"] is True
    assert not any(item["code"] in {"PP5", "BP6"} for item in result["applied_evidence"])


def test_conflicting_clinvar_record_blocks_applied_ps1_pm5(tmp_path: Path) -> None:
    record = _provider(tmp_path).query(_query("640004")).records[0]
    items, decisions = generate_ps1_pm5_evidence(
        variant=_validation_variant(hgvs_c="NM_064000.1:c.4A>T", pos=640104, alt="T"),
        context=_validation_context(),
        clinvar_records=[record],
    )

    assert decisions[0].clinvar_comparison.has_conflict is True
    assert decisions[0].applied is False
    assert all(item.applied is False and item.strength == "none" for item in items)


def test_local_file_malformed_records_are_limitations_not_crashes(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed_clinvar.jsonl"
    malformed.write_text(
        "\n".join(
            [
                json.dumps({"variation_id": "bad-index", "gene": "BAD", "genomic": {"chromosome": "1"}}),
                json.dumps(
                    {
                        "variation_id": "bad-parse",
                        "gene": "BAD",
                        "hgvs_c": "NM_BAD.1:c.1A>G",
                        "position": "not-an-int",
                        "clinical_significance": "Pathogenic",
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )
    provider = LocalFileClinVarProvider(
        DataSourceConfig(
            name="clinvar",
            mode=ProviderMode.LOCAL_FILE,
            local_file=str(malformed),
            cache_dir=str(tmp_path / "cache"),
        )
    )

    result = provider.query(
        ClinVarQuery(gene="BAD", hgvs_c="NM_BAD.1:c.1A>G", include_gene_comparators=True)
    )

    assert result.records == []
    assert result.candidate_evidence_items == []
    assert any("could not be indexed" in limitation for limitation in result.limitations)
    assert any("could not be parsed" in limitation for limitation in result.limitations)


def test_query_clinvar_mcp_remains_offline_candidate_only() -> None:
    from tools.rate_variant import query_clinvar

    payload = asyncio.run(query_clinvar({"query": {"variation_id": "17661"}}))

    assert payload["status"] == "ok"
    assert payload["stage"] == "mock_clinvar_provider"
    assert payload["clinvar_records"][0]["variation_id"] == "17661"
    assert payload["candidate_evidence_items"][0]["strength"] == "none"
    assert payload["candidate_evidence_items"][0]["supporting_data"]["applied"] is False
    assert payload["human_review"]["required"] is True
    assert any("no network" in limitation.lower() for limitation in payload["limitations"])


def test_mcp_rate_variant_preserves_local_fixture_applied_and_review_note_separation(
    tmp_path: Path,
) -> None:
    from tools.rate_variant import rate_variant as mcp_rate_variant

    result = asyncio.run(
        mcp_rate_variant(
            _rate_payload(
                gene="PS1G",
                transcript="NM_064001.1",
                hgvs_c="NM_064001.1:c.76A>G",
                hgvs_p="NP_064001.1:p.Lys26Arg",
                chromosome="2",
                position=641000,
                ref="A",
                alt="G",
                disease="PS1 validation disease",
                tmp_path=tmp_path,
            )
        )
    )

    assert [item["code"] for item in result["applied_evidence"]] == ["PS1"]
    assert any(item["code"] == "PP5" for item in result["review_note_evidence"])
    assert not any(item["code"] in {"PP5", "BP6"} for item in result["applied_evidence"])


def test_cli_rate_uses_local_fixture_from_env_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("VPR_CLINVAR_MODE", "local_file")
    monkeypatch.setenv("VPR_CLINVAR_LOCAL_FILE", str(FIXTURE))
    monkeypatch.setenv("VPR_CLINVAR_CACHE_DIR", str(tmp_path / "cli-cache"))

    exit_code = cli_main(
        [
            "rate",
            "--gene",
            "PS1G",
            "--transcript",
            "NM_064001.1",
            "--hgvs-c",
            "NM_064001.1:c.76A>G",
            "--hgvs-p",
            "NP_064001.1:p.Lys26Arg",
            "--chromosome",
            "2",
            "--position",
            "641000",
            "--ref",
            "A",
            "--alt",
            "G",
            "--disease",
            "PS1 validation disease",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["data_source_modes"]["clinvar"] == "local_file"
    assert [item["code"] for item in payload["applied_evidence"]] == ["PS1"]
    assert any("local-file mode" in limitation for limitation in payload["limitations"])
    assert not any("online" in limitation and "retrieved" in limitation for limitation in payload["limitations"])


def test_clinvar_erepo_conflicts_are_review_flags_and_do_not_change_classification(
    tmp_path: Path,
) -> None:
    base = _rate_payload(
        gene="GENE64",
        transcript="NM_064000.1",
        hgvs_c="NM_064000.1:c.5A>G",
        hgvs_p="NP_064000.1:p.Lys2Arg",
        chromosome="1",
        position=640005,
        ref="A",
        alt="G",
        disease="Example disease",
        tmp_path=tmp_path,
    )
    base["options"]["include_clingen_erepo"] = False
    without_erepo = rate_variant(base)

    with_erepo_payload = _rate_payload(
        gene="GENE64",
        transcript="NM_064000.1",
        hgvs_c="NM_064000.1:c.5A>G",
        hgvs_p="NP_064000.1:p.Lys2Arg",
        chromosome="1",
        position=640005,
        ref="A",
        alt="G",
        disease="Example disease",
        tmp_path=tmp_path,
        extra_options={
            "include_clingen_erepo": True,
            "clingen_erepo_query": {"clinvar_variation_id": "640005"},
            "clingen_erepo_records": [
                {
                    "record_id": "erepo-conflict-plp",
                    "gene": "GENE64",
                    "clinvar_variation_id": "640005",
                    "hgvs_c": "NM_064000.1:c.5A>G",
                    "hgvs_p": "NP_064000.1:p.Lys2Arg",
                    "genomic": {
                        "genome_build": "GRCh38",
                        "chromosome": "1",
                        "position": 640005,
                        "ref": "A",
                        "alt": "G",
                    },
                    "disease_condition": "Example disease",
                    "classification": "Pathogenic",
                    "classification_date": "2025-01-15",
                    "classification_version": "v1",
                    "source_url": "https://erepo.example/erepo-conflict-plp",
                }
            ],
        },
    )
    with_erepo = rate_variant(with_erepo_payload)

    assert with_erepo["final_classification"] == without_erepo["final_classification"]
    assert [item["code"] for item in with_erepo["applied_evidence"]] == [
        item["code"] for item in without_erepo["applied_evidence"]
    ]
    assert "CLINGEN_EREPO_CLINVAR_CONFLICT" in {flag["code"] for flag in with_erepo["review_flags"]}
    assert "ClinVar and ClinGen ERepo classifications conflict" in with_erepo["report_text"]


def test_clinvar_plp_vs_erepo_benign_conflict_is_detected(tmp_path: Path) -> None:
    clinvar = _provider(tmp_path).query(_query("640001")).records[0]
    variant = _validation_variant(hgvs_c="NM_064000.1:c.1A>G", protein="NP_064000.1:p.Lys1Arg", pos=640001)
    context = _validation_context()
    result = MockClinGenERepoProvider(
        [
            {
                "record_id": "erepo-conflict-benign",
                "gene": "GENE64",
                "clinvar_variation_id": "640001",
                "hgvs_c": "NM_064000.1:c.1A>G",
                "hgvs_p": "NP_064000.1:p.Lys1Arg",
                "disease_condition": "Example disease",
                "classification": "Likely benign",
                "classification_date": "2025-01-15",
                "classification_version": "v1",
                "source_url": "https://erepo.example/erepo-conflict-benign",
            }
        ]
    ).query(
        ClinGenERepoQuery.from_variant(variant, context, clinvar_variation_id="640001"),
        variant=variant,
        context=context,
        clinvar_records=[clinvar],
    )

    assert "CLINGEN_EREPO_CLINVAR_CONFLICT" in {flag.code for flag in result.review_flags}


def test_online_provider_malformed_response_is_limitation_with_mocked_http(tmp_path: Path) -> None:
    def http_get(endpoint: str, params: dict[str, str]) -> list:
        return []

    provider = ClinVarOnlineProvider(
        DataSourceConfig(
            name="clinvar",
            mode=ProviderMode.ONLINE,
            online_enabled=True,
            cache_dir=str(tmp_path),
        ),
        http_get=http_get,
    )
    result = provider.query(ClinVarQuery(rsid="rs334"))

    assert result.records == []
    assert result.candidate_evidence_items == []
    assert any("ClinVar online query failed" in limitation for limitation in result.limitations)
    assert any("AttributeError" in limitation for limitation in result.limitations)


@pytest.mark.online_clinvar_smoke
def test_optional_live_clinvar_online_smoke_requires_explicit_env_gates(tmp_path: Path) -> None:
    required = {
        "VPR_RUN_LIVE_PROVIDER_SMOKE": "1",
        "VPR_CLINVAR_ONLINE_SMOKE": "true",
        "VPR_CLINVAR_MODE": "online",
        "VPR_CLINVAR_ONLINE_ENABLED": "true",
    }
    if any(os.environ.get(name, "").lower() != value for name, value in required.items()):
        pytest.skip("ClinVar online smoke is opt-in and all ClinVar online env gates are required.")

    cache_dir = os.environ.get("VPR_CLINVAR_CACHE_DIR", str(tmp_path / "live-clinvar-cache"))
    provider = ClinVarOnlineProvider(
        DataSourceConfig(
            name="clinvar",
            mode=ProviderMode.ONLINE,
            online_enabled=True,
            source_version="NCBI ClinVar E-utilities live",
            parser_version="clinvar-parser-validation",
            cache_dir=cache_dir,
            timeout_seconds=float(os.environ.get("VPR_CLINVAR_TIMEOUT_SECONDS", "5")),
            email=os.environ.get("VPR_CLINVAR_EMAIL"),
            user_agent=os.environ.get("VPR_CLINVAR_USER_AGENT"),
        )
    )

    result = provider.query(ClinVarQuery(rsid="rs334", condition="sickle cell anemia"))

    if not result.records:
        assert result.limitations
        return

    provenance = result.records[0].source.provenance
    assert provenance.query["rsid"] == "rs334"
    assert provenance.raw_record_hash
    assert provenance.parser_version == "clinvar-parser-validation"
    assert provenance.source_url or provenance.endpoint
    assert result.records[0].source.retrieval_timestamp
    assert any("disk cache" in limitation for limitation in result.limitations)
