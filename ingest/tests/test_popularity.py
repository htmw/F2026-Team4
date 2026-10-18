"""Tests for the OSM based popularity proxy."""

import pytest

from ingest.popularity import count_name_translations, popularity, signals_from_tags


def _famous_tags(translations=120):
    tags = {f"name:{code}": "x" for code in _codes(translations)}
    tags.update(
        {
            "name": "Colosseo",
            "tourism": "attraction",
            "wikidata": "Q10285",
            "wikipedia": "it:Colosseo",
            "heritage": "1",
            "website": "https://colosseo.it",
            "opening_hours": "Mo-Su 08:30-16:30",
        }
    )
    return tags


def _codes(n):
    letters = "abcdefghijklmnopqrstuvwxyz"
    return [a + b for a in letters for b in letters][:n]


def test_counts_only_language_name_keys():
    tags = {
        "name": "A",
        "name:en": "A",
        "name:zh-Hans": "A",
        "name:pt-BR": "A",
        "name:etymology:wikidata": "Q1",
        "name:signed": "no",
        "alt_name": "B",
    }

    assert count_name_translations(tags) == 3


def test_famous_sight_scores_near_one():
    score = popularity(signals_from_tags(_famous_tags()))

    assert 0.95 <= score <= 1.0


def test_plain_cafe_scores_near_zero():
    score = popularity(signals_from_tags({"name": "Bar Mario", "amenity": "cafe"}))

    assert score == 0.0


def test_more_translations_never_lower_the_score():
    scores = [popularity(signals_from_tags(_famous_tags(n))) for n in (0, 5, 20, 40, 200)]

    assert scores == sorted(scores)


@pytest.mark.parametrize("key", ["wikidata", "wikipedia", "heritage"])
def test_each_reference_tag_adds_to_the_score(key):
    base = {"name": "Chiesa", "amenity": "place_of_worship"}
    with_tag = {**base, key: "yes"}

    assert popularity(signals_from_tags(with_tag)) > popularity(signals_from_tags(base))
