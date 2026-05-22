from __future__ import annotations

from variant_pathogenicity_rater.annotation import (
    AnnovarAdapter,
    BcftoolsCsqAdapter,
    GenericTableAdapter,
    OnlineResolverConfig,
    OnlineVariantNormalizer,
    TranscriptMetadataResolver,
    VepAdapter,
    evaluate_annotation_safety,
)


def test_parse_vep_fixture() -> None:
    text = """## ENSEMBL VARIANT EFFECT PREDICTOR
#Uploaded_variation\tSYMBOL\tFeature\tHGVSc\tHGVSp\tConsequence\tEXON\tCANONICAL\tMANE_SELECT\tBIOTYPE\tExisting_variation
1_123_A/G\tGENE1\tNM_000001.1\tNM_000001.1:c.76A>G\tNP_000001.1:p.Lys26Arg\tmissense_variant\t2/9\tYES\tYES\tprotein_coding\trs123
"""

    result = VepAdapter(source_version="vep-fixture-v1").parse_text(text)

    assert result.limitations == []
    annotation = result.annotations[0]
    assert annotation.gene == "GENE1"
    assert annotation.transcript == "NM_000001.1"
    assert annotation.hgvs_c == "NM_000001.1:c.76A>G"
    assert annotation.canonical is True
    assert annotation.mane_select is True
    assert annotation.transcript_biotype == "protein_coding"
    assert annotation.dbsnp_id == "rs123"
    assert annotation.provenance.data_source == "VEP"
    assert annotation.provenance.source_version == "vep-fixture-v1"
    assert annotation.provenance.query["adapter"] == "VEP"
    assert annotation.provenance.raw_record_hash


def test_parse_annovar_fixture() -> None:
    text = """Chr\tStart\tEnd\tRef\tAlt\tGene.refGene\tFunc.refGene\tExonicFunc.refGene\tAAChange.refGene\tavsnp150
1\t123\t123\tA\tG\tGENE1\texonic\tnonsynonymous SNV\tGENE1:NM_000001.1:exon2:c.76A>G:p.Lys26Arg\trs123
"""

    result = AnnovarAdapter(source_version="annovar-fixture-v1").parse_text(text)

    annotation = result.annotations[0]
    assert annotation.gene == "GENE1"
    assert annotation.transcript == "NM_000001.1"
    assert annotation.hgvs_c == "GENE1:NM_000001.1:exon2:c.76A>G:p.Lys26Arg"
    assert annotation.consequence == "nonsynonymous SNV"
    assert annotation.dbsnp_id == "rs123"
    assert annotation.provenance.data_source == "ANNOVAR"


def test_parse_bcftools_csq_fixture() -> None:
    text = """CHROM\tPOS\tID\tREF\tALT\tBCSQ
1\t123\trs123\tA\tG\tmissense|GENE1|NM_000001.1|p.Lys26Arg|c.76A>G
"""

    result = BcftoolsCsqAdapter(source_version="bcftools-fixture-v1").parse_text(text)

    annotation = result.annotations[0]
    assert annotation.gene == "GENE1"
    assert annotation.transcript == "NM_000001.1"
    assert annotation.hgvs_c == "c.76A>G"
    assert annotation.hgvs_p == "p.Lys26Arg"
    assert annotation.consequence_terms == ["missense"]
    assert annotation.dbsnp_id == "rs123"


def test_generic_tsv_fixture() -> None:
    text = """gene\ttranscript\thgvs_c\thgvs_p\tconsequence_terms\tcanonical\tmane_select\tsplice_region\tdbsnp_id
GENE1\tNM_000001.1\tNM_000001.1:c.76A>G\tNP_000001.1:p.Lys26Arg\tmissense_variant;splice_region_variant\ttrue\tfalse\ttrue\trs123
"""

    result = GenericTableAdapter(source_version="generic-fixture-v1").parse_text(text)

    annotation = result.annotations[0]
    assert annotation.splice_region is True
    assert annotation.consequence_terms == ["missense_variant", "splice_region_variant"]
    assert annotation.canonical is True
    assert annotation.mane_select is False


def test_malformed_rows_become_limitations() -> None:
    text = """unrelated\talso_unrelated
\t
"""

    result = GenericTableAdapter().parse_text(text)

    assert result.annotations == []
    assert result.limitations
    assert "Malformed generic_table annotation row 1" in result.limitations[0]


