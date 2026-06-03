from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_natural_language_skill_prefers_rate_variant_from_text_for_mixed_text() -> None:
    text = (ROOT / "skills" / "natural-language-variant-rating.md").read_text(
        encoding="utf-8"
    )

    assert "call MCP `rate_variant_from_text` first" in text
    assert "Do not pass the whole text block to `rate_variant.value`" in text
    assert '"name": "rate_variant_from_text"' in text
    assert '"report_language": "zh"' in text
    assert '"report_mode": "laboratory"' in text
    assert '"name": "rate_variant"' in text
    assert '"input_type": "hgvs"' in text
    assert "Bad MCP call" in text
    assert "Correct MCP call" in text


def test_natural_language_docs_warn_hgvs_input_type_is_pure_hgvs_only() -> None:
    docs = (ROOT / "docs" / "NATURAL_LANGUAGE_INPUT.md").read_text(encoding="utf-8")
    mcp_docs = (ROOT / "docs" / "MCP_TOOLS.md").read_text(encoding="utf-8")

    for text in (docs, mcp_docs):
        assert "HGVS+disease+inheritance mixed" in text
        assert "rate_variant_from_text" in text
        assert "rate_variant.value" in text
        assert "input_type=hgvs" in text
        assert "pure HGVS variant string" in text


def test_ai_assisted_context_docs_preserve_confirmation_boundary() -> None:
    skill = (ROOT / "skills" / "natural-language-variant-rating.md").read_text(
        encoding="utf-8"
    )
    docs = (ROOT / "docs" / "AI_ASSISTED_CONTEXT_PARSING.md").read_text(
        encoding="utf-8"
    )
    mcp_docs = (ROOT / "docs" / "MCP_TOOLS.md").read_text(encoding="utf-8")

    for text in (skill, docs, mcp_docs):
        assert "ai_assisted_context" in text
        assert "confirmed_context" in text
        assert "requires_user_confirmation" in text or "requires user confirmation" in text
        assert "candidate" in text
        assert "PVS1" in text
        assert "PM2" in text
        assert "PS1" in text
        assert "PM5" in text


def test_mcp_docs_include_parser_only_tool() -> None:
    docs = (ROOT / "docs" / "MCP_TOOLS.md").read_text(encoding="utf-8")

    assert "`parse_variant_text`" in docs
    assert "parser-only tool" in docs
    assert "without running `rate_variant`" in docs
    assert "no top-level `oneOf`" in docs
