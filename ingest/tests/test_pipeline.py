import json
from types import SimpleNamespace

from ingest import pipeline
from ingest.cache import slugify


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
