import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ingest import pipeline
from ingest.cache import slugify
from ingest.geocode import GeocodeError


def test_empty_run_overwrites_stale_matrix(tmp_path, monkeypatch):
    query = "Test City"
    out_dir = tmp_path / "out"
    city_dir = out_dir / slugify(query)
    city_dir.mkdir(parents=True)

    # Simulate a matrix left over from a previous run.
    (city_dir / "matrix.json").write_text(
        '{"ids": ["old-place"], "minutes": [[0]]}',
        encoding="utf-8",
    )

    geo = SimpleNamespace(
        display_name="Test City",
        bbox=(1.0, 2.0, 3.0, 4.0),
        country="US",
        destination=lambda: {"name": "Test City"},
    )

    monkeypatch.setattr(pipeline, "geocode", lambda *args, **kwargs: geo)
    monkeypatch.setattr(pipeline, "load_vocabulary", lambda path: {})
    monkeypatch.setattr(pipeline, "check_against_vocabulary", lambda vocab: None)
    monkeypatch.setattr(pipeline, "unmapped_vocabulary", lambda vocab: [])
    monkeypatch.setattr(pipeline, "make_validator", lambda path: None)
    monkeypatch.setattr(
        pipeline,
        "fetch_group",
        lambda *args, **kwargs: {
            "fetched_at": "2026-10-14T00:00:00Z",
            "payload": {"elements": []},
        },
    )

    pipeline.run_city(
        query,
        cache_dir=tmp_path / "cache",
        out_dir=out_dir,
        contracts_dir=tmp_path / "contracts",
        groups=["amenity"],
        log=lambda message: None,
    )

    places = json.loads((city_dir / "places.json").read_text(encoding="utf-8"))
    matrix = json.loads((city_dir / "matrix.json").read_text(encoding="utf-8"))

    assert places == []
    assert matrix["ids"] == []
    assert matrix["minutes"] == []


# --- End to end run with fake Nominatim and Overpass responses -------------------------

ROOT = Path(__file__).resolve().parents[2]
ITALY_BBOX = ["35.29", "47.09", "6.63", "18.78"]  # what Nominatim returns for a whole country


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _fake_get(boundingbox):
    def get(url, params=None, headers=None, timeout=None):
        return _Response(
            [
                {
                    "name": "Rome",
                    "lat": "41.8933",
                    "lon": "12.4829",
                    "boundingbox": boundingbox,
                    "address": {"country_code": "it"},
                    "display_name": "Rome, Lazio, Italy",
                }
            ]
        )

    return get


ELEMENTS = [
    {
        "type": "way",
        "id": 1,
        "center": {"lat": 41.8902, "lon": 12.4922},
        "tags": {
            "name": "Colosseo",
            "name:en": "Colosseum",
            "name:fr": "Colisee",
            "tourism": "attraction",
            "historic": "ruins",
            "wikidata": "Q10285",
            "wikipedia": "it:Colosseo",
            "heritage": "1",
        },
    },
    {
        "type": "node",
        "id": 2,
        "lat": 41.8903,
        "lon": 12.4923,
        "tags": {"name": "Colosseo", "tourism": "museum"},
    },
    {
        "type": "node",
        "id": 3,
        "lat": 41.8950,
        "lon": 12.4800,
        "tags": {"name": "Bar Centrale", "amenity": "bar", "opening_hours": "Mo-Su 07:00-22:00"},
    },
    {
        "type": "node",
        "id": 4,
        "lat": 41.8960,
        "lon": 12.4810,
        "tags": {"name": "Museo Chiuso", "tourism": "museum", "opening_hours": "off"},
    },
    {"type": "node", "id": 5, "lat": 41.8970, "lon": 12.4820, "tags": {"tourism": "museum"}},
]


def _fake_post(url, data=None, headers=None, timeout=None):
    return _Response({"elements": ELEMENTS})


def _curation_file(tmp_path):
    path = tmp_path / "rome.json"
    path.write_text(
        json.dumps(
            {
                "checked_on": "2026-10-17",
                "places": [
                    {
                        "name": "Colosseum",
                        "match": {"names": ["Colosseo"], "near": [41.8902, 12.4922]},
                        "opening_hours": "Mo-Su 08:30-16:30",
                        "price": {"amount": 18.0, "currency": "EUR"},
                        "duration_minutes": 120,
                        "sources": ["https://colosseo.it/en/"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _run(tmp_path, **kwargs):
    defaults = dict(
        cache_dir=tmp_path / "cache",
        out_dir=tmp_path / "out",
        contracts_dir=ROOT / "contracts",
        groups=["sights"],
        get=_fake_get(["41.6556", "42.1410", "12.2344", "12.8557"]),
        post=_fake_post,
        sleep=lambda _: None,
        log=lambda _: None,
    )
    defaults.update(kwargs)
    return pipeline.run_city("Rome, Italy", **defaults)


def test_full_run_dedupes_scores_curates_and_writes_city_files(tmp_path):
    out_dir = tmp_path / "out"
    stale = out_dir / "rome" / "matrix.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("{}", encoding="utf-8")

    result = _run(
        tmp_path,
        slug="rome",
        aliases=["Roma"],
        curation_path=_curation_file(tmp_path),
        matrix_top=0,
    )

    city_dir = out_dir / "rome"
    places = json.loads((city_dir / "places.json").read_text(encoding="utf-8"))
    report = json.loads((city_dir / "report.json").read_text(encoding="utf-8"))
    city = json.loads((city_dir / "city.json").read_text(encoding="utf-8"))

    assert [p["id"] for p in places] == ["osm:node/3", "osm:way/1"]
    colosseum = places[1]
    assert colosseum["source"] == "osm+curated"
    assert colosseum["hours"]["confidence"] == "known"
    assert colosseum["cost"] == {"amount": 18.0, "currency": "EUR", "confidence": "known"}
    assert colosseum["typical_duration_minutes"] == 120
    assert "museum" in colosseum["categories"]
    assert colosseum["popularity"] > places[0]["popularity"]

    assert report["counts"]["dropped_always_closed"] == 1
    assert report["counts"]["dropped_no_name"] == 1
    assert report["duplicates"]["merged"] == 1
    assert report["curation"]["applied"] == 1
    assert report["curation"]["unmatched"] == []
    assert report["bbox_source"] == "geocoded"

    assert city["key"] == "rome"
    assert "Roma" in city["aliases"]
    assert city["country"] == "IT"
    assert "OpenStreetMap" in city["attribution"]
    assert not stale.exists()
    assert len(result["places"]) == 2


def test_matrix_file_lists_walk_and_transit_minutes(tmp_path):
    _run(tmp_path, matrix_top=10)

    matrix = json.loads(
        (tmp_path / "out" / "rome-italy" / "matrix.json").read_text(encoding="utf-8")
    )

    assert len(matrix["ids"]) == 2
    assert len(matrix["minutes"]) == 2
    assert len(matrix["transit_minutes"]) == 2


def test_explicit_bbox_skips_the_city_size_check(tmp_path):
    with pytest.raises(GeocodeError, match="too large"):
        _run(tmp_path, get=_fake_get(ITALY_BBOX))

    result = _run(
        tmp_path,
        get=_fake_get(ITALY_BBOX),
        bbox=(41.87, 12.43, 41.94, 12.53),
    )

    assert result["report"]["bbox"] == [41.87, 12.43, 41.94, 12.53]
    assert result["report"]["bbox_source"] == "explicit"
