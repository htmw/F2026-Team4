#!/usr/bin/env python3
"""Build the walking-time matrix for the Rome candidate places.

How the ~300 candidates are picked:
  0. Famous sights, matched by name (Trevi, Roman Forum, St. Peter's, ...).
     Many of them have no website in Wikidata, so the website ranking
     below would skip them.
  1. All museums (the optimizer needs their hours and fees).
  2. All parks.
  3. Fill the rest with attractions, those with a website first
     (website = rough proxy for "well known"), then by name.

Distances are straight-line (Haversine), turned into walking minutes at:
  walk_min       4.5 km/h  normal adult pace
  walk_min_slow  3.0 km/h  limited-mobility persona (Michael)

I also try the public OSRM server on a small sample to check these numbers.
If OSRM is unreachable or gives silly speeds, osrm_walk_min stays NULL.

Only the travel_times table is rebuilt. places is never touched.
"""

import json
import sqlite3
import urllib.request
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
DB = BASE / "data" / "wanderwise_rome.db"

TARGET_SIZE = 300
WALK_KMH = 4.5
WALK_KMH_SLOW = 3.0
EARTH_KM = 6371.0088

OSRM_TABLE_URL = "https://router.project-osrm.org/table/v1/walking/{coords}"
OSRM_TIMEOUT_S = 25

# Matched with LIKE %keyword% on the lowercase name.
ICONIC_KEYWORDS = [
    "trevi", "spanish steps", "piazza di spagna", "roman forum", "foro romano",
    "st. peter", "san pietro", "sistine", "piazza navona", "castel sant'angelo",
    "castel sant’angelo", "villa borghese", "campo de' fiori", "caracalla",
    "circus maximus", "circo massimo", "vittoriano", "altare della patria",
    "santa maria maggiore", "san giovanni in laterano", "gianicolo", "janiculum",
    "pincio", "bocca della verit", "torre argentina", "trastevere",
    "sant'ignazio", "gesu", "chiesa del ges", "pantheon", "colosseum", "colosseo",
]

