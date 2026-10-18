"""Tests for the data spike report."""

import json

from ingest import spike


def _place(pid, category, hours="inferred", cost="unknown", amount=0.0, pop=0.5):
    return {
        "id": pid,
        "categories": [category],
        "hours": {"confidence": hours},
        "cost": {"amount": amount, "currency": "EUR", "confidence": cost},
        "popularity": pop,
    }


def _fake_result():
    places = [
        _place("osm:way/1", "museum", hours="known", cost="known", amount=15.0, pop=0.9),
        _place("osm:node/2", "church", cost="inferred", pop=0.6),
        _place("osm:node/3", "restaurant", hours="known", pop=0.1),
        _place("osm:node/4", "cafe", hours="unknown", pop=0.0),
    ]
    report = {
        "hours_status": {"parsed": 2, "absent": 1, "unparseable": 1},
        "counts": {"dropped_no_name": 5, "valid_records": 4, "places": 4},
        "duplicates": {"merged": 1},
        "bbox": [38.69, -9.23, 38.80, -9.09],
    }
    return {"places": places, "report": report}


def _args(tmp_path):
    return ["--cache", str(tmp_path / "cache"), "--out", str(tmp_path / "out"),
            "--contracts", str(tmp_path / "contracts"), "--docs", str(tmp_path / "docs")]


def test_spike_writes_the_lisbon_reports(tmp_path, monkeypatch):
    monkeypatch.setattr(spike, "run_city", lambda city, **kwargs: _fake_result())

    assert spike.main(_args(tmp_path)) == 0

    markdown = (tmp_path / "docs" / "data-spike.md").read_text(encoding="utf-8")
    data = json.loads((tmp_path / "docs" / "data-spike.json").read_text(encoding="utf-8"))
    assert "Lisbon, Portugal" in markdown
    assert "| Real hours: opening_hours tag fully read (`known`) | 2 | 50.0% |" in markdown
    assert "Real hours: 1 of 2 (50.0%)" in markdown  # top sights leave food and drink out
    assert data["city"] == "Lisbon, Portugal"
    assert data["stats"]["price_known_paid"] == 1
    assert data["stats"]["price_assumed_free"] == 1
    assert data["stats"]["price_no_data"] == 2


def test_a_failed_run_leaves_the_old_report_alone(tmp_path, monkeypatch):
    def failing_run(city, **kwargs):
        raise RuntimeError("simulated Overpass failure")

    monkeypatch.setattr(spike, "run_city", failing_run)
    old = tmp_path / "docs" / "data-spike.md"
    old.parent.mkdir()
    old.write_text("last good report", encoding="utf-8")

    assert spike.main(_args(tmp_path)) == 1
    assert old.read_text(encoding="utf-8") == "last good report"
