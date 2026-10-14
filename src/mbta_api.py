"""Talking to the MBTA V3 API politely, and translating its ids to the files' ids."""
from __future__ import annotations

import logging
import os
import time

import requests

BASE_URL = "https://api-v3.mbta.com"
KNOWN_DIRECTIONS = ("Inbound", "Outbound")


class MbtaApiError(Exception):
    pass


def _api_key():
    return os.environ.get("MBTA_API_KEY") or None   # optional: works without, just slower


def seconds_between_requests() -> float:
    # 20 requests/minute without a key, 1,000/minute with one.
    return 0.1 if _api_key() else 3.1


def get_json(path, params=None, max_retries=4, session=None, sleep=time.sleep) -> dict:
    """GET with the house rules: back off on 429, retry 5xx a few times,
    never retry other 4xx (our request is wrong; repeating it is spam).
    Follows `links.next` if the API paginates, and merges the `data` lists."""
    http = session or requests
    headers = {"x-api-key": _api_key()} if _api_key() else {}
    url, merged = BASE_URL + path, None
    while url:
        for attempt in range(max_retries + 1):
            resp = http.get(url, params=params, headers=headers, timeout=30)
            status = resp.status_code
            if status == 200:
                break
            retryable = status == 429 or 500 <= status < 600
            if not retryable or attempt == max_retries:
                raise MbtaApiError(f"HTTP {status} for {url} {params}: {resp.text[:200]}")
            wait = 2 ** (attempt + 1)                      # 2, 4, 8, 16 seconds
            logging.warning("HTTP %s for %s, retrying in %ss", status, path, wait)
            sleep(wait)
        payload = resp.json()
        if merged is None:
            merged = payload
        else:
            merged["data"].extend(payload.get("data", []))
        url = (payload.get("links") or {}).get("next")
        params = None                                      # the next link already has them
    return merged


def bus_route_lookup(session=None) -> dict:
    """{short_name: {"id": api_id, "direction_names": [...]}} for every bus route."""
    payload = get_json("/routes", {"filter[type]": "3"}, session=session)
    return {
        item["attributes"]["short_name"]: {
            "id": item["id"],
            "direction_names": item["attributes"].get("direction_names") or [],
        }
        for item in payload["data"]
    }


def to_api_route(file_route_id: str, lookup: dict):
    """File-style route id -> API route info, or None if the API doesn't know it.

    '01' -> short name '1' -> id '1';  'SL1' -> id '741';  'CT2' -> None.
    """
    short_name = file_route_id.lstrip("0") or file_route_id
    return lookup.get(short_name) or lookup.get(file_route_id)


def direction_word(direction_id, direction_names) -> str | None:
    """API 0/1 -> the files' word. For MBTA buses 1 = Inbound, 0 = Outbound;
    the route's own direction_names win when they use the same words."""
    if direction_id in (0, 1) and len(direction_names) > direction_id:
        name = direction_names[direction_id]
        if name in KNOWN_DIRECTIONS:
            return name
    return {1: "Inbound", 0: "Outbound"}.get(direction_id)


def schedules_to_records(data: list, file_route_id: str, direction_names: list) -> list[dict]:
    """One /schedules JSON item -> one flat dict in the files' vocabulary."""
    records = []
    for item in data:
        attrs, rels = item["attributes"], item["relationships"]
        trip = (rels.get("trip") or {}).get("data") or {}
        records.append({
            "route_id": file_route_id,
            "direction_id": direction_word(attrs.get("direction_id"), direction_names),
            "stop_id": rels["stop"]["data"]["id"],
            "half_trip_id": trip.get("id"),
            # departure_time, falling back to arrival_time at the last stop
            "scheduled_raw": attrs.get("departure_time") or attrs.get("arrival_time"),
        })
    return records
