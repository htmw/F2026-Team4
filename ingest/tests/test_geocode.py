
import pytest

from ingest.geocode import GeocodeError, geocode


@pytest.fixture
def london_response():
    return [
        {
            "name": "London",
            "lat": "51.5072",
            "lon": "-0.1276",
            # Nominatim order: south, north, west, east.
            "boundingbox": ["51.28", "51.70", "-0.51", "0.33"],
            "address": {"country_code": "gb"},
            "display_name": "London, Greater London, England, United Kingdom",
        }
    ]


def test_geocode_rejects_large_area_by_default(tmp_path, london_response):
    def fake_get(*args, **kwargs):
        class Response:
            def raise_for_status(self):
                pass

            def json(self):
                return london_response

        return Response()

    with pytest.raises(GeocodeError, match="too large for a city"):
        geocode("London, UK", tmp_path, get=fake_get)


def test_geocode_allows_large_area_when_limit_disabled(tmp_path, london_response):
    def fake_get(*args, **kwargs):
        class Response:
            def raise_for_status(self):
                pass

            def json(self):
                return london_response

        return Response()

    result = geocode(
        "London, UK",
        tmp_path,
        get=fake_get,
        max_span_deg=None,
    )

    assert result.name == "London"
    assert result.country == "GB"
    assert result.bbox == (51.28, -0.51, 51.70, 0.33)
