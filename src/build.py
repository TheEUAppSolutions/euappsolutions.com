#!/usr/bin/env python3
"""Generate the euappsolutions.com static site.

    python3 src/build.py                 # build for the custom domain (paths at /)
    python3 src/build.py --base /repo    # build for a github.io project URL

Everything is written to the repository root so GitHub Pages can serve the branch
directly. Sources live in src/ and assets/ and are left alone.
"""
import html
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"

SITE = "https://euappsolutions.com"
COMPANY = "European Apps Solutions"
COMPANY_LEGAL = "European Apps Solutions LTD"
EMAIL = "info@euappsolutions.com"
ADDRESS = ["71-75 Shelton Street", "Covent Garden", "London WC2H 9JQ", "United Kingdom"]
TIKTOK = "https://www.tiktok.com/@musica.ai.app"
# the subscription portal the current site links to (tracking parameters stripped)
SUBSCRIPTIONS = "https://eu-apps-solution.web2wave.com/manga-manage-subscription"

BASE = ""

# Pages that existed on the WordPress site but have no equivalent now. Apps that were
# sold on keep their old URL as an explanation rather than a dead link, because those
# URLs are still cited from old App Store listings and directories.
RETIRED = {
    "apps/wump": ("WUMP — Who Touched My Phone?",
                  "This app is no longer published by European Apps Solutions."),
    "apps/finger-picker": ("Finger Picker — Random Chooser",
                           "This app is no longer published by European Apps Solutions."),
    "apps/my-smart-keys": ("My Smart Keys — CarPlay Connect",
                           "This app is no longer available on the App Store."),
}

# On WordPress these two were 301s, so they never appeared in the sitemap -- but six live
# App Store listings cite them (Radio FM, Watch Faces Gallery, HDMI Monitor, XRay Anatomy,
# TalkBook, Finger Picker). Pages cannot issue redirects, so serve the same text at both
# paths and let rel=canonical point at the primary one.
#   alias path -> slug whose content and canonical URL it borrows
LEGAL_ALIASES = {
    "privacy-policy": "privacy-policy-looksmax",
    "terms-of-use": "terms-of-use-wristtube",
}

GROUPS = ["Utilities", "Photo & Video", "Audio", "Lifestyle", "Reading", "Productivity"]

pages_built = []


# --- helpers -----------------------------------------------------------------

def e(text):
    return html.escape(str(text), quote=True)


def url(path=""):
    path = path.strip("/")
    return f"{BASE}/{path}/" if path else f"{BASE}/"


def asset(path):
    return f"{BASE}/assets/{path.lstrip('/')}"


def thousands(n):
    return f"{n:,}"


