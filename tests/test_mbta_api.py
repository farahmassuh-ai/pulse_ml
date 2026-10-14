"""API logic tested with fake responses: no network, no database."""
import pytest

from mbta_api import (MbtaApiError, direction_word, get_json, schedules_to_records,
                      to_api_route)

LOOKUP = {
    "1": {"id": "1", "direction_names": ["Outbound", "Inbound"]},
    "SL1": {"id": "741", "direction_names": ["Outbound", "Inbound"]},
    "66": {"id": "66", "direction_names": ["Outbound", "Inbound"]},
}


class FakeResponse:
    def __init__(self, status, payload=None):
        self.status_code, self._payload, self.text = status, payload or {}, ""

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), 0

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls += 1
        return self.responses.pop(0)


def test_route_ids_translate_to_api_form():
    assert to_api_route("01", LOOKUP)["id"] == "1"
    assert to_api_route("SL1", LOOKUP)["id"] == "741"
    assert to_api_route("66", LOOKUP)["id"] == "66"
    assert to_api_route("CT2", LOOKUP) is None


def test_direction_words():
    names = ["Outbound", "Inbound"]
    assert direction_word(1, names) == "Inbound"
    assert direction_word(0, names) == "Outbound"
    assert direction_word(1, []) == "Inbound"          # rule when names are missing
    assert direction_word(None, names) is None


def test_schedule_record_mapping_and_departure_fallback():
    data = [
        {"attributes": {"direction_id": 1, "departure_time": "2026-10-14T05:10:00-04:00",
                        "arrival_time": "2026-10-14T05:09:00-04:00"},
         "relationships": {"stop": {"data": {"id": "64"}}, "trip": {"data": {"id": "70391179"}}}},
        {"attributes": {"direction_id": 0, "departure_time": None,     # last stop
                        "arrival_time": "2026-10-14T06:00:00-04:00"},
         "relationships": {"stop": {"data": {"id": "110"}}, "trip": {"data": {"id": "70391180"}}}},
    ]
    recs = schedules_to_records(data, "01", ["Outbound", "Inbound"])
    assert recs[0] == {"route_id": "01", "direction_id": "Inbound", "stop_id": "64",
                       "half_trip_id": "70391179", "scheduled_raw": "2026-10-14T05:10:00-04:00"}
    assert recs[1]["scheduled_raw"] == "2026-10-14T06:00:00-04:00"
    assert recs[1]["direction_id"] == "Outbound"


def test_429_backs_off_then_succeeds():
    waits = []
    session = FakeSession([FakeResponse(429), FakeResponse(429), FakeResponse(200, {"data": [1]})])
    out = get_json("/schedules", {}, session=session, sleep=waits.append)
    assert out["data"] == [1] and waits == [2, 4]


def test_4xx_fails_immediately_without_retry():
    session = FakeSession([FakeResponse(400)])
    with pytest.raises(MbtaApiError):
        get_json("/schedules", {}, session=session, sleep=lambda s: None)
    assert session.calls == 1


def test_5xx_gives_up_after_retries():
    session = FakeSession([FakeResponse(503)] * 5)
    with pytest.raises(MbtaApiError):
        get_json("/schedules", {}, session=session, max_retries=4, sleep=lambda s: None)
    assert session.calls == 5


def test_pagination_is_followed():
    session = FakeSession([
        FakeResponse(200, {"data": [1, 2], "links": {"next": "https://x/next"}}),
        FakeResponse(200, {"data": [3], "links": {}}),
    ])
    assert get_json("/schedules", {}, session=session)["data"] == [1, 2, 3]
