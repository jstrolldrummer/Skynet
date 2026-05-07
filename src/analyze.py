"""Deal scoring and AI-driven rehab estimation."""
from __future__ import annotations

import base64
import json
import os
import statistics
from typing import Any

import anthropic
import requests

from . import db


CLAUDE_MODEL = "claude-opus-4-7"


def _claude() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def estimate_rehab_with_vision(
    image_urls: list[str],
    description: str,
    sqft: int,
    default_per_sqft: float,
) -> dict[str, Any]:
    """Use Claude vision to estimate rehab condition + cost from listing photos.

    Returns: {"per_sqft": float, "total": int, "condition": str, "notes": str}
    """
    if not image_urls or not sqft:
        total = int(sqft * default_per_sqft) if sqft else 0
        return {
            "per_sqft": default_per_sqft,
            "total": total,
            "condition": "unknown",
            "notes": "No images or sqft available; using default rehab cost.",
        }

    image_blocks: list[dict[str, Any]] = []
    for url in image_urls[:5]:
        try:
            r = requests.get(url, timeout=20)
            r.raise_for_status()
            b64 = base64.standard_b64encode(r.content).decode("utf-8")
            media_type = r.headers.get("content-type", "image/jpeg").split(";")[0]
            if media_type not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
                media_type = "image/jpeg"
            image_blocks.append({
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": b64},
            })
        except Exception:
            continue

    if not image_blocks:
        total = int(sqft * default_per_sqft)
        return {
            "per_sqft": default_per_sqft,
            "total": total,
            "condition": "unknown",
            "notes": "Image download failed; using default rehab cost.",
        }

    prompt = f"""You are a real estate flip analyst evaluating a property in Fairfield County, CT (luxury market: Greenwich, Stamford, Darien, New Canaan, Norwalk).

Square footage: {sqft}
Listing description excerpt:
\"\"\"{description[:1500]}\"\"\"

Looking at the photos and description, estimate the rehab needed to bring this property to a top-of-market resale-ready luxury condition.

Categorize condition as one of: turnkey, light_cosmetic, moderate, heavy, gut.

Estimate cost per square foot for the rehab in this luxury market:
- turnkey: $0-15/sqft
- light_cosmetic (paint, fixtures, minor): $25-50/sqft
- moderate (kitchens/baths, flooring): $75-125/sqft
- heavy (full systems, additions): $150-225/sqft
- gut (down to studs): $250-400/sqft

Respond ONLY with valid JSON:
{{"condition": "...", "per_sqft": <number>, "notes": "<2-3 sentence rationale citing specific things you see>"}}"""

    content_blocks: list[dict[str, Any]] = list(image_blocks)
    content_blocks.append({"type": "text", "text": prompt})

    try:
        msg = _claude().messages.create(
            model=CLAUDE_MODEL,
            max_tokens=600,
            messages=[{"role": "user", "content": content_blocks}],
        )
        text = msg.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        parsed = json.loads(text)
        per_sqft = float(parsed.get("per_sqft", default_per_sqft))
        return {
            "per_sqft": per_sqft,
            "total": int(per_sqft * sqft),
            "condition": parsed.get("condition", "unknown"),
            "notes": parsed.get("notes", ""),
        }
    except Exception as e:
        total = int(sqft * default_per_sqft)
        return {
            "per_sqft": default_per_sqft,
            "total": total,
            "condition": "unknown",
            "notes": f"Vision analysis failed ({type(e).__name__}); using default cost.",
        }


def detect_distressed_signals(description: str, keywords: list[str]) -> list[str]:
    if not description:
        return []
    haystack = description.lower()
    return sorted({k for k in keywords if k.lower() in haystack})


def estimate_arv(listing: dict[str, Any], all_listings: list[dict[str, Any]]) -> int | None:
    """Crude ARV: median price/sqft of comps in same town with similar size, applied to this listing's sqft.

    NOTE: This uses *active* listings as comps. For real flip math you want SOLD comps,
    which requires a paid data source. Treat ARV as directional only.
    """
    sqft = listing.get("livingArea") or 0
    if not sqft:
        return None
    town = listing.get("_search_town")
    target_zpid = str(listing.get("zpid"))

    comps = [
        l for l in all_listings
        if l.get("_search_town") == town
        and str(l.get("zpid")) != target_zpid
        and l.get("livingArea")
        and l.get("price")
        and 0.7 * sqft <= l["livingArea"] <= 1.3 * sqft
    ]
    if len(comps) < 3:
        return None

    ppsqft = [c["price"] / c["livingArea"] for c in comps]
    median_ppsqft = statistics.median(ppsqft)
    return int(median_ppsqft * sqft)


