"""Zillow listing fetcher via unofficial RapidAPI endpoint.

Uses the "Zillow.com" API by apimaker on RapidAPI. The free tier allows
~100 requests/month which is enough for daily polling of 5 small towns.
"""
from __future__ import annotations

import os
import time
from typing import Any, Iterator

import requests


SEARCH_URL = "https://{host}/propertyExtendedSearch"
PROPERTY_URL = "https://{host}/property"
IMAGES_URL = "https://{host}/images"


def _headers() -> dict[str, str]:
    return {
        "x-rapidapi-key": os.environ["RAPIDAPI_KEY"],
        "x-rapidapi-host": os.environ.get("RAPIDAPI_HOST", "zillow-com1.p.rapidapi.com"),
    }


def _host() -> str:
    return os.environ.get("RAPIDAPI_HOST", "zillow-com1.p.rapidapi.com")


def search_town(
    location: str,
    min_price: int,
    max_price: int,
    min_beds: int,
    home_type: str = "Houses",
    status: str = "ForSale",
) -> Iterator[dict[str, Any]]:
    """Yield listings matching the filter for a single town. Handles pagination."""
    page = 1
    while True:
        params = {
            "location": location,
            "status_type": status,
            "home_type": home_type,
            "minPrice": str(min_price),
            "maxPrice": str(max_price),
            "bedsMin": str(min_beds),
            "page": str(page),
            "sort": "Newest",
        }
        resp = requests.get(SEARCH_URL.format(host=_host()), headers=_headers(), params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        props = data.get("props") or []
        if not props:
            return
        for p in props:
            yield p
        total_pages = data.get("totalPages", 1)
        if page >= total_pages:
            return
        page += 1
        time.sleep(0.5)


def get_property_detail(zpid: str) -> dict[str, Any]:
    """Fetch full detail for a single ZPID (sqft, year built, description, etc)."""
    resp = requests.get(
        PROPERTY_URL.format(host=_host()),
        headers=_headers(),
        params={"zpid": zpid},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_property_images(zpid: str, max_images: int = 6) -> list[str]:
    """Return up to max_images URLs for the listing."""
    try:
        resp = requests.get(
            IMAGES_URL.format(host=_host()),
            headers=_headers(),
            params={"zpid": zpid},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        images = data.get("images") or []
        return images[:max_images]
    except requests.HTTPError:
        return []


def fetch_all(towns: list[str], min_price: int, max_price: int, min_beds: int) -> list[dict[str, Any]]:
    """Fetch listings across all towns, deduplicated by zpid."""
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    for town in towns:
        for listing in search_town(town, min_price, max_price, min_beds):
            zpid = str(listing.get("zpid", ""))
            if not zpid or zpid in seen:
                continue
            seen.add(zpid)
            listing["_search_town"] = town
            results.append(listing)
        time.sleep(1.0)
    return results
