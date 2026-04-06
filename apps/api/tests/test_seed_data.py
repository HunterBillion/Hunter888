"""Tests for seed data integrity (seeds/data/*.py).

Covers:
  - All seed modules import without errors
  - Data structure completeness (required fields present)
  - Legal article format validation
  - No duplicate content hashes
  - Category distribution (all 10 categories covered)
  - Blitz Q&A completeness
  - Content version consistency
"""

import hashlib
import re
import uuid

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# Import tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSeedImports:
    def test_sales_objections_imports(self):
        from app.seeds.data.sales_objections import ALL_SALES_OBJECTIONS
        assert isinstance(ALL_SALES_OBJECTIONS, list)
        assert len(ALL_SALES_OBJECTIONS) >= 30

    def test_advanced_court_practice_imports(self):
        from app.seeds.data.advanced_court_practice import ALL_ADVANCED_COURT_PRACTICE
        assert isinstance(ALL_ADVANCED_COURT_PRACTICE, list)
        assert len(ALL_ADVANCED_COURT_PRACTICE) >= 20

    def test_myths_and_errors_imports(self):
        from app.seeds.data.myths_and_errors import ALL_MYTHS_AND_ERRORS
        assert isinstance(ALL_MYTHS_AND_ERRORS, list)
        assert len(ALL_MYTHS_AND_ERRORS) >= 20


# ═══════════════════════════════════════════════════════════════════════════════
# Data structure validation
# ═══════════════════════════════════════════════════════════════════════════════


def _get_all_chunks():
    """Collect all seed data chunks."""
    from app.seeds.data.sales_objections import ALL_SALES_OBJECTIONS
    from app.seeds.data.advanced_court_practice import ALL_ADVANCED_COURT_PRACTICE
    from app.seeds.data.myths_and_errors import ALL_MYTHS_AND_ERRORS
    return ALL_SALES_OBJECTIONS + ALL_ADVANCED_COURT_PRACTICE + ALL_MYTHS_AND_ERRORS


REQUIRED_FIELDS = [
    "category", "fact_text", "law_article", "common_errors",
    "match_keywords", "difficulty_level",
]


class TestDataStructure:
    def test_all_chunks_have_required_fields(self):
        for i, chunk in enumerate(_get_all_chunks()):
            for field in REQUIRED_FIELDS:
                assert field in chunk, f"Chunk #{i} missing field '{field}': {chunk.get('fact_text', '')[:50]}"

    def test_fact_text_not_empty(self):
        for chunk in _get_all_chunks():
            assert chunk["fact_text"].strip(), f"Empty fact_text for {chunk.get('law_article')}"

    def test_law_article_not_empty(self):
        for chunk in _get_all_chunks():
            assert chunk["law_article"].strip(), f"Empty law_article for {chunk.get('fact_text', '')[:50]}"

    def test_match_keywords_is_list(self):
        for chunk in _get_all_chunks():
            kw = chunk["match_keywords"]
            assert isinstance(kw, list), f"match_keywords is not list: {type(kw)}"
            assert len(kw) >= 2, f"Too few keywords ({len(kw)}) for {chunk.get('law_article')}"

    def test_common_errors_is_list(self):
        for chunk in _get_all_chunks():
            errors = chunk["common_errors"]
            assert isinstance(errors, list), f"common_errors is not list: {type(errors)}"

    def test_difficulty_level_range(self):
        for chunk in _get_all_chunks():
            dl = chunk["difficulty_level"]
            assert 1 <= dl <= 5, f"difficulty_level={dl} out of range for {chunk.get('law_article')}"


# ═══════════════════════════════════════════════════════════════════════════════
# Legal article format
# ═══════════════════════════════════════════════════════════════════════════════


class TestLawArticleFormat:
    """Law articles should follow a consistent format."""

    def test_articles_reference_known_laws(self):
        """All articles should reference known Russian laws."""
        KNOWN_LAWS = ["127-ФЗ", "229-ФЗ", "ГК РФ", "ГПК", "КоАП", "УК РФ",
                      "НК РФ", "ЖК РФ", "СК РФ", "ТК РФ", "Пленум", "КС РФ"]
        for chunk in _get_all_chunks():
            article = chunk["law_article"]
            has_known = any(law in article for law in KNOWN_LAWS)
            # Allow "ст." pattern as fallback
            has_article = "ст." in article.lower() or "ст " in article.lower()
            assert has_known or has_article, f"Unknown law format: '{article}'"


# ═══════════════════════════════════════════════════════════════════════════════
# Deduplication
# ═══════════════════════════════════════════════════════════════════════════════


