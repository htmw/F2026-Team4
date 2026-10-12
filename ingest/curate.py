"""Small helper for filling in the top-50 sights by hand.

You don't need to know SQL. Examples:
  python3 curate.py --list                  # checklist of the 50 sights
  python3 curate.py --progress              # how many have hours / fee
  python3 curate.py --name "Colosseum" --hours "Mo-Su 08:30-19:15" --fee yes
  python3 curate.py --name "Trevi Fountain" --fee no
  python3 curate.py --name "Pantheon" --website "https://pantheonroma.org"

Hours use the OpenStreetMap format:
  "Mo-Fr 09:00-18:00"           weekdays 9am-6pm
  "Mo-Su 08:30-19:15"           every day
  "Tu-Su 09:00-20:00; Mo off"   closed on Mondays
Fee: yes (paid) or no (free).
"""
import argparse
import csv
import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parent
DB = BASE / "data" / "wanderwise_rome.db"
TOP50 = BASE / "data" / "top50_curation.csv"


def top50_names():
    with open(TOP50, newline="", encoding="utf-8") as f:
        return [r["name"] for r in csv.DictReader(f)]


def find_place(conn, frag):
    # an exact name match wins, so "Circus Maximus" doesn't also match
    # "Circus Maximus Mithraeum". Otherwise fall back to a partial match.
    q = ("SELECT osm_type, osm_id, name, opening_hours, fee, website FROM places "
         "WHERE LOWER(name) = LOWER(?)")
    rows = conn.execute(q, (frag,)).fetchall()
    if rows:
        return rows
    return conn.execute(
        "SELECT osm_type, osm_id, name, opening_hours, fee, website FROM places "
        "WHERE LOWER(name) LIKE '%' || LOWER(?) || '%'", (frag,)).fetchall()


def main():
    ap = argparse.ArgumentParser(description="Top-50 curation helper")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--progress", action="store_true")
    ap.add_argument("--name")
    ap.add_argument("--hours")
    ap.add_argument("--fee", choices=["yes", "no"])
    ap.add_argument("--website")
    a = ap.parse_args()
    conn = sqlite3.connect(DB)

    if a.list:
        for i, n in enumerate(top50_names(), 1):
            r = conn.execute(
                "SELECT opening_hours, fee FROM places WHERE name = ?", (n,)).fetchone()
            hrs, fee = r or (None, "unknown")
            h = "✓ hours" if hrs else "· no hours"
            fp = "✓ fee" if fee in ("yes", "no") else "· fee?"
            print(f"{i:2}. {h:10} {fp:8} {n}")
        return

    if a.progress:
        names = top50_names()
        q = f"SELECT COUNT(*) FROM places WHERE name IN ({','.join('?' * len(names))})"
        nh = conn.execute(
            q + " AND opening_hours IS NOT NULL AND opening_hours != ''",
            names).fetchone()[0]
        nf = conn.execute(q + " AND fee IN ('yes','no')", names).fetchone()[0]
        print(f"Opening hours: {nh}/50   Fees: {nf}/50")
        return

    if not a.name:
        ap.print_help()
        return

    matches = find_place(conn, a.name)
    if not matches:
        print(f"No place matching '{a.name}'. Try --list to see the exact names.")
        return
    if len(matches) > 1:
        print(f"More than one match for '{a.name}', be more specific:")
        for m in matches[:10]:
            print(f"  - {m[2]}")
        return
    t, i, name, *_ = matches[0]
    sets, vals = [], []
    if a.hours is not None:
        sets.append("opening_hours = ?")
        vals.append(a.hours)
    if a.fee is not None:
        sets.append("fee = ?")
        vals.append(a.fee)
    if a.website is not None:
        sets.append("website = ?")
        vals.append(a.website)
        sets.append("website_status = 'ok'")
    if not sets:
        print("Nothing to update, add --hours, --fee or --website.")
        return
    sets.append("curated = 1")
    vals += [t, i]
    conn.execute(f"UPDATE places SET {', '.join(sets)} WHERE osm_type=? AND osm_id=?", vals)
    conn.commit()
    r = conn.execute("SELECT opening_hours, fee, website FROM places WHERE osm_type=? AND osm_id=?",
                     (t, i)).fetchone()
    print(f"Saved '{name}': hours={r[0] or '-'} fee={r[1]} website={r[2] or '-'}")

    # keep the CSV checklist in sync
    with open(TOP50, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        if row["name"] == name:
            if a.hours is not None:
                row["opening_hours"] = a.hours
            if a.fee is not None:
                row["fee"] = a.fee
            if a.website is not None:
                row["website"] = a.website
    with open(TOP50, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
