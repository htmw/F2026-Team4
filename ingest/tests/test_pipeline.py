"""End to end tests of the pipeline with fake Nominatim and Overpass responses (no network)."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ingest import pipeline
from ingest.cache import slugify
from ingest.curation import CurationError
from ingest.geocode import GeocodeError


def test_an_empty_run_writes_empty_files(tmp_path, monkeypatch):
    query = "Lisbon, Portugal"
    out_dir = tmp_path / "out"
    geo = SimpleNamespace(
        display_name="Lisbon, Portugal",
        bbox=(38.69, -9.23, 38.80, -9.09),
        country="PT",
        country_name="Portugal",
        destination=lambda: {"name": "Lisbon"},
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
        groups=["sights"],
        log=lambda message: None,
    )

    city_dir = out_dir / slugify(query)
    places = json.loads((city_dir / "places.json").read_text(encoding="utf-8"))
    report = json.loads((city_dir / "report.json").read_text(encoding="utf-8"))

    assert places == []
    assert report["counts"]["places"] == 0


# --- End to end run with fake Nominatim and Overpass responses -------------------------

ROOT = Path(__file__).resolve().parents[2]
# What Nominatim returns: south, north, west, east, as strings.
LISBON_BBOX = ["38.6913994", "38.7967584", "-9.2298356", "-9.0863328"]
PORTUGAL_BBOX = ["36.96", "42.15", "-9.53", "-6.19"]  # a whole country, far too big for a city
BOX_AROUND_LISBON = (38.69, -9.23, 38.80, -9.09)  # an explicit bbox: south, west, north, east


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
                    "name": "Lisbon",
                    "lat": "38.7077507",
                    "lon": "-9.1365919",
                    "boundingbox": boundingbox,
                    "address": {"country_code": "pt", "country": "Portugal"},
                    "display_name": "Lisbon, Portugal",
                }
            ]
        )

    return get


ELEMENTS = [
    {
        "type": "way",
        "id": 1,
        "center": {"lat": 38.6916, "lon": -9.2160},
        "tags": {
            "name": "Torre de Belém",
            "name:en": "Belem Tower",
            "name:fr": "Tour de Belem",
            "tourism": "attraction",
            "historic": "tower",
            "wikidata": "Q215003",
            "wikipedia": "pt:Torre de Belém",
            "heritage": "1",
        },
    },
    {
        # A second record of the same tower, 14 m away: merged into the first one.
        "type": "node",
        "id": 2,
        "lat": 38.6917,
        "lon": -9.2161,
        "tags": {"name": "Torre de Belém", "tourism": "museum"},
    },
    {
        "type": "node",
        "id": 3,
        "lat": 38.6950,
        "lon": -9.2050,
        "tags": {"name": "Bar Central", "amenity": "bar", "opening_hours": "Mo-Su 07:00-22:00"},
    },
    {
        # Closed every day: dropped.
        "type": "node",
        "id": 4,
        "lat": 38.6960,
        "lon": -9.2040,
        "tags": {"name": "Museu Fechado", "tourism": "museum", "opening_hours": "off"},
    },
    # No name: dropped.
    {"type": "node", "id": 5, "lat": 38.6970, "lon": -9.2030, "tags": {"tourism": "museum"}},
    {
        # A piece of a long aqueduct that only touches the box: its centre lies outside it.
        "type": "relation",
        "id": 6,
        "center": {"lat": 38.7500, "lon": -9.3000},
        "tags": {"name": "Aqueduto das Águas Livres", "historic": "aqueduct"},
    },
]


def _fake_post(url, data=None, headers=None, timeout=None):
    return _Response({"elements": ELEMENTS})


def _curation_file(tmp_path):
    path = tmp_path / "lisbon.json"
    path.write_text(
        json.dumps(
            {
                "checked_on": "2026-10-17",
                "places": [
                    {
                        "name": "Belem Tower",
                        "match": {"names": ["Torre de Belém"], "near": [38.6916, -9.2160]},
                        "opening_hours": "Tu-Su 10:00-17:30",
                        "price": {"amount": 15.0, "currency": "EUR"},
                        "duration_minutes": 60,
                        "sources": ["https://example.org/belem-tower"],
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
        get=_fake_get(LISBON_BBOX),
        post=_fake_post,
        sleep=lambda _: None,
        log=lambda _: None,
    )
    defaults.update(kwargs)
    return pipeline.run_city("Lisbon, Portugal", **defaults)


def test_full_run_dedupes_scores_curates_and_writes_city_files(tmp_path):
    out_dir = tmp_path / "out"

    result = _run(
        tmp_path,
        slug="lisbon",
        aliases=["Lisboa"],
        curation_path=_curation_file(tmp_path),
    )

    city_dir = out_dir / "lisbon"
    places = json.loads((city_dir / "places.json").read_text(encoding="utf-8"))
    report = json.loads((city_dir / "report.json").read_text(encoding="utf-8"))
    city = json.loads((city_dir / "city.json").read_text(encoding="utf-8"))

    assert [p["id"] for p in places] == ["osm:node/3", "osm:way/1"]
    tower = places[1]
    assert tower["source"] == "osm+curated"
    assert tower["hours"]["confidence"] == "known"
    assert tower["cost"] == {"amount": 15.0, "currency": "EUR", "confidence": "known"}
    assert tower["typical_duration_minutes"] == 60
    assert "museum" in tower["categories"]
    assert tower["popularity"] > places[0]["popularity"]

    assert report["counts"]["dropped_always_closed"] == 1
    assert report["counts"]["dropped_no_name"] == 1
    assert report["counts"]["dropped_outside_bbox"] == 1
    assert report["duplicates"]["merged"] == 1
    assert report["curation"]["applied"] == 1
    assert report["curation"]["unmatched"] == []
    assert report["bbox_source"] == "geocoded"

    assert city["key"] == "lisbon"
    assert "Lisboa" in city["aliases"]
    assert city["country"] == "PT"
    assert city["country_name"] == "Portugal"
    assert "OpenStreetMap" in city["attribution"]
    assert sorted(f.name for f in city_dir.iterdir()) == [
        "city.json",
        "destination.json",
        "places.json",
        "report.json",
    ]
    assert len(result["places"]) == 2


def test_a_bad_curation_file_leaves_the_previous_output_alone(tmp_path):
    _run(tmp_path)
    city_dir = tmp_path / "out" / "lisbon-portugal"
    before = {f.name: f.read_bytes() for f in city_dir.iterdir()}

    # Two entries for the same tower: the run stops before it writes anything.
    path = _curation_file(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["places"].append({**data["places"][0], "name": "Belem Tower again"})
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(CurationError, match="both match"):
        _run(tmp_path, curation_path=path)

    assert {f.name: f.read_bytes() for f in city_dir.iterdir()} == before


def test_output_files_use_unix_line_ends(tmp_path):
    _run(tmp_path)

    for f in (tmp_path / "out" / "lisbon-portugal").iterdir():
        assert b"\r\n" not in f.read_bytes(), f.name


def test_a_place_centred_outside_the_box_is_dropped(tmp_path):
    result = _run(tmp_path, bbox=BOX_AROUND_LISBON)

    assert result["report"]["counts"]["dropped_outside_bbox"] == 1
    assert "osm:relation/6" not in [p["id"] for p in result["places"]]


def test_explicit_bbox_skips_the_city_size_check(tmp_path):
    with pytest.raises(GeocodeError, match="too large"):
        _run(tmp_path, get=_fake_get(PORTUGAL_BBOX))

    result = _run(tmp_path, get=_fake_get(PORTUGAL_BBOX), bbox=BOX_AROUND_LISBON)

    assert result["report"]["bbox"] == list(BOX_AROUND_LISBON)
    assert result["report"]["bbox_source"] == "explicit"