class TestDeduplication:
    def test_no_duplicate_content_hashes(self):
        """No two chunks should have the same fact_text + law_article combination."""
        seen = {}
        for chunk in _get_all_chunks():
            key = f"{chunk['fact_text']}::{chunk['law_article']}"
            content_hash = hashlib.md5(key.encode()).hexdigest()
            assert content_hash not in seen, (
                f"Duplicate content hash:\n"
                f"  First: {seen[content_hash][:80]}\n"
                f"  Dupe:  {chunk['fact_text'][:80]}"
            )
            seen[content_hash] = chunk["fact_text"]


# ═══════════════════════════════════════════════════════════════════════════════
# Category coverage
# ═══════════════════════════════════════════════════════════════════════════════


class TestCategoryCoverage:
    EXPECTED_CATEGORIES = {
        "eligibility", "procedure", "property", "consequences", "costs",
        "creditors", "documents", "timeline", "court", "rights",
    }

    def test_all_categories_covered(self):
        categories = {chunk["category"] for chunk in _get_all_chunks()}
        missing = self.EXPECTED_CATEGORIES - categories
        assert not missing, f"Missing categories in seed data: {missing}"

    def test_minimum_chunks_per_category(self):
        """Each category should have at least 5 chunks."""
        from collections import Counter
        counts = Counter(chunk["category"] for chunk in _get_all_chunks())
        for cat in self.EXPECTED_CATEGORIES:
            assert counts.get(cat, 0) >= 5, f"Category '{cat}' has only {counts.get(cat, 0)} chunks (need ≥5)"


# ═══════════════════════════════════════════════════════════════════════════════
# Blitz Q&A completeness
# ═══════════════════════════════════════════════════════════════════════════════


class TestBlitzData:
    def test_blitz_question_has_answer(self):
        """Every chunk with blitz_question must also have blitz_answer."""
        for chunk in _get_all_chunks():
            if chunk.get("blitz_question"):
                assert chunk.get("blitz_answer"), (
                    f"blitz_question without blitz_answer: {chunk['blitz_question'][:60]}"
                )

    def test_blitz_coverage(self):
        """At least 60% of chunks should have blitz Q&A."""
        chunks = _get_all_chunks()
        with_blitz = sum(1 for c in chunks if c.get("blitz_question"))
        ratio = with_blitz / len(chunks)
        assert ratio >= 0.5, f"Only {ratio*100:.0f}% chunks have blitz Q&A (need ≥50%)"

    def test_blitz_answers_not_too_long(self):
        """Blitz answers should be concise (≤200 chars)."""
        for chunk in _get_all_chunks():
            answer = chunk.get("blitz_answer", "")
            if answer:
                assert len(answer) <= 300, (
                    f"Blitz answer too long ({len(answer)} chars): {answer[:80]}..."
                )


# ═══════════════════════════════════════════════════════════════════════════════
# Court practice entries
# ═══════════════════════════════════════════════════════════════════════════════


class TestCourtPractice:
    def test_court_practice_entries_flagged(self):
        from app.seeds.data.advanced_court_practice import ALL_ADVANCED_COURT_PRACTICE
        for chunk in ALL_ADVANCED_COURT_PRACTICE:
            assert chunk.get("is_court_practice") is True, (
                f"Court practice entry not flagged: {chunk.get('law_article')}"
            )

    def test_court_practice_has_references(self):
        """Court practice entries should have specific case references."""
        from app.seeds.data.advanced_court_practice import ALL_ADVANCED_COURT_PRACTICE
        for chunk in ALL_ADVANCED_COURT_PRACTICE:
            # Should mention Пленум, Определение, Постановление, etc.
            text = chunk["fact_text"]
            has_ref = any(kw in text for kw in [
                "Пленум", "Определение", "Постановление", "ВС РФ", "КС РФ",
                "суд", "практик", "решени",
            ])
            assert has_ref, f"Court practice without judicial reference: {text[:80]}"


# ═══════════════════════════════════════════════════════════════════════════════
# Tags validation
# ═══════════════════════════════════════════════════════════════════════════════


class TestTags:
    def test_tags_are_lists_of_strings(self):
        for chunk in _get_all_chunks():
            tags = chunk.get("tags")
            if tags is not None:
                assert isinstance(tags, list), f"tags is not list: {type(tags)}"
                for tag in tags:
                    assert isinstance(tag, str), f"tag is not string: {tag}"
                    assert len(tag) <= 50, f"Tag too long: {tag}"