def webp_size(path):
    """(width, height) from a WebP header, so <img> carries a correct aspect ratio.

    Without real dimensions the browser reserves the wrong box and the page jumps when
    the screenshots decode. Handles the three chunk types cwebp can emit.
    """
    data = path.read_bytes()[:32]
    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None
    kind = data[12:16]
    if kind == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
        w = int.from_bytes(data[26:28], "little") & 0x3FFF
        h = int.from_bytes(data[28:30], "little") & 0x3FFF
        return w, h
    if kind == b"VP8L" and data[20:21] == b"\x2f":
        bits = int.from_bytes(data[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if kind == b"VP8X":
        return (int.from_bytes(data[24:27], "little") + 1,
                int.from_bytes(data[27:30], "little") + 1)
    return None


def icon(name):
    paths = {
        "arrow": '<path d="M4 10h12m0 0-4.5-4.5M16 10l-4.5 4.5" stroke="currentColor" '
                 'stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
        "apple": '<path d="M13.6 10.6c0-2 1.6-2.9 1.7-3-1-1.4-2.4-1.6-2.9-1.6-1.2-.1-2.4.7-3 .7s-1.6-.7-2.6-.7C5.5 6 4.3 6.8 3.6 8c-1.3 2.3-.3 5.7 1 7.6.6.9 1.4 1.9 2.4 1.9s1.3-.6 2.5-.6 1.5.6 2.6.6 1.7-.9 2.3-1.8c.7-1 1-2 1-2.1s-2-.8-2-3zM11.7 4.7c.5-.7.9-1.6.8-2.5-.8 0-1.8.5-2.4 1.2-.5.6-1 1.6-.8 2.5.9.1 1.8-.4 2.4-1.2z" fill="currentColor"/>',
        "sun": '<circle cx="8" cy="8" r="3.2" fill="currentColor"/><path d="M8 .8v1.8M8 13.4v1.8M15.2 8h-1.8M2.6 8H.8M13.1 2.9l-1.3 1.3M4.2 11.8l-1.3 1.3M13.1 13.1l-1.3-1.3M4.2 4.2 2.9 2.9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>',
        "moon": '<path d="M14 9.8A6.2 6.2 0 0 1 6.2 2 6.4 6.4 0 1 0 14 9.8z" fill="currentColor"/>',
    }
    box = "0 0 20 20" if name == "arrow" else "0 0 16 16"
    return f'<svg viewBox="{box}" aria-hidden="true" focusable="false">{paths[name]}</svg>'


def mark():
    return (
        '<svg class="brand__mark" viewBox="0 0 32 32" aria-hidden="true" focusable="false">'
        '<defs><linearGradient id="m" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#3B5BDB"/><stop offset="1" stop-color="#1B2F9E"/>'
        '</linearGradient></defs>'
        '<rect width="32" height="32" rx="8.5" fill="url(#m)"/>'
        '<path d="M9.5 11.5h13M9.5 16h9.5M9.5 20.5h6" stroke="#fff" stroke-width="2.75" '
        'stroke-linecap="round"/></svg>'
    )


# --- chrome ------------------------------------------------------------------

def head(title, description, path, *, image=None, jsonld=None, noindex=False,
         canonical_path=None):
    # canonical_path lets an alias page point at the URL it duplicates
    path = canonical_path if canonical_path is not None else path
    canonical = SITE + url(path).replace(BASE, "", 1) if BASE else SITE + url(path)
    image = image or (SITE + asset("img/og.png").replace(BASE, "", 1) if BASE
                      else SITE + asset("img/og.png"))
    ld = f'\n<script type="application/ld+json">{json.dumps(jsonld)}</script>' if jsonld else ""
    robots = '\n<meta name="robots" content="noindex,follow">' if noindex else ""
    return f"""<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(description)}">
<link rel="canonical" href="{e(canonical)}">{robots}
<meta property="og:type" content="website">
<meta property="og:site_name" content="{e(COMPANY)}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(description)}">
<meta property="og:url" content="{e(canonical)}">
<meta property="og:image" content="{e(image)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#ffffff" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0a0a0c" media="(prefers-color-scheme: dark)">
<link rel="icon" href="{asset('img/mark.svg')}" type="image/svg+xml">
<link rel="apple-touch-icon" href="{asset('img/apple-touch-icon.png')}">
<link rel="stylesheet" href="{asset('css/site.css')}">
<script>
// set the stored theme before first paint so the page never flashes the wrong palette
try{{var t=localStorage.getItem('theme');if(t==='light'||t==='dark')
document.documentElement.setAttribute('data-theme',t);}}catch(e){{}}
</script>
<noscript><style>.reveal{{opacity:1;transform:none}}</style></noscript>{ld}
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
"""


def masthead(current):
    links = [("Apps", "apps"), ("About", "about"), ("Contact", "contact")]
    # built with .format rather than an f-string: a backslash inside an f-string
    # expression is a syntax error before Python 3.12, and macOS ships 3.9
    nav = "".join(
        '<a href="{}"{}>{}</a>'.format(
            url(slug), ' aria-current="page"' if current == slug else "", label)
        for label, slug in links
    )
    return f"""<header class="masthead">
<div class="wrap masthead__inner">
<a class="brand" href="{url()}" aria-label="{e(COMPANY)} — home">
{mark()}
<span class="brand__text">EU Apps <span>Solutions</span></span>
</a>
<nav class="nav" aria-label="Main">{nav}</nav>
<button class="theme-toggle" type="button" aria-label="Switch theme">
<span class="icon-light">{icon('sun')}</span><span class="icon-dark">{icon('moon')}</span>
</button>
</div>
</header>
<main id="main">
"""


def footer(apps):
    top = apps[:6]
    app_links = "".join(
        f'<li><a href="{url("apps/" + a["slug"])}">{e(a["name"])}</a></li>' for a in top
    )
    return f"""</main>
<footer class="footer">
<div class="wrap">
<div class="footer__grid">
<div class="footer__about">
<a class="brand" href="{url()}">{mark()}<span class="brand__text">EU Apps <span>Solutions</span></span></a>
<p>A UK company designing and publishing apps for iPhone, iPad and Apple Watch.
{len(apps)} live on the App Store.</p>
</div>
<div class="footer__col">
<h4>Apps</h4>
<ul>{app_links}<li><a href="{url('apps')}">All {len(apps)} apps</a></li></ul>
</div>
<div class="footer__col">
<h4>Company</h4>
<ul>
<li><a href="{url('about')}">About</a></li>
<li><a href="{url('contact')}">Contact</a></li>
<li><a href="mailto:{EMAIL}">{EMAIL}</a></li>
<li><a href="{TIKTOK}" rel="noopener">TikTok</a></li>
</ul>
</div>
<div class="footer__col">
<h4>Support</h4>
<ul>
<li><a href="{SUBSCRIPTIONS}" rel="noopener">Manage subscriptions</a></li>
<li><a href="{url('privacy-policy-looksmax')}">Privacy Policy</a></li>
<li><a href="{url('terms-of-use-wristtube')}">Terms of Use (WristTube)</a></li>
<li><a href="{url('term-of-use')}">Terms of Use</a></li>
</ul>
</div>
</div>
<div class="footer__base">
<span>&copy; {date.today().year} {e(COMPANY_LEGAL)}</span>
<span>{e(', '.join(ADDRESS))}</span>
</div>
</div>
</footer>
<script src="{asset('js/site.js')}" defer></script>
</body>
</html>
"""


# --- components --------------------------------------------------------------

def rating_bit(app):
    if not app["rating"]:
        return f'<span>{e(app["category"])}</span>'
    return (
        f'<span class="rating"><svg viewBox="0 0 16 16" aria-hidden="true">'
        f'<path d="M8 1.3l2 4.1 4.5.7-3.3 3.2.8 4.5L8 11.6l-4 2.1.8-4.5L1.5 6.1l4.5-.7z"/>'
        f'</svg>{app["rating"]:.1f}</span>'
        f'<span class="dot"></span><span>{thousands(app["ratingCount"])} ratings</span>'
        f'<span class="dot"></span><span>{e(app["category"])}</span>'
    )


def app_card(app):
    return f"""<a class="app-card" href="{url('apps/' + app['slug'])}" data-group="{e(app['group'])}">
<img class="app-card__icon" src="{asset('img/icons/' + app['slug'] + '.webp')}"
 alt="" width="58" height="58" loading="lazy" decoding="async">
<span class="app-card__body">
<span class="app-card__name">{e(app['name'])}</span>
<span class="app-card__tag">{e(app['tagline'])}</span>
<span class="app-card__meta">{rating_bit(app)}</span>
</span>
</a>"""


def app_grid(apps, *, filters=True):
    counts = {g: sum(1 for a in apps if a["group"] == g) for g in GROUPS}
    bar = ""
    if filters:
        chips = [f'<button class="filter" type="button" data-group="all" aria-pressed="true">'
                 f'All<span class="filter__count">{len(apps)}</span></button>']
        for g in GROUPS:
            if not counts[g]:
                continue
            chips.append(f'<button class="filter" type="button" data-group="{e(g)}" '
                         f'aria-pressed="false">{e(g)}'
                         f'<span class="filter__count">{counts[g]}</span></button>')
        bar = f'<div class="filters" data-filters role="group" aria-label="Filter apps">' \
              f'{"".join(chips)}</div>'
    cards = "\n".join(app_card(a) for a in apps)
    return f"""{bar}
<div class="app-grid" data-app-grid>
{cards}
</div>
<p class="empty" data-empty hidden>No apps in that category.</p>"""


def store_button(app, label="View on the App Store"):
    return (f'<a class="btn btn--primary" href="{e(app["storeUrl"])}" rel="noopener">'
            f'{icon("apple")}{label}</a>')


# --- pages -------------------------------------------------------------------

def write(path, content):
    out = ROOT / (path if path.endswith(".html") or path.endswith(".xml")
                  or path.endswith(".txt") else f"{path}/index.html".lstrip("/"))
    if path == "":
        out = ROOT / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    pages_built.append(str(out.relative_to(ROOT)))


def page_home(apps, totals):
    # Each row animates by -50%, so its content must be exactly two identical halves.
    # Repeat the source list enough times that one half is wider than any viewport
    # (each tile is 76px + a 14px gap), otherwise the row runs out mid-screen.
    def marquee_row(items, reps=3):
        seq = items * reps
        return "".join(
            f'<a href="{url("apps/" + a["slug"])}" aria-label="{e(a["name"])}" tabindex="-1">'
            f'<img src="{asset("img/icons/" + a["slug"] + ".webp")}" alt="" width="76"'
            f' height="76" loading="lazy" decoding="async"></a>'
            for a in seq * 2
        )

    half = len(apps) // 2
    row_a = marquee_row(apps[:half])
    row_b = marquee_row(apps[half:])

    jsonld = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": COMPANY_LEGAL,
        "alternateName": COMPANY,
        "url": SITE + "/",
        "email": EMAIL,
        "logo": SITE + "/assets/img/mark.svg",
        "sameAs": [TIKTOK],
        "address": {
            "@type": "PostalAddress",
            "streetAddress": "71-75 Shelton Street, Covent Garden",
            "addressLocality": "London",
            "postalCode": "WC2H 9JQ",
            "addressCountry": "GB",
        },
    }

    return head(
        f"{COMPANY} — iOS apps, built in Europe",
        f"{COMPANY} designs and publishes apps for iPhone, iPad and Apple Watch. "
        f"{totals['count']} live on the App Store, {thousands(totals['ratings'])} ratings, "
        f"a {totals['avg']:.1f} average.",
        "", jsonld=jsonld,
    ) + masthead("") + f"""
<section class="hero">
<div class="wrap hero__grid">
<p class="eyebrow">London &middot; Apps for Apple platforms</p>
<h1>We make small apps<em>that people keep.</em></h1>
<p class="lede">{totals['count']} apps live on the App Store, {thousands(totals['ratings'])}
ratings between them and a {totals['avg']:.1f} average. Utilities, audio tools, readers and
the odd thing that just exists to be calming.</p>
<div class="btn-row">
<a class="btn btn--primary" href="{url('apps')}">Browse the apps {icon('arrow')}</a>
<a class="btn btn--ghost" href="{SUBSCRIPTIONS}" rel="noopener">Manage subscriptions</a>
</div>
<div class="stats">
<div class="stat"><span class="stat__num">{totals['count']}</span>
<span class="stat__label">Apps live</span></div>
<div class="stat"><span class="stat__num">{thousands(totals['ratings'])}</span>
<span class="stat__label">Ratings</span></div>
<div class="stat"><span class="stat__num">{totals['avg']:.2f}</span>
<span class="stat__label">Average score</span></div>
<div class="stat"><span class="stat__num">{totals['categories']}</span>
<span class="stat__label">Categories</span></div>
</div>
</div>
<div class="wrap">
<div class="marquee" aria-hidden="true">
<div class="marquee__row marquee__row--a">{row_a}</div>
<div class="marquee__row marquee__row--b">{row_b}</div>
</div>
</div>
</section>

<section class="section section--sub" id="apps">
<div class="wrap">
<div class="section-head reveal">
<p class="eyebrow">The portfolio</p>
<h2>Every app we publish</h2>
<p class="lede">All {totals['count']} are live on the App Store right now. Ratings come
straight from Apple and are refreshed when the site is rebuilt.</p>
</div>
<div class="reveal">
{app_grid(apps)}
</div>
</div>
</section>

<section class="section">
<div class="wrap">
<div class="section-head reveal">
<p class="eyebrow">Work with us</p>
<h2>We build for other people too</h2>
<p class="lede">The same team, the same pipeline, pointed at someone else's idea. Most
useful to people who have a product in mind and no iOS team to build it.</p>
</div>
<div class="cols reveal">
<div class="col">
<span class="col__num">01 &mdash; Design</span>
<h3>Decide what it's for</h3>
<p>Work out what the app is actually for, then cut everything that isn't that. One screen
usually has to carry the whole thing.</p>
</div>
<div class="col">
<span class="col__num">02 &mdash; Build</span>
<h3>Native, and kept current</h3>
<p>Swift and SwiftUI, built against the current iOS and moved forward as the platform
moves. No cross-platform layer between you and the device.</p>
</div>
<div class="col">
<span class="col__num">03 &mdash; Ship</span>
<h3>Through review and out</h3>
<p>Store listing, screenshots, localisation, subscriptions, review and release &mdash;
then the updates afterwards. The part where most projects stall.</p>
</div>
</div>
</div>
</section>

<section class="section section--tight">
<div class="wrap">
<div class="callout reveal">
<div class="callout__text">
<h2>Got something you want built?</h2>
<p>Tell us what it is and what it has to do. We'll tell you whether we're the right
people for it.</p>
</div>
<div class="btn-row">
<a class="btn btn--primary" href="mailto:{EMAIL}">{EMAIL}</a>
<a class="btn btn--ghost" href="{url('contact')}">Contact {icon('arrow')}</a>
</div>
</div>
</div>
</section>
""" + footer(apps)


def page_apps(apps, totals):
    return head(
        f"Apps — {COMPANY}",
        f"All {totals['count']} apps published by {COMPANY}: utilities, audio tools, "
        f"photo and video, readers and productivity, on iPhone, iPad and Apple Watch.",
        "apps",
    ) + masthead("apps") + f"""
<section class="section section--tight">
<div class="wrap">
<div class="section-head">
<p class="eyebrow">{totals['count']} apps &middot; {thousands(totals['ratings'])} ratings</p>
<h1>Apps</h1>
<p class="lede">Everything we currently publish on the App Store. Free to download, with
optional subscriptions where an app has running costs behind it.</p>
</div>
{app_grid(apps)}
</div>
</section>

<section class="section section--tight">
<div class="wrap">
<div class="callout">
<div class="callout__text">
<h2>Already subscribed to one of these?</h2>
<p>Manage or cancel a subscription through the portal, or write to us and we'll sort it.</p>
</div>
<div class="btn-row">
<a class="btn btn--primary" href="{SUBSCRIPTIONS}" rel="noopener">Manage subscriptions</a>
<a class="btn btn--ghost" href="mailto:{EMAIL}">Email support</a>
</div>
</div>
</div>
</section>
""" + footer(apps)


def page_app(app, apps):
    shot_dir = ROOT / "assets" / "img" / "shots" / app["slug"]
    shots = sorted(shot_dir.glob("*.webp"), key=lambda p: int(p.stem)) if shot_dir.exists() else []
    shots_html = ""
    if shots:
        def shot_img(i, s):
            size = webp_size(s)
            dims = f' width="{size[0]}" height="{size[1]}"' if size else ""
            return (f'<img src="{asset("img/shots/" + app["slug"] + "/" + s.name)}"'
                    f' alt="{e(app["name"])} screenshot {i + 1}" loading="lazy"'
                    f' decoding="async"{dims}>')

        imgs = "".join(shot_img(i, s) for i, s in enumerate(shots))
        shots_html = f"""
<section class="section section--tight">
<div class="wrap">
<div class="section-head"><p class="eyebrow">Screenshots</p></div>
<div class="shots">{imgs}</div>
</div>
</section>"""

    facts = [("Category", app["category"]), ("Price", app["price"] or "Free")]
    if app["rating"]:
        facts.append(("Rating", f'{app["rating"]:.1f} from {thousands(app["ratingCount"])}'))
    if app["languages"]:
        facts.append(("Languages", str(app["languages"])))
    if app["age"]:
        facts.append(("Age rating", app["age"]))
    if app["updated"]:
        facts.append(("Last updated", app["updated"]))
    facts_html = "".join(
        f'<div class="fact"><div class="fact__label">{e(k)}</div>'
        f'<div class="fact__value">{e(v)}</div></div>' for k, v in facts
    )

    others = [a for a in apps if a["slug"] != app["slug"]][:3]
    more = "\n".join(app_card(a) for a in others)

    jsonld = {
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "name": app["storeName"],
        "alternateName": app["name"],
        "operatingSystem": "iOS",
        "applicationCategory": app["category"],
        "url": app["storeUrl"],
        "description": app["tagline"],
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
        "publisher": {"@type": "Organization", "name": COMPANY_LEGAL},
    }
    if app["rating"] and app["ratingCount"]:
        jsonld["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": round(app["rating"], 2),
            "ratingCount": app["ratingCount"],
            "bestRating": 5,
            "worstRating": 1,
        }

    og = SITE + f"/assets/img/icons/{app['slug']}@512.png"
    return head(
        f"{app['name']} — {COMPANY}",
        app["tagline"],
        f"apps/{app['slug']}",
        image=og, jsonld=jsonld,
    ) + masthead("apps") + f"""
<section class="app-hero">
<div class="wrap">
<p class="eyebrow" style="margin-bottom:26px">
<a href="{url('apps')}">Apps</a> &nbsp;/&nbsp; {e(app['name'])}</p>
<div class="app-hero__top">
<img class="app-hero__icon" src="{asset('img/icons/' + app['slug'] + '.webp')}"
 alt="{e(app['name'])} app icon" width="116" height="116" fetchpriority="high">
<div class="app-hero__head">
<h1>{e(app['name'])}</h1>
<p class="app-hero__tag">{e(app['tagline'])}</p>
<div class="btn-row">{store_button(app)}</div>
</div>
</div>
<div class="facts">{facts_html}</div>
</div>
</section>

<section class="section section--tight">
<div class="wrap">
<div class="prose">
<p class="lede">{e(app['blurb'])}</p>
</div>
</div>
</section>
{shots_html}
<section class="section section--sub">
<div class="wrap">
<div class="section-head">
<p class="eyebrow">More from us</p>
<h2>Other apps</h2>
</div>
<div class="app-grid">
{more}
</div>
<p style="margin-top:24px"><a class="arrow-link" href="{url('apps')}">
All {len(apps)} apps {icon('arrow')}</a></p>
</div>
</section>
""" + footer(apps)


def page_about(apps, totals):
    cats = sorted({a["category"] for a in apps})
    return head(
        f"About — {COMPANY}",
        f"{COMPANY_LEGAL} is a UK company that designs and publishes apps for Apple "
        f"platforms. {totals['count']} are live on the App Store.",
        "about",
    ) + masthead("about") + f"""
<section class="section section--tight">
<div class="wrap">
<div class="section-head">
<p class="eyebrow">About</p>
<h1>Who we are</h1>
</div>
<div class="prose">
<p class="lede">{e(COMPANY_LEGAL)} is a UK-registered company that designs, builds and
publishes apps for Apple platforms. {totals['count']} of them are live on the App Store
today, carrying {thousands(totals['ratings'])} ratings at a {totals['avg']:.2f} average.</p>

<h2>What we make</h2>
<p>Small, single-purpose apps, mostly. A tone generator that also gets water out of a
speaker. A browser that keeps video playing while you do something else. A CV builder that
exports a clean PDF. A reader for manga. A gallery of watch faces. Nothing here is trying
to be a platform.</p>
<p>Across the catalogue that spans {len(cats)} App Store categories &mdash;
{e(', '.join(cats[:-1]))} and {e(cats[-1])} &mdash; on iPhone, iPad and Apple Watch.</p>

<h2>How we work</h2>
<p>Everything is native Swift. The apps are localised into dozens of languages, ship
through the same automated build-and-release pipeline, and get updated rather than
abandoned &mdash; several in this list have been maintained for years.</p>
<p>We also take on client work: the same team and the same pipeline, pointed at someone
else's product. If you have an idea that needs an iOS team,
<a href="mailto:{EMAIL}">write to us</a>.</p>

<h2>Support</h2>
<p>Every app is supported from the same place. For a question about a specific app, or
a subscription, email <a href="mailto:{EMAIL}">{EMAIL}</a> and say which app it is.
Subscriptions can also be managed
<a href="{SUBSCRIPTIONS}" rel="noopener">through the portal</a>.</p>
</div>

<div class="legal-meta">
<span>{e(COMPANY_LEGAL)}</span>
<span>{e(', '.join(ADDRESS))}</span>
</div>
</div>
</section>

<section class="section section--tight">
<div class="wrap">
<div class="callout">
<div class="callout__text">
<h2>See what we've shipped</h2>
<p>The full catalogue, with live App Store ratings.</p>
</div>
<div class="btn-row">
<a class="btn btn--primary" href="{url('apps')}">Browse {totals['count']} apps {icon('arrow')}</a>
</div>
</div>
</div>
</section>
""" + footer(apps)


def page_contact(apps):
    address = "<br>".join(e(line) for line in ADDRESS)
    return head(
        f"Contact — {COMPANY}",
        f"Get in touch with {COMPANY}: {EMAIL}, or manage an app subscription.",
        "contact",
    ) + masthead("contact") + f"""
<section class="section section--tight">
<div class="wrap">
<div class="section-head">
<p class="eyebrow">Contact</p>
<h1>Get in touch</h1>
<p class="lede">One inbox for everything &mdash; app support, subscriptions, and new
projects. Tell us which app you're writing about and we'll get to it faster.</p>
</div>

<div class="cols">
<dl class="contact-list">
<div class="contact-item">
<dt>Email</dt>
<dd><a href="mailto:{EMAIL}">{EMAIL}</a></dd>
</div>
<div class="contact-item">
<dt>Subscriptions</dt>
<dd><a href="{SUBSCRIPTIONS}" rel="noopener">Manage or cancel a subscription</a></dd>
</div>
<div class="contact-item">
<dt>TikTok</dt>
<dd><a href="{TIKTOK}" rel="noopener">@musica.ai.app</a></dd>
</div>
</dl>

<dl class="contact-list">
<div class="contact-item">
<dt>Registered office</dt>
<dd><address>{e(COMPANY_LEGAL)}<br>{address}</address></dd>
</div>
<div class="contact-item">
<dt>Legal</dt>
<dd><a href="{url('privacy-policy-looksmax')}">Privacy Policy</a> &middot;
<a href="{url('term-of-use')}">Terms of Use</a></dd>
</div>
</dl>
</div>
</div>
</section>
""" + footer(apps)


def page_legal(slug, title, body, apps, *, extra="", canonical_path=None):
    return head(
        f"{title} — {COMPANY}",
        f"{title} for {COMPANY_LEGAL}. "
        f"{COMPANY_LEGAL}, {', '.join(ADDRESS)}.",
        slug,
        canonical_path=canonical_path,
    ) + masthead("") + f"""
<section class="section section--tight">
<div class="wrap">
<div class="section-head">
<p class="eyebrow">Legal</p>
<h1>{e(title)}</h1>
</div>
<div class="prose">
{body}
{extra}
</div>
<div class="legal-meta">
<span>{e(COMPANY_LEGAL)}</span>
<span>{e(', '.join(ADDRESS))}</span>
<span><a href="mailto:{EMAIL}">{EMAIL}</a></span>
</div>
</div>
</section>
""" + footer(apps)


def page_retired(slug, title, message, apps):
    return head(
        f"{title} — {COMPANY}",
        f"{title}: {message} See the {len(apps)} apps {COMPANY} publishes today.",
        slug, noindex=True,
    ) + masthead("apps") + f"""
<section class="section">
<div class="wrap center-page">
<p class="eyebrow">No longer listed</p>
<h1>{e(title)}</h1>
<p class="lede">{e(message)} You can see everything we publish today on the apps page.</p>
<div class="btn-row">
<a class="btn btn--primary" href="{url('apps')}">Browse our apps {icon('arrow')}</a>
<a class="btn btn--ghost" href="mailto:{EMAIL}">Email us</a>
</div>
</div>
</section>
""" + footer(apps)


def page_404(apps):
    return head("Page not found — " + COMPANY,
                f"That page doesn't exist. Browse the {len(apps)} apps {COMPANY} "
                f"publishes on the App Store, or get in touch.", "404",
                noindex=True) + masthead("") + f"""
<section class="section">
<div class="wrap center-page">
<p class="eyebrow">Error 404</p>
<h1>This page doesn't exist</h1>
<p class="lede">The link may be out of date. Everything we publish is on the apps page.</p>
<div class="btn-row">
<a class="btn btn--primary" href="{url('apps')}">Browse our apps {icon('arrow')}</a>
<a class="btn btn--ghost" href="{url()}">Home</a>
</div>
</div>
</section>
""" + footer(apps)


# --- build -------------------------------------------------------------------

def main():
    global BASE
    if "--base" in sys.argv:
        BASE = "/" + sys.argv[sys.argv.index("--base") + 1].strip("/")

    apps = json.loads((SRC / "apps.json").read_text())
    ratings = sum(a["ratingCount"] for a in apps)
    totals = {
        "count": len(apps),
        "ratings": ratings,
        "avg": sum((a["rating"] or 0) * a["ratingCount"] for a in apps) / ratings,
        "categories": len({a["category"] for a in apps}),
    }

    write("", page_home(apps, totals))
    write("apps", page_apps(apps, totals))
    for app in apps:
        write(f"apps/{app['slug']}", page_app(app, apps))
    write("about", page_about(apps, totals))
    write("contact", page_contact(apps))

    legal_titles = {
        "privacy-policy-looksmax": "Privacy Policy",
        "terms-of-use-wristtube": "Terms of Use (WristTube)",
        "term-of-use": "Terms of Use",
    }
    contact_block = (
        f'<p><strong>Email:</strong> <a href="mailto:{EMAIL}">{EMAIL}</a><br>'
        f'<strong>Post:</strong> {e(COMPANY_LEGAL)}, {e(", ".join(ADDRESS))}</p>'
    )
    for slug, title in legal_titles.items():
        body = (SRC / "legal" / f"{slug}.html").read_text()
        # the source page ended in a contact form; give the reader real details instead
        extra = contact_block if slug == "privacy-policy-looksmax" else ""
        write(slug, page_legal(slug, title, body, apps, extra=extra))

    # the two paths WordPress served as 301s, reproduced as real pages
    for alias, target in LEGAL_ALIASES.items():
        body = (SRC / "legal" / f"{target}.html").read_text()
        extra = contact_block if target == "privacy-policy-looksmax" else ""
        write(alias, page_legal(alias, legal_titles[target], body, apps,
                                extra=extra, canonical_path=target))

    for slug, (title, message) in RETIRED.items():
        write(slug, page_retired(slug, title, message, apps))

    write("404.html", page_404(apps))

    # sitemap: canonical pages only, never the noindexed ones
    urls = [""] + ["apps", "about", "contact"] + [f"apps/{a['slug']}" for a in apps] \
        + list(legal_titles)
    today = date.today().isoformat()
    entries = "\n".join(
        f"  <url><loc>{SITE}/{(p + '/') if p else ''}</loc>"
        f"<lastmod>{today}</lastmod>"
        f"<priority>{'1.0' if not p else '0.8' if p == 'apps' else '0.6'}</priority></url>"
        for p in urls
    )
    write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n'
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
          f"{entries}\n</urlset>\n")

    write("robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\n")

    (ROOT / "CNAME").write_text("euappsolutions.com\n")
    (ROOT / ".nojekyll").write_text("")

    print(f"built {len(pages_built)} files")
    for p in pages_built:
        print(f"  {p}")


if __name__ == "__main__":
    main()
