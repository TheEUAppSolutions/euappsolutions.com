#!/usr/bin/env python3
"""Merge the curated per-app copy below with live App Store metadata into src/apps.json.

The curated half (display name, tagline, blurb, group, slug) is editorial and lives here.
The live half (rating, rating count, version, artwork URLs, last-updated) is pulled from the
iTunes lookup API, so re-running this keeps the numbers on the site honest.

    python3 src/make_apps_json.py          # refresh from the App Store
    python3 src/make_apps_json.py --offline  # reuse src/appstore-raw.json

Only apps whose App Store sellerName is SELLER are included. Apps that were sold on
(Zipo Apps, OD SP Z O O, BON APP & T LTD) are deliberately excluded -- see RETIRED in build.py.
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SELLER = "European apps solutions LTD"

# slug, bundleId, display name, group, tagline, blurb
CURATED = [
    (
        "time-warp-scan", "com.fipu.timewarp", "Time Warp Scan", "Photo & Video",
        "The blue-line scan effect, and two more ways to freeze a moment mid-frame.",
        "A line sweeps the frame and cements whatever it passes, so half the picture is "
        "live and half is already history. Three distinct effects, saved to your library "
        "or shared straight out of the app.",
    ),
    (
        "radio-fm", "com.yourcompany.fmtransmitter", "Radio FM", "Audio",
        "Thousands of live stations from every corner of the world.",
        "News, music, talk and sport from thousands of live stations, kept up to date "
        "automatically. Tell it your mood -- Relax, Workout, Focus, Driving, Party, Morning -- "
        "and it picks the station for you.",
    ),
    (
        "watch-facely", "cool.watchfaces.WatchFaces", "Watch Faces Gallery", "Lifestyle",
        "A gallery of custom Apple Watch faces, complications and widgets.",
        "Hundreds of watch faces from classic and minimal through to loud and graphic, plus "
        "screen widgets and themes. Browse, preview, and change the look of your Watch as "
        "often as you like.",
    ),
    (
        "triple-a-hd", "com.tada.triplea", "Triple A HD", "Lifestyle",
        "Fluid and light simulation you paint with a finger.",
        "Drag a finger and colour blooms behind it -- swirls of fluid, rays of light, "
        "hypnotic and slow. There is nothing to win and nothing to finish. It exists to "
        "slow you down.",
    ),
    (
        "resume-app", "com.eralpb.kolaycv", "Resume Builder", "Productivity",
        "Build a professional CV and cover letter, export to PDF in one tap.",
        "Over twenty professional templates, multiple profiles you can duplicate and tailor "
        "per application, AI-generated cover letters pulled from your own details, and a "
        "built-in job search. One tap exports a PDF ready to send.",
    ),
    (
        "dynamic-island", "com.deepansh.notch.NotchedOut", "Dynamic Island", "Photo & Video",
        "Wallpapers, widgets, custom icons and a configurable Dynamic Island.",
        "Thousands of HD and 3D live wallpapers sorted by category, with new ones weekly. "
        "Then go further: home screen and photo widgets, custom app icons, and a Dynamic "
        "Island you can configure yourself.",
    ),
    (
        "clear-wave", "com.tada.cleanwave", "Clear Wave", "Audio",
        "Pure tones from 50 Hz to 30 kHz, a sound-level meter, and speaker water ejection.",
        "Generate clean wave tones across the full audible range for testing acoustics, "
        "hearing, instruments and equipment -- sine, square, triangle and saw, adjustable "
        "live. It also measures the noise around you, and ejects trapped water from a "
        "phone speaker.",
    ),
    (
        "manga-reader-plus", "top.reader.manga.fox.vn", "Manga Reader Plus", "Reading",
        "Continuous-scroll manga reading with a private browsing mode.",
        "Comic mode gives you uninterrupted vertical reading with no page-turn interruptions. "
        "Privacy mode keeps what you read to yourself -- incognito browsing, encrypted "
        "activity, hidden sites.",
    ),
    (
        "snaptik", "com.ksunana.favtik", "Tiksave", "Utilities",
        "Pull the stats and info out of any video, then edit it.",
        "Read the numbers behind a video, then work on it: filters, speed changes, trimming, "
        "and audio extracted straight to MP3.",
    ),
    (
        "bro-browser", "com.fipu.brobrowser", "Bro Browser", "Utilities",
        "A browser built around Picture-in-Picture.",
        "Open a video, press the PiP button, and it keeps playing in a corner while you do "
        "something else entirely. Lock the screen and the audio carries on -- the problem "
        "every other mobile browser leaves unsolved.",
    ),
    (
        "glow-ai-scanner", "com.fipu.looksmax", "Glow AI Scanner", "Lifestyle",
        "AI facial analysis across six aesthetic dimensions.",
        "Upload a photo and get a rating broken down across six aspects of facial aesthetics, "
        "with specific feedback rather than a single number, plus a knowledge base and an "
        "active community.",
    ),
    (
        "hdmi-monitor", "com.fipu.monitor", "HDMI Monitor", "Utilities",
        "Turn an iPhone or iPad into a wired HDMI monitor.",
        "Pair the app with an HDMI-to-USB-C capture card and your device becomes a "
        "full-screen wired monitor for a games console, camera, set-top box or desktop. "
        "Useful when travelling, studying, or anywhere a screen is not.",
    ),
    (
        "xray-anatomy", "com.bonapp.xrayanatomy", "XRay Anatomy", "Reading",
        "Radiographic anatomy with labelled overlays and quiz modes.",
        "Explore detailed X-ray images with anatomy labelled on top, then test what stuck "
        "with interactive quizzes that track your progress. Built for students, healthcare "
        "professionals, and the plain curious.",
    ),
    (
        "sing-whiz", "com.fipu.vocalrange", "Sing Whiz", "Audio",
        "Find your lowest note, your highest, and the range in between.",
        "Sing along and the app maps your range -- the lowest note you can hold and the "
        "highest you can reach. For trained singers working out what suits their voice, and "
        "for everyone else who has simply wondered.",
    ),
    (
        "video-journal", "com.bonapp.journal", "TalkBook", "Productivity",
        "Talk for a minute. Get a searchable, transcribed journal entry.",
        "Press record and speak. On-device transcription in over fifty languages turns it "
        "into a searchable entry, with location, weather and step count attached quietly in "
        "the background -- and mood patterns surfacing over time.",
    ),
]


def lookup(bundle_id, offline_index):
    if offline_index is not None:
        return offline_index.get(bundle_id)
    for cc in ("us", "gb", "de"):
        url = f"https://itunes.apple.com/lookup?bundleId={bundle_id}&country={cc}"
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                data = json.load(r)
        except Exception as exc:  # network hiccup -- try the next storefront
            print(f"  ! {bundle_id} ({cc}): {exc}")
            continue
        if data.get("resultCount"):
            time.sleep(0.25)
            return data["results"][0]
    return None


def main():
    offline_index = None
    if "--offline" in sys.argv:
        raw = json.loads((ROOT / "src" / "appstore-raw.json").read_text())
        offline_index = {r["bundleId"]: r for r in raw if r.get("name")}
        # normalise the offline snapshot to iTunes API field names
        for r in offline_index.values():
            r.setdefault("trackName", r.get("name"))
            r.setdefault("trackId", r.get("id"))
            r.setdefault("sellerName", r.get("seller"))
            r.setdefault("primaryGenreName", r.get("genre"))
            r.setdefault("averageUserRating", r.get("rating"))
            r.setdefault("userRatingCount", r.get("ratingCount"))
            r.setdefault("artworkUrl512", r.get("icon"))
            r.setdefault("screenshotUrls", r.get("shots"))
            r.setdefault("trackViewUrl", r.get("url"))
            r.setdefault("currentVersionReleaseDate", r.get("updated"))
            r.setdefault("formattedPrice", r.get("price"))
            r.setdefault("releaseDate", r.get("released", ""))
            r.setdefault("languageCodesISO2A", r.get("langs") or [])
            r.setdefault("contentAdvisoryRating", r.get("age"))

    out, skipped = [], []
    for slug, bundle_id, name, group, tagline, blurb in CURATED:
        r = lookup(bundle_id, offline_index)
        if not r:
            skipped.append((slug, "not found on the App Store"))
            continue
        if r.get("sellerName") != SELLER:
            skipped.append((slug, f"seller is {r.get('sellerName')!r}"))
            continue
        out.append({
            "slug": slug,
            "name": name,
            "storeName": r["trackName"],
            "group": group,
            "tagline": tagline,
            "blurb": blurb,
            "bundleId": bundle_id,
            "appId": r["trackId"],
            "storeUrl": (r.get("trackViewUrl") or "").split("?")[0],
            "category": r.get("primaryGenreName"),
            "rating": round(r["averageUserRating"], 2) if r.get("averageUserRating") else None,
            "ratingCount": r.get("userRatingCount") or 0,
            "price": r.get("formattedPrice"),
            "age": r.get("contentAdvisoryRating"),
            "updated": (r.get("currentVersionReleaseDate") or "")[:10],
            "released": (r.get("releaseDate") or "")[:10],
            "languages": len(r.get("languageCodesISO2A") or []),
            "iconUrl": r.get("artworkUrl512"),
            "shotUrls": r.get("screenshotUrls") or [],
        })

    # the curated copy above is written in ASCII; render real punctuation on the way out
    for a in out:
        for field in ("tagline", "blurb"):
            a[field] = a[field].replace(" -- ", " \u2014 ")

    out.sort(key=lambda a: -a["ratingCount"])
    (ROOT / "src" / "apps.json").write_text(json.dumps(out, indent=1) + "\n")

    total = sum(a["ratingCount"] for a in out)
    weighted = sum((a["rating"] or 0) * a["ratingCount"] for a in out) / total
    print(f"{len(out)} apps -> src/apps.json")
    print(f"{total:,} ratings, weighted average {weighted:.2f}")
    for slug, why in skipped:
        print(f"skipped {slug}: {why}")


if __name__ == "__main__":
    main()
