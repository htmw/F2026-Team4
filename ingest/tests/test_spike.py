"""Tests for data spike reporting."""

import json

from ingest import spike


def test_spike_writes_reports_when_one_city_fails(tmp_path, monkeypatch):
    def fake_run_city(city, **kwargs):
        if city == "Failed City":
            raise RuntimeError("simulated Overpass failure")

        return {
            "places": [],
            "report": {
                "hours_status": {},
                "counts": {},
            },
        }

    monkeypatch.setattr(spike, "run_city", fake_run_city)

    docs_dir = tmp_path / "docs"

    result = spike.main(
        [
            "Failed City",
            "Successful City",
            "--cache",
            str(tmp_path / "cache"),
            "--out",
            str(tmp_path / "out"),
            "--contracts",
            str(tmp_path / "contracts"),
            "--docs",
            str(docs_dir),
        ]
    )

    assert result == 1

    markdown_path = docs_dir / "data-spike.md"
    json_path = docs_dir / "data-spike.json"

    assert markdown_path.exists()
    assert json_path.exists()

    markdown = markdown_path.read_text(encoding="utf-8")
    results = json.loads(json_path.read_text(encoding="utf-8"))

    assert "Failed City" in markdown
    assert "Successful City" in markdown
    assert "FAILED" in markdown

    assert results["Failed City"]["error"] == ("RuntimeError: simulated Overpass failure")
    assert results["Successful City"]["stats"]["places"] == 0
