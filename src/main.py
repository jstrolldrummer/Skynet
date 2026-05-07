"""Daily orchestrator: fetch -> store -> score -> digest."""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv

from . import analyze, db, digest, fetch


def load_config() -> dict:
    path = Path(__file__).parent.parent / "config.yaml"
    return yaml.safe_load(path.read_text())


def run(dry_run: bool = False, no_email: bool = False) -> int:
    load_dotenv()
    config = load_config()
    db.init_db()

    search = config["search"]
    print(f"Fetching listings across {len(search['towns'])} towns...", flush=True)
    listings = fetch.fetch_all(
        towns=search["towns"],
        min_price=search["min_price"],
        max_price=search["max_price"],
        min_beds=search["min_beds"],
    )
    print(f"  fetched {len(listings)} listings", flush=True)

    new_count = 0
    price_change_count = 0
    for listing in listings:
        is_new, prev_price = db.upsert_listing(listing)
        if is_new:
            new_count += 1
        elif prev_price is not None and prev_price != (listing.get("price") or 0):
            price_change_count += 1
    print(f"  {new_count} new, {price_change_count} price changes", flush=True)

    print("Scoring listings...", flush=True)
    scored: list[dict] = []
    for i, listing in enumerate(listings, 1):
        zpid = str(listing.get("zpid", ""))
        if not zpid:
            continue

        description = listing.get("description") or ""
        sqft = listing.get("livingArea") or 0

        if not description and sqft:
            try:
                detail = fetch.get_property_detail(zpid)
                description = detail.get("description") or ""
                listing["description"] = description
                if not listing.get("yearBuilt"):
                    listing["yearBuilt"] = detail.get("yearBuilt")
                time.sleep(0.4)
            except Exception:
                pass

        image_urls: list[str] = []
        if not dry_run and sqft:
            try:
                image_urls = fetch.get_property_images(zpid, max_images=5)
                time.sleep(0.4)
            except Exception:
                pass

        if dry_run:
            rehab = {
                "per_sqft": config["scoring"]["rehab_cost_per_sqft_default"],
                "total": int(sqft * config["scoring"]["rehab_cost_per_sqft_default"]),
                "condition": "unknown",
                "notes": "dry run, vision skipped",
            }
        else:
            rehab = analyze.estimate_rehab_with_vision(
                image_urls=image_urls,
                description=description,
                sqft=sqft,
                default_per_sqft=config["scoring"]["rehab_cost_per_sqft_default"],
            )

        breakdown = analyze.score_listing(listing, listings, rehab, config)
        scored.append({"listing": listing, "breakdown": breakdown, "rehab": rehab})

        if i % 10 == 0:
            print(f"  scored {i}/{len(listings)}", flush=True)

    scored.sort(key=lambda x: x["breakdown"]["total_score"], reverse=True)

    threshold = config["digest"]["min_score_to_alert"]
    top_n = config["digest"]["top_n"]
    qualified = [s for s in scored if s["breakdown"]["total_score"] >= threshold][:top_n]

    if not qualified:
        print(f"No listings scored above threshold ({threshold}). No digest sent.", flush=True)
        return 0

    print(f"Building digest with {len(qualified)} deals...", flush=True)
    html = digest.build_html(qualified, total_listings=len(listings))

    if no_email or dry_run:
        out = Path(__file__).parent.parent / "data" / "digest_preview.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html)
        print(f"  digest written to {out} (no email sent)", flush=True)
    else:
        subject = f"CT Flip Watch — {len(qualified)} deals worth a look"
        digest.send_email(html, subject)
        for s in qualified:
            db.record_alert(
                str(s["listing"]["zpid"]),
                s["breakdown"]["total_score"],
                f"top-{top_n} digest",
            )
        print(f"  email sent to {os.environ['DIGEST_TO']}", flush=True)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Skip vision API and email")
    parser.add_argument("--no-email", action="store_true", help="Build digest but write to file instead of emailing")
    args = parser.parse_args()
    return run(dry_run=args.dry_run, no_email=args.no_email)


if __name__ == "__main__":
    sys.exit(main())
