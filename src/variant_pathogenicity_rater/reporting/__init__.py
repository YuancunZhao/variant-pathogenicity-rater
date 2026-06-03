"""Report rendering for structured ACMG rating outputs."""

from variant_pathogenicity_rater.reporting.generator import (
    generate_report,
    render_literature_evidence_section,
    render_literature_search_summary_section,
)

__all__ = [
    "generate_report",
    "render_literature_evidence_section",
    "render_literature_search_summary_section",
]
