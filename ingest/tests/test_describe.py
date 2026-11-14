"""Short "what is this place" lines: OSM tags for every place, Wikipedia for famous ones."""

from ingest.describe import WIKIDATA_API, WIKIPEDIA_API, describe_from_tags, describe_places


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


def test_a_restaurant_names_its_food():
    tags = {"amenity": "restaurant", "cuisine": "indian;biryani"}
    assert describe_from_tags(tags, ["restaurant"]) == "Restaurant serving indian and biryani food."


def test_a_temple_names_its_religion_and_year():
    tags = {"amenity": "place_of_worship", "religion": "hindu", "start_date": "1591"}
    assert describe_from_tags(tags, ["landmark"]) == "Hindu temple, built in 1591."


def test_the_osm_description_is_used_when_readable():
    tags = {"description": "A small museum about the history of the old railway."}
    assert describe_from_tags(tags, ["museum"]) == tags["description"]


def test_a_description_in_another_script_is_not_used():
    tags = {"description": "చారిత్రక కట్టడం మరియు స్మారక చిహ్నం", "historic": "monument"}
    assert describe_from_tags(tags, ["monument"]) == "Monument."


def test_famous_places_get_wikipedia_others_keep_their_line():
    places = [
        {"id": "a", "categories": ["landmark"], "popularity": 0.9},
        {"id": "b", "categories": ["cafe"], "popularity": 0.2},
    ]
    info = {"a": {"tags": {"wikidata": "Q6510"}}, "b": {"tags": {"amenity": "cafe"}}}
    asked = []

    def get(url, params, **kw):
        asked.append(url)
        if url == WIKIDATA_API:
            return FakeResponse({"entities": {"Q6510": {"sitelinks": {"enwiki": {
                "title": "Charminar"}}}}})
        return FakeResponse({"query": {"pages": {"1": {
            "title": "Charminar",
            "extract": "The Charminar is a monument in Hyderabad, India, built in 1591.",
        }}}})

    out = describe_places(places, info, get=get, log=lambda *_: None)

    assert out["a"] == {
        "text": "The Charminar is a monument in Hyderabad, India, built in 1591.",
        "source": "wikipedia",
    }
    assert out["b"] == {"text": "Café.", "source": "openstreetmap"}
    assert asked == [WIKIDATA_API, WIKIPEDIA_API], "one request each, not one per place"


def test_a_long_intro_is_cut_at_a_sentence():
    places = [{"id": "a", "categories": ["museum"], "popularity": 1}]
    long = "First sentence about the museum and its long history. " * 8

    def get(url, params, **kw):
        return FakeResponse({"query": {"pages": {"1": {"title": "M", "extract": long}}}})

    out = describe_places(places, {"a": {"tags": {"wikipedia": "en:M"}}}, get=get,
                          log=lambda *_: None)
    assert len(out["a"]["text"]) <= 280
    assert out["a"]["text"].endswith(".")