def test_multiple_transcripts_review_flag() -> None:
    result = GenericTableAdapter().parse_text(
        """gene,transcript,hgvs_c
GENE1,NM_000001.1,NM_000001.1:c.76A>G
GENE1,NM_000002.1,NM_000002.1:c.80A>G
"""
    )

    safety = evaluate_annotation_safety(result.annotations)

    assert [flag.code for flag in safety.review_flags] == ["MULTIPLE_TRANSCRIPT_AMBIGUITY"]


def test_transcript_mismatch_review_flag() -> None:
    result = GenericTableAdapter().parse_text(
        """gene,transcript,hgvs_c
GENE1,NM_000001.1,NM_000001.1:c.76A>G
"""
    )

    safety = evaluate_annotation_safety(result.annotations, expected_transcript="NM_000002.1")

    assert [flag.code for flag in safety.review_flags] == ["TRANSCRIPT_MISMATCH"]


def test_missing_hgvs_limitation_and_mane_not_evidence() -> None:
    result = GenericTableAdapter().parse_text(
        """gene,transcript,consequence,mane_select
GENE1,NM_000001.1,missense_variant,true
"""
    )

    safety = evaluate_annotation_safety(result.annotations)

    assert any("Missing HGVS" in limitation for limitation in safety.limitations)
    assert any("not ACMG evidence" in limitation for limitation in safety.limitations)
    assert not hasattr(result.annotations[0], "evidence_code")


def test_online_disabled_by_default(tmp_path) -> None:
    resolver = OnlineVariantNormalizer(
        OnlineResolverConfig(name="normalizer", cache_dir=str(tmp_path / "cache"))
    )

    result = resolver.resolve({"hgvs_c": "NM_000001.1:c.76A>G"})

    assert result.resolved is None
    assert result.provenance is None
    assert result.cache_hit is False
    assert "disabled by default" in result.limitations[0]


def test_mocked_online_resolver_success_and_cache(tmp_path) -> None:
    calls = {"count": 0}

    def fetcher(query: dict[str, object], timeout_seconds: float) -> dict[str, object]:
        calls["count"] += 1
        assert timeout_seconds == 2.0
        return {"normalized": "NC_000001.11:g.123A>G", "query_echo": query}

    resolver = OnlineVariantNormalizer(
        OnlineResolverConfig(
            name="normalizer",
            enabled=True,
            online_enabled=True,
            source_version="mock-normalizer-v1",
            timeout_seconds=2.0,
            cache_dir=str(tmp_path / "cache"),
        ),
        fetcher=fetcher,
    )

    first = resolver.resolve({"hgvs_c": "NM_000001.1:c.76A>G"})
    second = resolver.resolve({"hgvs_c": "NM_000001.1:c.76A>G"})

    assert calls["count"] == 1
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert first.resolved is not None
    assert first.resolved["source"] == "normalizer"
    assert first.resolved["version"] == "mock-normalizer-v1"
    assert first.resolved["source_version"] == "mock-normalizer-v1"
    assert first.resolved["query"] == {"hgvs_c": "NM_000001.1:c.76A>G"}
    assert first.resolved["retrieved_at"]
    assert first.provenance is not None
    assert first.provenance.data_source == "normalizer"
    assert first.provenance.source_version == "mock-normalizer-v1"
    assert first.provenance.query == {"hgvs_c": "NM_000001.1:c.76A>G"}
    assert first.provenance.retrieved_at
    assert first.provenance.raw_record_hash
    assert second.provenance is not None
    assert second.provenance.raw_record_hash == first.provenance.raw_record_hash


def test_mocked_online_resolver_failure_becomes_limitation(tmp_path) -> None:
    def fetcher(_query: dict[str, object], _timeout_seconds: float) -> dict[str, object]:
        raise TimeoutError("request timed out")

    resolver = TranscriptMetadataResolver(
        OnlineResolverConfig(
            name="transcript_metadata",
            enabled=True,
            online_enabled=True,
            timeout_seconds=1.0,
            cache_dir=str(tmp_path / "cache"),
        ),
        fetcher=fetcher,
    )

    result = resolver.resolve({"transcript": "NM_000001.1"})

    assert result.resolved is None
    assert result.provenance is None
    assert any("TimeoutError" in limitation for limitation in result.limitations)
    assert any("pipeline execution can continue" in limitation for limitation in result.limitations)
