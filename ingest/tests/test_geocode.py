import pytest

from ingest.geocode import GeocodeError, bbox_span_km, geocode

# The Lisbon box as Nominatim returns it, and the same box in our south, west, north, east order.
LISBON_NOMINATIM_BOX = ["38.6913994", "38.7967584", "-9.2298356", "-9.0863328"]
LISBON_BBOX = (38.6913994, -9.2298356, 38.7967584, -9.0863328)


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
def lisbon_response():
    return [
        {
            "name": "Lisbon",
            "lat": "38.7077507",
            "lon": "-9.1365919",
            # Nominatim order: south, north, west, east.
            "boundingbox": LISBON_NOMINATIM_BOX,
            "address": {"country_code": "pt", "country": "Portugal"},
            "display_name": "Lisbon, Portugal",
        }
    ]


@pytest.fixture
def portugal_response():
    # A whole country: far too big to be a city.
    return [
        {
            "name": "Portugal",
            "lat": "39.6621",
            "lon": "-8.1354",
            "boundingbox": ["36.96", "42.15", "-9.53", "-6.19"],
            "address": {"country_code": "pt"},
            "display_name": "Portugal",
        }
    ]


def test_bbox_span_uses_latitude_for_width():
    width, height = bbox_span_km(LISBON_BBOX)

    # 0.1435 degrees of longitude at 38.7 N is about 12.5 km, not 16 km.
    assert width == pytest.approx(12.5, abs=0.1)
    assert height == pytest.approx(11.7, abs=0.1)


def test_geocode_accepts_lisbon_by_default(tmp_path, lisbon_response):
    result = geocode("Lisbon, Portugal", tmp_path, get=_fake_get(lisbon_response))

    assert result.name == "Lisbon"
    assert result.country == "PT"
    assert result.country_name == "Portugal"
    assert result.bbox == LISBON_BBOX


def test_geocode_rejects_a_country_sized_area(tmp_path, portugal_response):
    with pytest.raises(GeocodeError, match="too large for a city"):
        geocode("Portugal", tmp_path, get=_fake_get(portugal_response))


def test_geocode_rejects_area_over_a_custom_limit(tmp_path, lisbon_response):
    with pytest.raises(GeocodeError, match="12 x 12 km"):
        geocode("Lisbon, Portugal", tmp_path, get=_fake_get(lisbon_response), max_span_km=10)


def test_geocode_allows_any_area_when_limit_disabled(tmp_path, portugal_response):
    result = geocode("Portugal", tmp_path, get=_fake_get(portugal_response), max_span_km=None)

    assert result.country == "PT"


def test_missing_address_gives_empty_country_fields(tmp_path, portugal_response):
    del portugal_response[0]["address"]
    result = geocode("Portugal", tmp_path, get=_fake_get(portugal_response), max_span_km=None)

    assert result.country == ""
    assert result.country_name == ""
