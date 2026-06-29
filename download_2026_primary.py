#!/usr/bin/env python3
"""Download 2026 Mississippi March primary result PDFs from the Secretary of
State site into a local 2026/ folder.

The SoS results page lists, per party, an overall "recap" report plus one PDF per
county. This script scrapes both the Democratic and Republican party pages,
collects every linked PDF, and mirrors the source layout locally:

    2026/Recap report Democratic Primary 2026.pdf
    2026/republican primary 2026.pdf
    2026/Democratic Primary/Adams County.pdf
    2026/Republican Primary/Adams County.pdf
    ...

Re-running is safe: files already present are skipped unless --force is given.
Stdlib only; run with plain `python3 download_2026_primary.py`.
"""

import argparse
import re
import ssl
import sys
import urllib.parse
import urllib.request
from pathlib import Path

PAGE_URL = ("https://sos.ms.gov/elections/electionresults_aspx/"
            "elections_results_2026_march_primary.aspx")
PARTIES = ["democrat", "republican"]
BASE = "https://www.sos.ms.gov"
# The SoS server returns 403 for browser-like (Mozilla) User-Agents but serves
# curl-style clients fine, so identify as curl.
USER_AGENT = "curl/8.7.1"

HREF_RE = re.compile(r'href="([^"]+\.pdf)"', re.IGNORECASE)

# Populated in main(); some Python installs lack a usable system cert store.
SSL_CTX = None


def make_ssl_context(insecure):
    if insecure:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60, context=SSL_CTX) as resp:
        return resp.read()


def encode_url(url):
    """Percent-encode the path of a URL (spaces etc.) while leaving the
    structure intact, so links with spaces resolve correctly."""
    parts = urllib.parse.urlsplit(url)
    # safe="/%" so already-encoded links (e.g. "Recap%20report") aren't
    # double-encoded, while literal spaces in county links still get escaped.
    path = urllib.parse.quote(parts.path, safe="/%")
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def collect_pdf_urls():
    """Scrape both party pages; return a sorted set of absolute PDF URLs."""
    urls = set()
    for party in PARTIES:
        page = f"{PAGE_URL}?party={party}"
        try:
            html = fetch(page).decode("utf-8", "replace")
        except Exception as e:
            print(f"! failed to fetch {page}: {e}", file=sys.stderr)
            continue
        found = HREF_RE.findall(html)
        print(f"{party}: found {len(found)} pdf links")
        for href in found:
            urls.add(urllib.parse.urljoin(BASE, href))
    return sorted(urls)


def local_path(url, out_dir):
    """Map a source PDF URL to its local path under out_dir.

    County PDFs live under '.../2026MarchPrimary/<Party> Primary/<file>.pdf' and
    keep that party subfolder; recap reports keep just their basename."""
    path = urllib.parse.unquote(urllib.parse.urlsplit(url).path)
    marker = "/2026MarchPrimary/"
    if marker in path:
        rel = path.split(marker, 1)[1]  # e.g. "Democratic Primary/Adams County.pdf"
        return out_dir / rel
    return out_dir / Path(path).name


def download(url, dest, force=False):
    if dest.exists() and not force:
        return "skip"
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = fetch(encode_url(url))
    if not data.startswith(b"%PDF"):
        return "bad"  # not a PDF (error page, redirect, etc.)
    dest.write_bytes(data)
    return "ok"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-o", "--out", default="2026",
                    help="output directory (default: 2026)")
    ap.add_argument("--force", action="store_true",
                    help="re-download files that already exist")
    ap.add_argument("--insecure", action="store_true",
                    help="skip TLS certificate verification (last resort)")
    args = ap.parse_args()

    global SSL_CTX
    SSL_CTX = make_ssl_context(args.insecure)

    out_dir = Path(args.out)
    urls = collect_pdf_urls()
    print(f"\n{len(urls)} unique PDF(s) to fetch into {out_dir}/\n")

    counts = {"ok": 0, "skip": 0, "bad": 0, "err": 0}
    for url in urls:
        dest = local_path(url, out_dir)
        try:
            status = download(url, dest, force=args.force)
        except Exception as e:
            status = "err"
            print(f"  ! {dest}: {e}", file=sys.stderr)
        counts[status] += 1
        if status in ("ok", "bad"):
            print(f"  {status:4} {dest}")

    print(f"\nDone: {counts['ok']} downloaded, {counts['skip']} skipped, "
          f"{counts['bad']} non-PDF, {counts['err']} errored.")


if __name__ == "__main__":
    main()
