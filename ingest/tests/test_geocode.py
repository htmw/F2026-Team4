import pytest

from ingest.geocode import GeocodeError, bbox_span_km, geocode


def _fake_get(payload):
    def fake_get(*args, **kwargs):
        class Response:
            def raise_for_status(self):
                pass

            def json(self):
                return payload

        return Response()

    return fake_get


@pytest.fixture
def london_response():
    return [
        {
            "name": "London",
            "lat": "51.5072",
            "lon": "-0.1276",
            # Nominatim order: south, north, west, east.
            "boundingbox": ["51.28", "51.70", "-0.51", "0.33"],
            "address": {"country_code": "gb", "country": "United Kingdom"},
            "display_name": "London, Greater London, England, United Kingdom",
        }
    ]


@pytest.fixture
def italy_response():
    return [
        {
            "name": "Italy",
            "lat": "42.6384",
            "lon": "12.6743",
            "boundingbox": ["35.29", "47.09", "6.63", "18.78"],
            "address": {"country_code": "it"},
            "display_name": "Italy",
        }
    ]


def test_bbox_span_uses_latitude_for_width():
    width, height = bbox_span_km((51.28, -0.51, 51.70, 0.33))

    # 0.84 degrees of longitude at 51.5 N is about 58 km, not 93 km.
    assert width == pytest.approx(58.2, abs=0.5)
    assert height == pytest.approx(46.8, abs=0.5)


def test_geocode_accepts_london_by_default(tmp_path, london_response):
    result = geocode("London, UK", tmp_path, get=_fake_get(london_response))

    assert result.name == "London"
    assert result.country == "GB"
    assert result.country_name == "United Kingdom"
    assert result.bbox == (51.28, -0.51, 51.70, 0.33)


def test_geocode_rejects_a_country_sized_area(tmp_path, italy_response):
    with pytest.raises(GeocodeError, match="too large for a city"):
        geocode("Italy", tmp_path, get=_fake_get(italy_response))


def test_geocode_rejects_area_over_a_custom_limit(tmp_path, london_response):
    with pytest.raises(GeocodeError, match="58 x 47 km"):
        geocode("London, UK", tmp_path, get=_fake_get(london_response), max_span_km=30)


def test_geocode_allows_any_area_when_limit_disabled(tmp_path, italy_response):
    result = geocode("Italy", tmp_path, get=_fake_get(italy_response), max_span_km=None)

    assert result.country == "IT"


def test_missing_address_gives_empty_country_fields(tmp_path, italy_response):
    del italy_response[0]["address"]
    result = geocode("Italy", tmp_path, get=_fake_get(italy_response), max_span_km=None)

    assert result.country == ""
    assert result.country_name == ""
