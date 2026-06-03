from __future__ import annotations

from variant_pathogenicity_rater.literature_agent.schema import (
    DuplicateGroup,
    LiteratureDeduplicationResult,
    LiteratureRecord,
)


def collapse_duplicate_records(records: list[LiteratureRecord]) -> LiteratureDeduplicationResult:
    seen: dict[str, LiteratureRecord] = {}
    duplicates: dict[str, list[LiteratureRecord]] = {}
    reasons: dict[str, str] = {}

    for record in records:
        key, reason = _identity(record)
        if key not in seen:
            seen[key] = record
            reasons[key] = reason
            continue
        duplicates.setdefault(key, []).append(record)

    groups = [
        DuplicateGroup(
            group_id=key,
            reason=reasons[key],
            kept_record_id=seen[key].record_id,
            duplicate_record_ids=[item.record_id for item in items],
            citations=_unique([*seen[key].citations, *[citation for item in items for citation in item.citations]]),
        )
        for key, items in duplicates.items()
    ]
    return LiteratureDeduplicationResult(records=list(seen.values()), duplicate_groups=groups)


def _identity(record: LiteratureRecord) -> tuple[str, str]:
    if record.duplicate_study_group:
        return f"duplicate_study_group:{record.duplicate_study_group}", "duplicate_study_group"
    if record.pmid:
        return f"pmid:{record.pmid}", "pmid"
    if record.doi:
        return f"doi:{record.doi.lower()}", "doi"
    if record.study_id:
        return f"study_id:{record.study_id}", "study_id"
    return f"title:{record.title.strip().lower()}", "title"


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