COLS = "osm_type, osm_id, name, category, lat, lon, website"
FIELDS = ["osm_type", "osm_id", "name", "category", "lat", "lon", "website"]


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance between every pair of points (arrays in degrees) -> km matrix."""
    lat1 = np.radians(lat1)[:, None]
    lon1 = np.radians(lon1)[:, None]
    lat2 = np.radians(lat2)[None, :]
    lon2 = np.radians(lon2)[None, :]
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def select_candidates(conn):
    """Apply the selection rule. Returns (list of place dicts, log lines)."""
    log = []
    seen = set()
    cands = []

    def add(rows, why):
        added = 0
        for r in rows:
            key = (r[0], r[1])
            if key not in seen:
                seen.add(key)
                cands.append(dict(zip(FIELDS, r, strict=True)))
                added += 1
        log.append(f"{why}: {added} new")

    conds = " OR ".join("LOWER(name) LIKE '%" + k.replace("'", "''") + "%'"
                        for k in ICONIC_KEYWORDS)
    iconic = conn.execute(f"SELECT {COLS} FROM places WHERE {conds}").fetchall()
    add(iconic, f"famous sights ({len(iconic)} matched)")

    museums = conn.execute(
        f"SELECT {COLS} FROM places WHERE category='museum' ORDER BY name").fetchall()
    add(museums, "museums")

    parks = conn.execute(
        f"SELECT {COLS} FROM places WHERE category='park' ORDER BY name").fetchall()
    add(parks, "parks")

    remaining = TARGET_SIZE - len(cands)
    if remaining > 0:
        not_in = " AND ".join(f"(osm_type != '{t}' OR osm_id != {i})" for t, i in seen)
        attractions = conn.execute(
            f"SELECT {COLS} FROM places WHERE category='attraction' "
            + (f"AND {not_in} " if seen else "")
            + "ORDER BY (website IS NOT NULL AND website != '') DESC, name ASC "
            f"LIMIT {remaining}"
        ).fetchall()
        with_site = sum(1 for r in attractions if r[6])
        add(attractions,
            f"attractions to fill up ({with_site} with website, "
            f"{len(attractions) - with_site} without)")

    log.append(f"TOTAL candidates: {len(cands)} (target {TARGET_SIZE})")
    return cands, log


def try_osrm_sample(cands, n_places=7):
    """One OSRM /table request for n_places random places. Returns {(i, j): minutes} or None."""
    rng = np.random.default_rng(42)
    idx = sorted(rng.choice(len(cands), size=min(n_places, len(cands)),
                            replace=False).tolist())
    coords = ";".join(f"{cands[i]['lon']},{cands[i]['lat']}" for i in idx)
    url = OSRM_TABLE_URL.format(coords=coords) + "?annotations=duration"
    req = urllib.request.Request(url, headers={"User-Agent": "Wanderwise-Capstone/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=OSRM_TIMEOUT_S) as resp:
            data = json.load(resp)
    except Exception as e:
        print(f"[osrm] could not reach server ({type(e).__name__}: {e}), "
              "leaving osrm_walk_min NULL")
        return None
    if data.get("code") != "Ok" or "durations" not in data:
        print(f"[osrm] bad response (code={data.get('code')}), leaving osrm_walk_min NULL")
        return None
    out = {}
    for a, i in enumerate(idx):
        for b, j in enumerate(idx):
            d = data["durations"][a][b]
            if d is not None:
                out[(i, j)] = d / 60.0
    print(f"[osrm] got {len(out)} pair durations")
    return out


def main():
    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA journal_mode=WAL")

    cands, log = select_candidates(conn)
    for line in log:
        print("[select]", line)
    n = len(cands)

    lat = np.array([c["lat"] for c in cands])
    lon = np.array([c["lon"] for c in cands])
    km = haversine_km(lat, lon, lat, lon)
    walk = km / WALK_KMH * 60.0
    walk_slow = km / WALK_KMH_SLOW * 60.0

    osrm = try_osrm_sample(cands)

    conn.execute("DROP TABLE IF EXISTS travel_times")
    conn.execute("""
        CREATE TABLE travel_times (
          from_type    TEXT NOT NULL,
          from_id      INTEGER NOT NULL,
          to_type      TEXT NOT NULL,
          to_id        INTEGER NOT NULL,
          haversine_km REAL NOT NULL,
          walk_min     REAL NOT NULL,   -- at 4.5 km/h
          walk_min_slow REAL NOT NULL,  -- at 3.0 km/h
          osrm_walk_min REAL,           -- NULL unless validated with OSRM
          PRIMARY KEY (from_type, from_id, to_type, to_id)
        )
    """)
    conn.execute("CREATE INDEX idx_tt_from ON travel_times(from_type, from_id)")
    conn.execute("CREATE INDEX idx_tt_to   ON travel_times(to_type, to_id)")

    rows = []
    osrm_hits = 0
    for i in range(n):
        for j in range(n):
            o = osrm.get((i, j)) if osrm else None
            if o is not None:
                osrm_hits += 1
            rows.append((cands[i]["osm_type"], cands[i]["osm_id"],
                         cands[j]["osm_type"], cands[j]["osm_id"],
                         round(float(km[i, j]), 4),
                         round(float(walk[i, j]), 2),
                         round(float(walk_slow[i, j]), 2), o))
    conn.executemany("INSERT INTO travel_times VALUES (?,?,?,?,?,?,?,?)", rows)
    conn.commit()

    # stats ignore the diagonal (a place to itself)
    mask = ~np.eye(n, dtype=bool)
    d = km[mask]
    w = walk[mask]
    print(f"[matrix] {n} places, {n*n} pairs")
    print(f"[matrix] distance km: median {np.median(d):.2f}, "
          f"p90 {np.percentile(d, 90):.2f}, max {d.max():.2f}")
    print(f"[matrix] walk min:    median {np.median(w):.1f}, "
          f"p90 {np.percentile(w, 90):.1f}, max {w.max():.1f}")

    note = {"osrm_ok": osrm is not None, "osrm_pairs": osrm_hits}
    if osrm:
        ratios, speeds = [], []
        for (i, j), mins in osrm.items():
            if i != j and walk[i, j] > 0 and mins > 0:
                ratios.append(mins / walk[i, j])
                speeds.append(km[i, j] / (mins / 60.0))
        med_speed = float(np.median(speeds))
        note["ratio_mean"] = round(float(np.mean(ratios)), 3)
        note["ratio_median"] = round(float(np.median(ratios)), 3)
        note["implied_speed_kmh_median"] = round(med_speed, 2)
        print(f"[validate] OSRM/Haversine time ratio: mean {note['ratio_mean']}, "
              f"median {note['ratio_median']} (n={len(ratios)})")
        print(f"[validate] median OSRM speed: {med_speed:.1f} km/h")
        if med_speed > 8.0:
            # Nobody walks faster than 8 km/h. The public demo server's foot
            # profile gives car-like speeds, so don't use its numbers.
            note["rejected"] = (
                f"public OSRM demo server gave unrealistic walking speeds "
                f"(median {med_speed:.1f} km/h); osrm_walk_min left NULL. "
                "Re-run against a self-hosted OSRM with a proper foot profile."
            )
            print("[validate] REJECTED: speeds too high, osrm_walk_min stays NULL")
            conn.execute("UPDATE travel_times SET osrm_walk_min = NULL")
            conn.commit()
            note["osrm_pairs_kept"] = 0
        else:
            note["osrm_pairs_kept"] = osrm_hits
    else:
        print("[validate] OSRM not reachable; run this again on a network that can reach it")

    (BASE / "data" / "osrm_validation.json").write_text(json.dumps(note, indent=2))
    conn.close()
    print("[done] travel_times written")


if __name__ == "__main__":
    main()
