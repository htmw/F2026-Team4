"""The command line passes the traveler-facing options on to the pipeline."""

from ingest import cli


def _run(monkeypatch, *args):
    seen = {}
    monkeypatch.setattr(cli, "run_city", lambda city, **kw: seen.update(kw, city=city))
    assert cli.main(["Rome, Italy", *args]) == 0
    return seen


def test_a_saved_city_can_get_wikipedia_descriptions_like_a_live_one(monkeypatch):
    """Rome, 20 Nov 2026: refreshed from the command line, it got 0 Wikipedia descriptions."""
    assert _run(monkeypatch, "--wikipedia")["wikipedia"] is True


def test_wikipedia_stays_off_unless_asked_for(monkeypatch):
    assert _run(monkeypatch)["wikipedia"] is False
