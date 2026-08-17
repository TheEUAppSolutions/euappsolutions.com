#!/usr/bin/env python3
"""Post-build checks. Exits non-zero if anything is broken.

Verifies that every internal link and asset reference resolves on disk, that the
App Store links point at real listings, that titles/descriptions are unique and
present, and that no editorial placeholders leaked into the output.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://euappsolutions.com"

# must match the --base the site was built with, so hrefs resolve back to disk
BASE = ""
if "--base" in sys.argv:
    BASE = "/" + sys.argv[sys.argv.index("--base") + 1].strip("/")

problems = []


def note(page, message):
    problems.append(f"{page}: {message}")


def resolve(href):
    """Map a site-absolute href to the file that would be served."""
    path = href.split("#")[0].split("?")[0]
    if not path.startswith("/"):
        return None
    if BASE:
        if not path.startswith(BASE + "/") and path != BASE:
            return None
        path = path[len(BASE):] or "/"
    target = ROOT / path.lstrip("/")
    if path.endswith("/") or not target.suffix:
        return (ROOT / path.strip("/") / "index.html") if path.strip("/") else ROOT / "index.html"
    return target


def main():
    pages = sorted(p for p in ROOT.rglob("*.html") if "src" not in p.parts)
    if not pages:
        print("no pages found — run build.py first")
        return 1

    apps = json.loads((ROOT / "src" / "apps.json").read_text())
    store_urls = {a["storeUrl"] for a in apps}
    titles, descriptions = {}, {}

    for page in pages:
        rel = page.relative_to(ROOT)
        doc = page.read_text(encoding="utf-8")

        title = re.search(r"<title>(.*?)</title>", doc, re.S)
        if not title or not title.group(1).strip():
            note(rel, "missing <title>")
        else:
            titles.setdefault(title.group(1), []).append(str(rel))

        desc = re.search(r'<meta name="description" content="(.*?)"', doc)
        if not desc or len(desc.group(1)) < 40:
            note(rel, "missing or very short meta description")
        else:
            descriptions.setdefault(desc.group(1), []).append(str(rel))

        if not re.search(r'<link rel="canonical" href="https://', doc):
            note(rel, "missing canonical URL")

        if re.search(r"\s--\s", re.sub(r"(?is)<(script|style).*?</\1>", "", doc)):
            note(rel, "ASCII '--' placeholder left in visible copy")

        for href in re.findall(r'href="([^"]+)"', doc):
            if href.startswith(("http", "mailto:", "#", "data:")):
                continue
            target = resolve(href)
            if target is None:
                note(rel, f"relative href that will break on nested pages: {href}")
            elif not target.exists():
                note(rel, f"dead link {href} -> {target.relative_to(ROOT)}")

        for src in re.findall(r'src="([^"]+)"', doc):
            if src.startswith(("http", "data:")):
                continue
            target = resolve(src)
            if target is None or not target.exists():
                note(rel, f"missing asset {src}")

        for img in re.findall(r"<img\b[^>]*>", doc):
            if 'alt="' not in img:
                note(rel, f"<img> without alt: {img[:70]}")

        for store in re.findall(r'href="(https://apps\.apple\.com[^"]+)"', doc):
            if store not in store_urls:
                note(rel, f"App Store link not in apps.json: {store}")

        for ld in re.findall(r'<script type="application/ld\+json">(.*?)</script>', doc, re.S):
            try:
                json.loads(ld)
            except json.JSONDecodeError as exc:
                note(rel, f"invalid JSON-LD: {exc}")

    for title, where in titles.items():
        if len(where) > 1:
            problems.append(f"duplicate <title> {title!r} on {', '.join(where)}")
    for desc, where in descriptions.items():
        if len(where) > 1:
            problems.append(f"duplicate description on {', '.join(where)}")

    # every app in the data set must have a page, an icon, and appear in the sitemap
    sitemap = (ROOT / "sitemap.xml").read_text()
    for app in apps:
        page = ROOT / "apps" / app["slug"] / "index.html"
        if not page.exists():
            problems.append(f"no page for {app['slug']}")
        if not (ROOT / "assets" / "img" / "icons" / f"{app['slug']}.webp").exists():
            problems.append(f"no icon for {app['slug']}")
        if f"{SITE}/apps/{app['slug']}/" not in sitemap:
            problems.append(f"{app['slug']} missing from sitemap")

    required = [".nojekyll", "robots.txt", "404.html"]
    if not BASE:
        # a --base build is a github.io preview; the custom domain only applies at the root
        required.append("CNAME")
    for name in required:
        if not (ROOT / name).exists():
            problems.append(f"missing {name}")

    print(f"checked {len(pages)} pages, {len(apps)} apps")
    if problems:
        print(f"\n{len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
