#!/usr/bin/env python3
"""Pull the legal pages off the live WordPress site and keep their text verbatim.

These URLs are cited from App Store listings, so the wording must not drift. The source
is Elementor: the page body is a flat run of `.elementor-widget-container` divs, each
holding either a heading or a text-editor block whose paragraphs are often unwrapped.

This walks those widgets in document order and emits a clean HTML fragment per page to
src/legal/<slug>.html for build.py to drop into the new layout. Text is never rewritten --
only re-tagged.

Run once; the fragments are committed. Re-run only if the source text is amended.
"""
import html
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "legal"

PAGES = {
    "privacy-policy-looksmax": "Privacy Policy",
    "terms-of-use-wristtube": "Terms of Use (WristTube)",
    "term-of-use": "Terms of Use",
}

# the host's WAF 406s on a bare urllib request, so send a full browser header set
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}

WIDGET_OPEN = re.compile(r'<div[^>]*\bclass="[^"]*\belementor-widget-container\b[^"]*"[^>]*>', re.I)
DIV_TAG = re.compile(r"(?i)<(/?)div\b[^>]*>")
HEADING = re.compile(r"(?is)<h([1-6])[^>]*>(.*?)</h\1>")
BLOCK_START = re.compile(r"(?i)^\s*<(p|ul|ol|h[1-6]|table)\b")
# the privacy page ends with an Elementor contact-form widget; its field labels are not policy
# text. A block is dropped when every word in it is a form label -- build.py appends the real
# contact details in their place.
FORM_LABELS = {"name", "email", "e-mail", "website", "phone", "message",
               "subject", "send", "submit", "*"}


def is_form_noise(text):
    words = re.findall(r"[\w'-]+|\*", text.lower())
    return bool(words) and all(w in FORM_LABELS for w in words)


def iter_widgets(region):
    """Yield the inner HTML of each widget container, matching nested <div>s properly."""
    for opening in WIDGET_OPEN.finditer(region):
        start = opening.end()
        depth = 1
        for tag in DIV_TAG.finditer(region, start):
            depth += -1 if tag.group(1) else 1
            if depth == 0:
                yield region[start:tag.start()]
                break


def fetch(slug):
    req = urllib.request.Request(f"https://euappsolutions.com/{slug}/", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def inline_only(frag):
    """Keep strong/em/a/br, drop every other tag and all attributes except href."""
    def tag(m):
        closing, name, attrs = m.group(1), m.group(2).lower(), m.group(3)
        if name in ("strong", "b"):
            return "</strong>" if closing else "<strong>"
        if name in ("em", "i"):
            return "</em>" if closing else "<em>"
        if name == "br":
            return "<br>"
        if name == "a":
            if closing:
                return "</a>"
            href = re.search(r'href=(["\'])(.*?)\1', attrs, re.I)
            if not href:
                return ""
            url = html.escape(href.group(2), quote=True)
            rel = ' rel="noopener"' if url.startswith("http") else ""
            return f'<a href="{url}"{rel}>'
        return " "

    frag = re.sub(r"(?is)<!--.*?-->", "", frag)
    frag = re.sub(r"(?is)<(/?)([a-z0-9]+)((?:\s[^>]*)?)/?>", tag, frag)
    return re.sub(r"\s+", " ", frag).strip()


def widget_to_html(raw):
    """Turn one Elementor widget's inner HTML into well-formed block markup.

    A text-editor widget frequently mixes headings and paragraphs in one container, so
    walk the content in document order rather than treating a widget as a single kind.
    """
    out = []
    for part in re.split(r"(?is)(<h[1-6][^>]*>.*?</h[1-6]>)", raw):
        if not part or not part.strip():
            continue
        h = HEADING.fullmatch(part.strip())
        if h:
            text = re.sub(r"(?is)</?a[^>]*>", "", inline_only(h.group(2))).strip()
            if text:
                # source uses h2 for the page title and h4/h5 for sections; template owns the h1
                out.append(f"<h{2 if int(h.group(1)) <= 4 else 3}>{text}</h{2 if int(h.group(1)) <= 4 else 3}>")
            continue
        out.extend(blocks_from(part))
    return out


def blocks_from(raw):
    """Paragraphs and lists out of a run of non-heading widget content."""
    out = []
    # split the widget on real block boundaries first so lists survive intact
    for chunk in re.split(r"(?is)(<ul.*?</ul>|<ol.*?</ol>|<table.*?</table>)", raw):
        if not chunk or not chunk.strip():
            continue
        if re.match(r"(?is)^\s*<(ul|ol)\b", chunk):
            items = [inline_only(m) for m in re.findall(r"(?is)<li[^>]*>(.*?)</li>", chunk)]
            items = [i for i in items if i]
            if items:
                kind = "ol" if chunk.lstrip().lower().startswith("<ol") else "ul"
                out.append(f"<{kind}>" + "".join(f"<li>{i}</li>" for i in items) + f"</{kind}>")
            continue
        if re.match(r"(?is)^\s*<table\b", chunk):
            continue  # no tables in these documents; skip rather than mangle
        # a text-editor block: <p>-wrapped paragraphs, or bare text separated by newlines
        if BLOCK_START.match(chunk):
            for p in re.findall(r"(?is)<p[^>]*>(.*?)</p>", chunk):
                t = inline_only(p)
                if t:
                    out.append(f"<p>{t}</p>")
            continue
        for para in re.split(r"(?i)\n\s*\n|<br\s*/?>\s*<br\s*/?>", chunk):
            t = inline_only(para)
            if t and t not in ("<br>",):
                out.append(f"<p>{t}</p>")
    return out


def extract(doc, page_title):
    start = doc.find('id="content"')
    end = doc.find("<footer", start if start > 0 else 0)
    region = doc[start if start > 0 else 0: end if end > 0 else len(doc)]
    region = re.sub(r"(?is)<(script|style|noscript|svg|nav)[^>]*>.*?</\1>", " ", region)

    blocks, seen_title = [], False
    for raw in iter_widgets(region):
        for block in widget_to_html(raw):
            plain = html.unescape(re.sub(r"(?is)<[^>]+>", "", block)).strip()
            if not plain or plain.lower() in ("skip to content", "menu"):
                continue
            if block.startswith("<p>") and is_form_noise(plain):
                continue
            # the source repeats its own title as the first heading; the template supplies it
            if not seen_title and block.startswith("<h2>") and plain.lower().rstrip("!") in (
                page_title.lower(), "privacy policy", "terms of use", "terms and conditions",
            ):
                seen_title = True
                continue
            if blocks and blocks[-1] == block:
                continue  # Elementor duplicates a few widgets for its mobile layout
            blocks.append(block)
    return blocks


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    failed = False
    for slug, title in PAGES.items():
        try:
            doc = fetch(slug)
        except Exception as exc:
            print(f"! {slug}: {exc}", file=sys.stderr)
            failed = True
            continue
        blocks = extract(doc, title)
        words = len(re.sub(r"(?is)<[^>]+>", " ", "\n".join(blocks)).split())
        if words < 500:
            print(f"! {slug}: only {words} words extracted, refusing to write", file=sys.stderr)
            failed = True
            continue
        (OUT / f"{slug}.html").write_text("\n".join(blocks) + "\n")
        heads = sum(1 for b in blocks if b.startswith("<h"))
        print(f"{slug}.html  {words:,} words  {len(blocks)} blocks  {heads} headings")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
