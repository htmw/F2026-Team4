"""Short "what is this place" lines: OSM tags for every place, Wikipedia for famous ones."""

from ingest.describe import (
    WIKIDATA_API,
    WIKIPEDIA_API,
    contacts_from_tags,
    describe_from_tags,
    describe_places,
    without_pronunciation,
)


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


def test_a_place_keeps_its_own_website():
    tags = {"website": "https://www.salarjungmuseum.in", "phone": "+91 40 2457 6443"}
    assert contacts_from_tags(tags) == {"website": "https://www.salarjungmuseum.in"}


def test_contact_tags_are_cleaned():
    assert contacts_from_tags({"contact:website": "example.com"}) == {"website": "https://example.com"}
    assert contacts_from_tags({"website": "https://a.example; https://b.example"}) == {
        "website": "https://a.example"}


def test_anything_that_is_not_a_web_link_is_dropped():
    assert contacts_from_tags({"website": "javascript:alert(1)"}) == {}
    assert contacts_from_tags({"website": "ftp://files.example.com"}) == {}
    assert contacts_from_tags({"website": "see the sign at the door"}) == {}


def test_a_famous_place_keeps_its_contacts_next_to_the_wikipedia_text():
    places = [{"id": "a", "categories": ["museum"], "popularity": 1}]

    def get(url, params, **kw):
        return FakeResponse({"query": {"pages": {"1": {"title": "M", "extract": "A museum."}}}})

    out = describe_places(
        places, {"a": {"tags": {"wikipedia": "en:M", "website": "https://m.example"}}},
        get=get, log=lambda *_: None,
    )
    assert out["a"] == {"text": "A museum.", "source": "wikipedia", "website": "https://m.example"}


class Busy(FakeResponse):
    status_code = 429
    headers = {"Retry-After": "3"}


def test_wikipedia_saying_slow_down_is_waited_for_not_given_up_on():
    """Paris, 18 Nov 2026: a 429 left the whole city without Wikipedia descriptions."""
    places = [{"id": "a", "categories": ["landmark"], "popularity": 1}]
    answers = [Busy({}), FakeResponse({"query": {"pages": {"1": {
        "title": "Arc de Triomphe", "extract": "The Arc de Triomphe is a monument in Paris."}}}})]
    waits = []

    out = describe_places(places, {"a": {"tags": {"wikipedia": "en:Arc de Triomphe"}}},
                          get=lambda url, params, **kw: answers.pop(0), sleep=waits.append,
                          log=lambda *_: None)

    assert out["a"]["source"] == "wikipedia"
    assert waits == [3.0], "waited as long as Wikipedia asked"


def test_a_long_list_pauses_between_batches():
    places = [{"id": f"p{i}", "categories": ["museum"], "popularity": 1} for i in range(25)]
    info = {f"p{i}": {"tags": {"wikipedia": f"en:Museum {i}"}} for i in range(25)}
    waits = []

    describe_places(places, info, get=lambda url, params, **kw: FakeResponse({"query": {}}),
                    sleep=waits.append, log=lambda *_: None)

    assert waits == [1.0], "two Wikipedia batches of 20 and 5, one polite pause between"


def test_how_to_say_a_name_is_left_out_but_a_translation_stays():
    """Rome, 20 Nov 2026: the Colosseum's description began with its pronunciation."""
    assert without_pronunciation(
        "The Colosseum ( KOL-ə-SEE-əm; Italian: Colosseo [kolosˈsɛːo]) is an elliptical"
        " amphitheatre."
    ) == "The Colosseum is an elliptical amphitheatre."
    assert without_pronunciation(
        "The Palazzo Colonna (Italian pronunciation: [paˈlattso koˈlonna]) is a palace in Rome."
    ) == "The Palazzo Colonna is a palace in Rome."
    kept = "Fontana delle Api (Fountain of the Bees) is a fountain in Piazza Barberini."
    assert without_pronunciation(kept) == kept
    museum = "The National Etruscan Museum (Italian: Museo Nazionale Etrusco) is a museum."
    assert without_pronunciation(museum) == museum


def test_a_new_wikipedia_intro_comes_without_its_pronunciation():
    places = [{"id": "a", "categories": ["landmark"], "popularity": 1}]
    intro = "The Colosseum ( KOL-ə-SEE-əm) is an amphitheatre in Rome."
    out = describe_places(
        places, {"a": {"tags": {"wikipedia": "en:Colosseum"}}},
        get=lambda url, params, **kw: FakeResponse(
            {"query": {"pages": {"1": {"title": "Colosseum", "extract": intro}}}}),
        log=lambda *_: None,
    )
    assert out["a"]["text"] == "The Colosseum is an amphitheatre in Rome."
