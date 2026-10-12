"""Check which website links in the places table are dead.

For every distinct website URL:
  - send a HEAD request (12 s timeout), and try GET if the server says 405/501
  - 10 threads, one pass, no retries
Result is saved in places.website_status as 'ok', 'dead' or 'unchecked'.
The URLs themselves are never changed, only flagged.

403 and 429 usually mean the site blocks bots, not that it is dead,
so those go to 'unchecked' for a manual look.

Usage: python3 check_links.py            # only rows not checked yet (or 'unchecked')
       python3 check_links.py --refresh  # check everything again
"""
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent
DB = BASE / "data" / "wanderwise_rome.db"
TIMEOUT = 12
WORKERS = 10
UA = {"User-Agent": "Wanderwise-Capstone/1.0 (dead-link check, single pass)"}

BOT_BLOCKED = {403, 429}


def classify(status, error):
    """Turn a status code or error into (flag, detail)."""
    if error:
        return "dead", error
    if status is None:
        return "unchecked", "no response"
    if 200 <= status < 400:
        return "ok", f"HTTP {status}"
    if status in BOT_BLOCKED:
        return "unchecked", f"HTTP {status} (probably blocks bots)"
    return "dead", f"HTTP {status}"


def check(url):
    """One check per URL: HEAD first, GET if HEAD isn't allowed."""
    try:
        r = requests.head(url, timeout=TIMEOUT, allow_redirects=True, headers=UA)
        if r.status_code in (405, 501):
            r = requests.get(url, timeout=TIMEOUT, allow_redirects=True,
                             headers=UA, stream=True)
            r.close()
        return classify(r.status_code, None)
    except requests.exceptions.SSLError:
        # some sites have an expired certificate, so try plain http once
        if url.startswith("https://"):
            try:
                r = requests.head("http://" + url[len("https://"):], timeout=TIMEOUT,
                                  allow_redirects=True, headers=UA)
                return classify(r.status_code, None)
            except Exception:
                pass
        return "dead", "SSLError"
    except requests.exceptions.ConnectTimeout:
        return "dead", "connect timeout"
    except requests.exceptions.ReadTimeout:
        return "dead", "read timeout"
    except requests.exceptions.ConnectionError as e:
        msg = str(e)
        if ("NameResolutionError" in type(e).__name__ or "DNS" in msg
                or "Name or service not known" in msg):
            return "dead", "DNS failure"
        return "dead", "connection error"
    except requests.exceptions.TooManyRedirects:
        return "dead", "redirect loop"
    except requests.exceptions.InvalidURL:
        return "dead", "invalid URL"
    except requests.exceptions.MissingSchema:
        return "dead", "missing scheme"
    except Exception as e:
        return "dead", type(e).__name__


def main():
    refresh = "--refresh" in sys.argv
    conn = sqlite3.connect(DB)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(places)")]
    if "website_status" not in cols:
        conn.execute("ALTER TABLE places ADD COLUMN website_status TEXT")
        conn.commit()
        print("added website_status column")

    if refresh:
        urls = [r[0] for r in conn.execute(
            "SELECT DISTINCT website FROM places "
            "WHERE website IS NOT NULL AND TRIM(website) != ''")]
    else:
        urls = [r[0] for r in conn.execute(
            """SELECT DISTINCT website FROM places
               WHERE website IS NOT NULL AND TRIM(website) != ''
                 AND (website_status IS NULL OR website_status = 'unchecked')""")]
    urls = sorted({u.strip() for u in urls if u and u.strip()})
    print(f"{len(urls)} URLs to check")
    if not urls:
        conn.close()
        return

    results = {}
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for url, res in zip(urls, pool.map(check, urls), strict=True):
            results[url] = res
    dt = time.time() - t0

    for url, (flag, _detail) in results.items():
        conn.execute("UPDATE places SET website_status = ? WHERE website = ?", (flag, url))
    conn.commit()

    ok = sum(1 for f, _ in results.values() if f == "ok")
    dead = sum(1 for f, _ in results.values() if f == "dead")
    unchk = sum(1 for f, _ in results.values() if f == "unchecked")
    print(f"done in {dt:.0f}s: ok={ok} dead={dead} unchecked={unchk}")

    # keep the details so I can look at why a link failed
    conn.execute("DROP TABLE IF EXISTS _link_check_raw")
    conn.execute("CREATE TABLE _link_check_raw (website TEXT PRIMARY KEY, flag TEXT, detail TEXT)")
    conn.executemany("INSERT INTO _link_check_raw VALUES (?,?,?)",
                     [(u, f, d) for u, (f, d) in results.items()])
    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
