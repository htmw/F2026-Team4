
#!/usr/bin/env python3
"""Build a walking-time matrix for candidate places in Rome.

Selects famous sights, museums, parks, and other attractions from an
existing SQLite database. Calculates straight-line distances and estimated
walking times, then optionally compares them with OSRM routing durations.

Only the travel_times table is rebuilt. The places table is never modified.
"""

import json
import sqlite3
import urllib.request
from pathlib import Path

import numpy as np


# --------------------------------------------------
# Configuration
# --------------------------------------------------

BASE = Path(__file__).resolve().parent
DB = BASE / "data" / "wanderwise_rome.db"

TARGET_SIZE = 300

WALK_KMH = 4.5
WALK_KMH_SLOW = 3.0
EARTH_KM = 6371.0088

OSRM_TABLE_URL = "https://router.project-osrm.org/table/v1/walking/{coords}"
OSRM_TIMEOUT_S = 25

ICONIC_KEYWORDS = [
    "trevi",
    "spanish steps",
    "piazza di spagna",
    "roman forum",
    "foro romano",
    "st. peter",
    "san pietro",
    "sistine",
    "piazza navona",
    "castel sant'angelo",
    "castel sant’angelo",
    "villa borghese",
    "campo de' fiori",
    "caracalla",
    "circus maximus",
    "circo massimo",
    "vittoriano",
    "altare della patria",
    "santa maria maggiore",
    "san giovanni in laterano",
    "gianicolo",
    "janiculum",
    "pincio",
    "bocca della verit",
    "torre argentina",
    "trastevere",
    "sant'ignazio",
    "gesu",
    "chiesa del ges",
    "pantheon",
    "colosseum",
    "colosseo",
]

COLS = "osm_type, osm_id, name, category, lat, lon, website"

FIELDS = [
    "osm_type",
    "osm_id",
    "name",
    "category",
    "lat",
    "lon",
    "website",
]


# --------------------------------------------------
# Distance calculation
# --------------------------------------------------

def haversine_km(lat1, lon1, lat2, lon2):
    """Return the great-circle distance matrix in kilometers."""

    lat1 = np.radians(lat1)[:, None]
    lon1 = np.radians(lon1)[:, None]

    lat2 = np.radians(lat2)[None, :]
    lon2 = np.radians(lon2)[None, :]

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        np.sin(dlat / 2) ** 2
        + np.cos(lat1)
        * np.cos(lat2)
        * np.sin(dlon / 2) ** 2
    )

    return 2 * EARTH_KM * np.arcsin(
        np.sqrt(np.clip(a, 0, 1))
    )


# --------------------------------------------------
# Candidate selection
# --------------------------------------------------

def select_candidates(conn):
    """Select famous sights, museums, parks, and attractions."""

    log = []
    seen = set()
    candidates = []

    def add(rows, reason):
        added = 0

        for row in rows:
            key = (row[0], row[1])

            if key not in seen:
                seen.add(key)
                candidates.append(dict(zip(FIELDS, row)))
                added += 1

        log.append(f"{reason}: {added} new")

    # 1. Famous sights
    conditions = " OR ".join(
        "LOWER(name) LIKE ?"
        for _ in ICONIC_KEYWORDS
    )

    parameters = [
        f"%{keyword.lower()}%"
        for keyword in ICONIC_KEYWORDS
    ]

    iconic = conn.execute(
        f"SELECT {COLS} FROM places WHERE {conditions}",
        parameters,
    ).fetchall()

    add(iconic, f"Famous sights ({len(iconic)} matched)")

    # 2. Museums
    museums = conn.execute(
        f"""
        SELECT {COLS}
        FROM places
        WHERE category = 'museum'
        ORDER BY name
        """
    ).fetchall()

    add(museums, "Museums")

    # 3. Parks
    parks = conn.execute(
        f"""
        SELECT {COLS}
        FROM places
        WHERE category = 'park'
        ORDER BY name
        """
    ).fetchall()

    add(parks, "Parks")

    # 4. Fill the remaining target with attractions.
    # Prefer attractions with a website, then sort by name.
    remaining = TARGET_SIZE - len(candidates)

    if remaining > 0:
        attractions = conn.execute(
            f"""
            SELECT {COLS}
            FROM places
            WHERE category = 'attraction'
            ORDER BY
                CASE
                    WHEN website IS NOT NULL AND website != ''
                    THEN 0
                    ELSE 1
                END,
                name
            """
        ).fetchall()

        # Filter previously selected places before applying the limit.
        attractions = [
            row
            for row in attractions
            if (row[0], row[1]) not in seen
        ][:remaining]

        with_website = sum(
            1 for row in attractions if row[6]
        )

        add(
            attractions,
            (
                f"Attractions to fill up "
                f"({with_website} with website, "
                f"{len(attractions) - with_website} without)"
            ),
        )

    log.append(
        f"TOTAL candidates: {len(candidates)} "
        f"(target {TARGET_SIZE})"
    )

    return candidates, log


