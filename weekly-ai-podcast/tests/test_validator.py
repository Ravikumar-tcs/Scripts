from podcast import research


def test_dedupe_drops_repeated_urls():
    findings = {
        "new_ai_implementations": [
            {"headline": "A", "one_line_summary": "x", "source_url": "https://ex.com/1", "source_title": "S", "published_at": "2026-04-18"},
            {"headline": "A2", "one_line_summary": "x2", "source_url": "https://ex.com/1", "source_title": "S", "published_at": "2026-04-18"},
        ],
        "new_or_updated_llms": [],
        "us_insurer_ai": [
            {"headline": "A3", "one_line_summary": "x3", "source_url": "https://ex.com/1", "source_title": "S", "published_at": "2026-04-18"},
        ],
        "global_insurer_ai": [],
    }
    out = research._dedupe(findings)
    all_items = sum((out[b] for b in research.BUCKETS), [])
    assert len(all_items) == 1


def test_shape_check_rejects_missing_bucket():
    import pytest

    with pytest.raises(ValueError, match="missing buckets"):
        research._shape_check({"new_ai_implementations": [], "new_or_updated_llms": []})


def test_shape_check_rejects_non_list_bucket():
    import pytest

    bad = {b: [] for b in research.BUCKETS}
    bad["us_insurer_ai"] = "not a list"
    with pytest.raises(ValueError, match="is not a list"):
        research._shape_check(bad)


def test_render_sources_skips_empty_buckets():
    findings = {b: [] for b in research.BUCKETS}
    findings["us_insurer_ai"] = [
        {"headline": "H", "source_url": "https://ex.com", "source_title": "T", "published_at": "2026-04-18"}
    ]
    md = research.render_sources(findings)
    assert "US insurer AI" in md
    assert "Global insurer AI" not in md