def town_median_ppsqft(all_listings: list[dict[str, Any]], town: str) -> float | None:
    values = [
        l["price"] / l["livingArea"]
        for l in all_listings
        if l.get("_search_town") == town and l.get("price") and l.get("livingArea")
    ]
    if len(values) < 5:
        return None
    return statistics.median(values)


def score_listing(
    listing: dict[str, Any],
    all_listings: list[dict[str, Any]],
    rehab: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Score 0-100 across weighted signals. Returns dict with score + breakdown."""
    weights = config["scoring"]["weights"]
    luxury_multiplier = config["scoring"]["luxury_multiplier"]
    selling_costs_pct = config["scoring"]["selling_costs_pct"]
    distressed_keywords = config["distressed_keywords"]

    price = listing.get("price") or 0
    sqft = listing.get("livingArea") or 0
    town = listing.get("_search_town")
    description = (listing.get("description") or "")
    zpid = str(listing.get("zpid"))

    arv = estimate_arv(listing, all_listings)
    rehab_cost = rehab["total"]

    breakdown: dict[str, Any] = {
        "price": price,
        "sqft": sqft,
        "arv_estimate": arv,
        "rehab_cost": rehab_cost,
        "rehab_condition": rehab["condition"],
    }

    seventy_score = 0.0
    if arv and price:
        max_bid = (arv * luxury_multiplier) - rehab_cost - (arv * selling_costs_pct)
        margin_ratio = (max_bid - price) / arv if arv else 0
        seventy_score = max(0.0, min(1.0, 0.5 + margin_ratio * 4))
        breakdown["max_bid"] = int(max_bid)
        breakdown["potential_profit"] = int(arv - price - rehab_cost - (arv * selling_costs_pct))
    breakdown["seventy_score"] = round(seventy_score, 3)

    ppsqft_score = 0.0
    median_ppsqft = town_median_ppsqft(all_listings, town) if town else None
    if median_ppsqft and sqft and price:
        listing_ppsqft = price / sqft
        delta = (median_ppsqft - listing_ppsqft) / median_ppsqft
        ppsqft_score = max(0.0, min(1.0, 0.5 + delta * 2))
        breakdown["listing_ppsqft"] = round(listing_ppsqft, 2)
        breakdown["town_median_ppsqft"] = round(median_ppsqft, 2)
    breakdown["ppsqft_score"] = round(ppsqft_score, 3)

    dom_score = 0.0
    dom = listing.get("daysOnZillow") or 0
    if dom >= 180:
        dom_score = 1.0
    elif dom >= 90:
        dom_score = 0.7
    elif dom >= 45:
        dom_score = 0.4
    elif dom >= 14:
        dom_score = 0.15
    breakdown["days_on_market"] = dom
    breakdown["dom_score"] = round(dom_score, 3)

    signals = detect_distressed_signals(description, distressed_keywords)
    distressed_score = min(1.0, 0.25 * len(signals))
    breakdown["distressed_signals"] = signals
    breakdown["distressed_score"] = round(distressed_score, 3)

    drop_pct = db.get_total_price_drop_pct(zpid)
    drop_count = db.get_price_drop_count(zpid)
    drop_score = min(1.0, drop_pct * 5 + drop_count * 0.15)
    breakdown["price_drop_pct"] = round(drop_pct, 3)
    breakdown["price_drop_count"] = drop_count
    breakdown["drop_score"] = round(drop_score, 3)

    total = (
        seventy_score * weights["seventy_percent_rule"]
        + ppsqft_score * weights["price_per_sqft_vs_median"]
        + dom_score * weights["days_on_market"]
        + distressed_score * weights["distressed_signals"]
        + drop_score * weights["price_drop_history"]
    ) * 100

    breakdown["total_score"] = round(total, 1)
    return breakdown