# --------------------------------------------------
# Coordinate validation
# --------------------------------------------------

def valid_coordinate(value, minimum, maximum):
    """Check whether a coordinate is a valid finite number."""

    try:
        number = float(value)
        return (
            np.isfinite(number)
            and minimum <= number <= maximum
        )
    except (TypeError, ValueError):
        return False


def filter_valid_coordinates(candidates):
    """Remove places that do not have valid coordinates."""

    valid = []
    removed = 0

    for place in candidates:
        if (
            valid_coordinate(place.get("lat"), -90, 90)
            and valid_coordinate(place.get("lon"), -180, 180)
        ):
            place["lat"] = float(place["lat"])
            place["lon"] = float(place["lon"])
            valid.append(place)
        else:
            removed += 1

    print(
        f"[coordinates] kept {len(valid)} places; "
        f"removed {removed} with invalid coordinates"
    )

    return valid


# --------------------------------------------------
# OSRM routing validation
# --------------------------------------------------

def try_osrm_sample(candidates, n_places=7):
    """Request routing durations for a small reproducible sample.

    Returns {(i, j): minutes} or None if routing is unavailable.
    """

    if not candidates:
        return None

    rng = np.random.default_rng(42)

    indices = sorted(
        rng.choice(
            len(candidates),
            size=min(n_places, len(candidates)),
            replace=False,
        ).tolist()
    )

    coordinates = ";".join(
        f"{candidates[i]['lon']},{candidates[i]['lat']}"
        for i in indices
    )

    url = (
        OSRM_TABLE_URL.format(coords=coordinates)
        + "?annotations=duration"
    )

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Wanderwise-Capstone/1.0"},
    )

    try:
        with urllib.request.urlopen(
            request, timeout=OSRM_TIMEOUT_S
        ) as response:
            data = json.load(response)

    except Exception as error:
        print(
            f"[osrm] request failed "
            f"({type(error).__name__}: {error}); "
            "OSRM values will remain NULL"
        )
        return None

    if data.get("code") != "Ok" or "durations" not in data:
        print("[osrm] invalid response; skipping validation")
        return None

    durations = data["durations"]

    if (
        not isinstance(durations, list)
        or len(durations) != len(indices)
        or any(
            not isinstance(row, list)
            or len(row) != len(indices)
            for row in durations
        )
    ):
        print("[osrm] malformed duration matrix; skipping validation")
        return None

    output = {}

    for a, i in enumerate(indices):
        for b, j in enumerate(indices):
            duration = durations[a][b]

            if (
                duration is not None
                and isinstance(duration, (int, float))
                and np.isfinite(duration)
                and duration >= 0
            ):
                output[(i, j)] = float(duration) / 60.0

    print(f"[osrm] got {len(output)} pair durations")

    return output


# --------------------------------------------------
# Main matrix-building process
# --------------------------------------------------

