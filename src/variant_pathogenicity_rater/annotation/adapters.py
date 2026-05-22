from __future__ import annotations

import csv
import json
from abc import ABC, abstractmethod
from io import StringIO
from typing import Any, Iterable

from pydantic import ValidationError

from variant_pathogenicity_rater.data_sources.provenance import (
    ProvenanceMetadata,
    provenance_from_raw_record,
)
from variant_pathogenicity_rater.schemas.annotation import (
    AnnotationParseResult,
    LofteeFlags,
    VariantAnnotation,
)


class AnnotationAdapter(ABC):
    parser_version = "annotation-parser-v1"

    def __init__(self, *, source_version: str | None = None) -> None:
        self._source_version = source_version

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Human-readable annotation source name."""

    @property
    def source_version(self) -> str | None:
        return self._source_version

    @abstractmethod
    def parse_record(self, record: dict[str, Any]) -> VariantAnnotation:
        """Parse one raw record into the internal annotation schema."""

    def parse_records(self, records: Iterable[dict[str, Any]]) -> AnnotationParseResult:
        annotations: list[VariantAnnotation] = []
        limitations: list[str] = []
        for index, record in enumerate(records):
            try:
                annotation = self.parse_record(record)
                annotation = self.normalize_annotation(annotation)
                self.validate_annotation(annotation)
                annotations.append(annotation)
            except (ValueError, TypeError, ValidationError) as exc:
                limitations.append(
                    f"Malformed {self.source_name} annotation row {index + 1}: "
                    f"{exc.__class__.__name__}: {exc}"
                )
        return AnnotationParseResult(annotations=annotations, limitations=limitations)

    def normalize_annotation(self, annotation: VariantAnnotation) -> VariantAnnotation:
        if not annotation.consequence_terms and annotation.consequence:
            annotation.consequence_terms = split_terms(annotation.consequence)
        if annotation.splice_region is None:
            annotation.splice_region = any(
                term in {"splice_region_variant", "splice_donor_variant", "splice_acceptor_variant"}
                for term in annotation.consequence_terms
            )
        return annotation

    def validate_annotation(self, annotation: VariantAnnotation) -> None:
        if not any([annotation.gene, annotation.transcript, annotation.hgvs_c, annotation.dbsnp_id]):
            raise ValueError("Annotation has no recognizable gene, transcript, HGVS, or dbSNP field.")

    def provenance(self, record: dict[str, Any]) -> ProvenanceMetadata:
        return provenance_from_raw_record(
            data_source=self.source_name,
            source_version=self.source_version,
            query={"adapter": self.source_name, "record_keys": sorted(record.keys())},
            raw_record=record,
            parser_version=self.parser_version,
            confidence=0.7,
            limitations=[
                "Annotation is descriptive context only and does not directly trigger ACMG evidence."
            ],
        )


class VepAdapter(AnnotationAdapter):
    @property
    def source_name(self) -> str:
        return "VEP"

    def parse_text(self, text: str) -> AnnotationParseResult:
        stripped = text.lstrip()
        if stripped.startswith("["):
            return self.parse_records(json.loads(text))
        rows = _read_delimited(text, delimiter="\t", comment_prefix="##")
        return self.parse_records(rows)

    def parse_record(self, record: dict[str, Any]) -> VariantAnnotation:
        consequence = pick(record, "Consequence", "consequence", default="")
        return VariantAnnotation(
            gene=pick(record, "SYMBOL", "Gene", "gene_symbol", "gene"),
            transcript=pick(record, "Feature", "transcript", "transcript_id"),
            hgvs_c=pick(record, "HGVSc", "hgvs_c"),
            hgvs_p=pick(record, "HGVSp", "hgvs_p"),
            consequence=consequence,
            exon=pick(record, "EXON", "exon"),
            intron=pick(record, "INTRON", "intron"),
            canonical=parse_bool(pick(record, "CANONICAL", "canonical")),
            mane_select=parse_bool(pick(record, "MANE_SELECT", "mane_select")),
            transcript_biotype=pick(record, "BIOTYPE", "transcript_biotype"),
            consequence_terms=split_terms(consequence),
            splice_region=None,
            loftee_flags=LofteeFlags(
                lof=pick(record, "LoF", "lof"),
                lof_filter=pick(record, "LoF_filter", "lof_filter"),
                lof_flags=pick(record, "LoF_flags", "lof_flags"),
                lof_info=pick(record, "LoF_info", "lof_info"),
            ),
            dbsnp_id=pick(record, "Existing_variation", "dbsnp_id", "rsid"),
            annotation_source=self.source_name,
            provenance=self.provenance(record),
            raw_fields=dict(record),
        )


class AnnovarAdapter(AnnotationAdapter):
    @property
    def source_name(self) -> str:
        return "ANNOVAR"

    def parse_text(self, text: str) -> AnnotationParseResult:
        return self.parse_records(_read_delimited(text, delimiter="\t"))

    def parse_record(self, record: dict[str, Any]) -> VariantAnnotation:
        consequence = pick(record, "ExonicFunc.refGene", "Func.refGene", "consequence", default="")
        hgvs_c = pick(record, "AAChange.refGene", "hgvs_c")
        transcript = _annovar_transcript(hgvs_c) or pick(record, "transcript")
        return VariantAnnotation(
            gene=pick(record, "Gene.refGene", "gene"),
            transcript=transcript,
            hgvs_c=hgvs_c,
            hgvs_p=pick(record, "hgvs_p"),
            consequence=consequence,
            exon=pick(record, "exon"),
            intron=pick(record, "intron"),
            canonical=parse_bool(pick(record, "canonical")),
            mane_select=parse_bool(pick(record, "mane_select")),
            transcript_biotype=pick(record, "transcript_biotype"),
            consequence_terms=split_terms(consequence),
            splice_region=None,
            dbsnp_id=pick(record, "avsnp150", "avsnp151", "dbsnp_id"),
            annotation_source=self.source_name,
            provenance=self.provenance(record),
            raw_fields=dict(record),
        )


class BcftoolsCsqAdapter(AnnotationAdapter):
    @property
    def source_name(self) -> str:
        return "bcftools csq"

    def parse_text(self, text: str) -> AnnotationParseResult:
        return self.parse_records(_read_delimited(text, delimiter="\t"))

    def parse_record(self, record: dict[str, Any]) -> VariantAnnotation:
        csq = pick(record, "BCSQ", "csq", "INFO/BCSQ", default="") or ""
        parsed = _parse_bcftools_csq(csq)
        consequence = pick(record, "consequence") or parsed.get("consequence") or ""
        return VariantAnnotation(
            gene=pick(record, "gene") or parsed.get("gene"),
            transcript=pick(record, "transcript") or parsed.get("transcript"),
            hgvs_c=pick(record, "hgvs_c") or parsed.get("hgvs_c"),
            hgvs_p=pick(record, "hgvs_p") or parsed.get("hgvs_p"),
            consequence=consequence,
            exon=pick(record, "exon"),
            intron=pick(record, "intron"),
            canonical=parse_bool(pick(record, "canonical")),
            mane_select=parse_bool(pick(record, "mane_select")),
            transcript_biotype=pick(record, "transcript_biotype"),
            consequence_terms=split_terms(consequence),
            splice_region=None,
            dbsnp_id=pick(record, "ID", "dbsnp_id"),
            annotation_source=self.source_name,
            provenance=self.provenance(record),
            raw_fields=dict(record),
        )


class GenericTableAdapter(AnnotationAdapter):
    @property
    def source_name(self) -> str:
        return "generic_table"

    def parse_text(self, text: str, *, delimiter: str | None = None) -> AnnotationParseResult:
        chosen = delimiter or ("\t" if "\t" in text.splitlines()[0] else ",")
        return self.parse_records(_read_delimited(text, delimiter=chosen))

    def parse_record(self, record: dict[str, Any]) -> VariantAnnotation:
        consequence = pick(record, "consequence", "Consequence", default="")
        return VariantAnnotation(
            gene=pick(record, "gene", "gene_symbol", "symbol"),
            transcript=pick(record, "transcript", "transcript_id", "feature"),
            hgvs_c=pick(record, "hgvs_c", "hgvsc"),
            hgvs_p=pick(record, "hgvs_p", "hgvsp"),
            consequence=consequence,
            exon=pick(record, "exon"),
            intron=pick(record, "intron"),
            canonical=parse_bool(pick(record, "canonical")),
            mane_select=parse_bool(pick(record, "mane_select", "mane")),
            transcript_biotype=pick(record, "transcript_biotype", "biotype"),
            consequence_terms=split_terms(
                pick(record, "consequence_terms", "terms", default=consequence) or ""
            ),
            splice_region=parse_bool(pick(record, "splice_region")),
            dbsnp_id=pick(record, "dbsnp_id", "rsid", "id"),
            annotation_source=self.source_name,
            provenance=self.provenance(record),
            raw_fields=dict(record),
        )


def _read_delimited(
    text: str,
    *,
    delimiter: str,
    comment_prefix: str | None = None,
) -> list[dict[str, Any]]:
    lines = []
    for raw_line in text.splitlines():
        if not raw_line.strip() and delimiter not in raw_line:
            continue
        if comment_prefix and raw_line.startswith(comment_prefix):
            continue
        if raw_line.startswith("#") and not raw_line.startswith("##"):
            raw_line = raw_line.lstrip("#")
        lines.append(raw_line)
    if not lines:
        return []
    return [dict(row) for row in csv.DictReader(StringIO("\n".join(lines)), delimiter=delimiter)]


def pick(record: dict[str, Any], *keys: str, default: str | None = None) -> str | None:
    lowered = {str(key).lower(): value for key, value in record.items()}
    for key in keys:
        value = record.get(key)
        if value is None:
            value = lowered.get(key.lower())
        if value is None or value == "":
            continue
        return str(value)
    return default


def parse_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "mane_select"}


def split_terms(value: str | None) -> list[str]:
    if not value:
        return []
    terms: list[str] = []
    for chunk in str(value).replace(",", "&").replace(";", "&").split("&"):
        term = chunk.strip()
        if term:
            terms.append(term)
    return terms


def _annovar_transcript(value: str | None) -> str | None:
    if not value:
        return None
    first = value.split(",", 1)[0]
    parts = first.split(":")
    return parts[1] if len(parts) > 2 else None


def _parse_bcftools_csq(value: str) -> dict[str, str]:
    first = value.split(",", 1)[0]
    parts = first.split("|")
    if len(parts) < 2:
        return {}
    parsed = {"consequence": parts[0], "gene": parts[1]}
    if len(parts) > 2:
        parsed["transcript"] = parts[2]
    if len(parts) > 3:
        parsed["hgvs_p"] = parts[3]
    if len(parts) > 4:
        parsed["hgvs_c"] = parts[4]
    return parsed