def main():
    """Build and save the travel-time matrix."""

    if not DB.is_file():
        raise FileNotFoundError(
            f"Database not found: {DB}\n"
            "Check the database path before running this script."
        )

    conn = sqlite3.connect(DB)

    try:
        conn.execute("PRAGMA journal_mode=WAL")

        # Confirm that the expected source table exists.
        table = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'places'
            """
        ).fetchone()

        if table is None:
            raise RuntimeError(
                "The database does not contain a 'places' table."
            )

        candidates, log = select_candidates(conn)

        for line in log:
            print("[select]", line)

        candidates = filter_valid_coordinates(candidates)
        n = len(candidates)

        if n == 0:
            raise ValueError(
                "No places with valid coordinates were found."
            )

        print(f"[matrix] calculating distances for {n} places")

        lat = np.array(
            [place["lat"] for place in candidates],
            dtype=float,
        )

        lon = np.array(
            [place["lon"] for place in candidates],
            dtype=float,
        )

        # Calculate straight-line distances and estimated walking times.
        km = haversine_km(lat, lon, lat, lon)

        walk = km / WALK_KMH * 60.0
        walk_slow = km / WALK_KMH_SLOW * 60.0

        # Optionally compare a small sample with routing estimates.
        osrm = try_osrm_sample(candidates)

        # Rebuild only travel_times.
        conn.execute("DROP TABLE IF EXISTS travel_times")

        conn.execute(
            """
            CREATE TABLE travel_times (
                from_type TEXT NOT NULL,
                from_id INTEGER NOT NULL,
                to_type TEXT NOT NULL,
                to_id INTEGER NOT NULL,
                haversine_km REAL NOT NULL,
                walk_min REAL NOT NULL,
                walk_min_slow REAL NOT NULL,
                osrm_walk_min REAL,
                PRIMARY KEY (
                    from_type, from_id, to_type, to_id
                )
            )
            """
        )

        conn.execute(
            """
            CREATE INDEX idx_tt_from
            ON travel_times(from_type, from_id)
            """
        )

        conn.execute(
            """
            CREATE INDEX idx_tt_to
            ON travel_times(to_type, to_id)
            """
        )

        # Prepare every ordered pair, including each place to itself.
        rows = []
        osrm_hits = 0

        for i in range(n):
            for j in range(n):
                osrm_minutes = osrm.get((i, j)) if osrm else None

                if osrm_minutes is not None:
                    osrm_hits += 1

                rows.append(
                    (
                        candidates[i]["osm_type"],
                        candidates[i]["osm_id"],
                        candidates[j]["osm_type"],
                        candidates[j]["osm_id"],
                        round(float(km[i, j]), 4),
                        round(float(walk[i, j]), 2),
                        round(float(walk_slow[i, j]), 2),
                        osrm_minutes,
                    )
                )

        conn.executemany(
            "INSERT INTO travel_times VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )

        conn.commit()

        # Summary statistics, excluding self-to-self pairs.
        if n > 1:
            mask = ~np.eye(n, dtype=bool)
            distances = km[mask]
            walking_minutes = walk[mask]

            print(f"[matrix] {n} places, {n * n} pairs")
            print(
                f"[matrix] distance km: "
                f"median {np.median(distances):.2f}, "
                f"p90 {np.percentile(distances, 90):.2f}, "
                f"max {distances.max():.2f}"
            )
            print(
                f"[matrix] walk min: "
                f"median {np.median(walking_minutes):.1f}, "
                f"p90 {np.percentile(walking_minutes, 90):.1f}, "
                f"max {walking_minutes.max():.1f}"
            )
        else:
            print("[matrix] one place found; no between-place statistics")

        # Save routing validation information.
        note = {
            "osrm_ok": osrm is not None,
            "osrm_pairs": osrm_hits,
            "places": n,
        }

        if osrm:
            ratios = []
            speeds = []

            for (i, j), minutes in osrm.items():
                if i == j or minutes <= 0 or walk[i, j] <= 0:
                    continue

                ratios.append(minutes / walk[i, j])
                speeds.append(km[i, j] / (minutes / 60.0))

            if speeds:
                median_speed = float(np.median(speeds))

                note["ratio_mean"] = round(
                    float(np.mean(ratios)), 3
                ) if ratios else None

                note["ratio_median"] = round(
                    float(np.median(ratios)), 3
                ) if ratios else None

                note["implied_speed_kmh_median"] = round(
                    median_speed, 2
                )

                print(
                    f"[validate] median OSRM speed: "
                    f"{median_speed:.1f} km/h"
                )

                if median_speed > 8.0:
                    note["rejected"] = (
                        "OSRM sample produced implausibly high "
                        "walking speeds. OSRM values were cleared."
                    )

                    conn.execute(
                        "UPDATE travel_times SET osrm_walk_min = NULL"
                    )
                    conn.commit()

                    note["osrm_pairs_kept"] = 0

                    print(
                        "[validate] rejected OSRM values; "
                        "osrm_walk_min remains NULL"
                    )
                else:
                    note["osrm_pairs_kept"] = osrm_hits
            else:
                note["validation_note"] = (
                    "No usable non-diagonal OSRM durations "
                    "were available for speed validation."
                )
                note["osrm_pairs_kept"] = osrm_hits
        else:
            print(
                "[validate] routing unavailable; "
                "OSRM values remain NULL"
            )

        output_path = BASE / "data" / "osrm_validation.json"

        output_path.write_text(
            json.dumps(note, indent=2),
            encoding="utf-8",
        )

        print(f"[done] travel_times written to {DB}")
        print(f"[done] validation report written to {output_path}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
