"""Migrate packet_logs from raw-only to structured schema.

Usage:
    uv run python scripts/migrate_packet_logs.py [--dry-run] DB_PATH

Performs:
1. Renames 'timestamp' to 'collected_at' if needed
2. Adds new columns if missing (fingerprint, parse_status, direction, etc.)
3. Removes junk rows (EOF, empty)
4. Removes exact duplicate rows (keeping lowest id)
5. Backfills fingerprints and structured fields from raw_line
6. Handles fingerprint collisions
7. Creates unique index on fingerprint and index on collected_at
"""

from __future__ import annotations

import argparse
import sqlite3
import sys

from meshcore_dashboard.serial.parser import _LOG_LINE_RE, _compute_fingerprint

_JUNK_WHERE = "raw_line LIKE '%EOF%' OR TRIM(raw_line) = ''"


def migrate(db_path: str, *, dry_run: bool = False) -> None:
    """Run the packet_logs migration."""
    if sqlite3.sqlite_version_info < (3, 25, 0):
        print(
            f"ERROR: SQLite >= 3.25.0 required for RENAME COLUMN; "
            f"found {sqlite3.sqlite_version}",
            file=sys.stderr,
        )
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    cur = conn.cursor()

    # Check current columns
    columns = {row[1] for row in cur.execute("PRAGMA table_info(packet_logs)")}
    print(f"Existing columns: {sorted(columns)}")

    if dry_run:
        total = cur.execute("SELECT COUNT(*) FROM packet_logs").fetchone()[0]
        junk = cur.execute(
            f"SELECT COUNT(*) FROM packet_logs WHERE {_JUNK_WHERE}"
        ).fetchone()[0]
        # Count duplicates excluding junk rows (matches apply-mode order)
        non_junk = total - junk
        unique_non_junk = cur.execute(
            "SELECT COUNT(*) FROM (SELECT MIN(id) FROM packet_logs"
            f" WHERE NOT ({_JUNK_WHERE})"
            " GROUP BY raw_line)"
        ).fetchone()[0]
        dupes = non_junk - unique_non_junk
        print(f"Rows: {total}, Junk: {junk}, Duplicates: {dupes}")
        print(f"Would delete: {junk + dupes} rows")
        print("Dry run -- no changes made.")
        conn.close()
        return

    print("WARNING: This operation modifies the database. Ensure you have a backup.")

    try:
        # Step 1: Rename timestamp -> collected_at if needed
        if "timestamp" in columns and "collected_at" not in columns:
            cur.execute(
                "ALTER TABLE packet_logs RENAME COLUMN timestamp TO collected_at"
            )
            print("Renamed timestamp -> collected_at")

        # Step 2: Add new columns if missing
        new_cols = {
            "fingerprint": "TEXT",
            "parse_status": "TEXT DEFAULT 'raw_only'",
            "direction": "TEXT",
            "packet_type": "INTEGER",
            "route": "TEXT",
            "payload_len": "INTEGER",
            "snr": "REAL",
            "rssi": "INTEGER",
            "device_time_text": "TEXT",
            "device_date_text": "TEXT",
        }
        # Re-read columns after potential rename
        columns = {row[1] for row in cur.execute("PRAGMA table_info(packet_logs)")}
        for col, typedef in new_cols.items():
            if col not in columns:
                cur.execute(f"ALTER TABLE packet_logs ADD COLUMN {col} {typedef}")
                print(f"Added column: {col}")

        # Step 3: Remove junk rows
        junk_deleted = cur.execute(
            f"DELETE FROM packet_logs WHERE {_JUNK_WHERE}"
        ).rowcount
        print(f"Deleted {junk_deleted} junk rows")

        # Step 4: Remove exact duplicates (keep lowest id per raw_line)
        dupe_deleted = cur.execute(
            "DELETE FROM packet_logs WHERE id NOT IN"
            " (SELECT MIN(id) FROM packet_logs GROUP BY raw_line)"
        ).rowcount
        print(f"Deleted {dupe_deleted} duplicate rows")

        # Step 5: Backfill fingerprints and structured fields
        updated = 0
        for row_id, raw_line in cur.execute(
            "SELECT id, raw_line FROM packet_logs WHERE fingerprint IS NULL"
        ):
            fp = _compute_fingerprint(raw_line)
            m = _LOG_LINE_RE.search(raw_line)
            if m:
                cur.execute(
                    """UPDATE packet_logs SET
                        fingerprint=?, parse_status='parsed',
                        device_time_text=?, device_date_text=?,
                        direction=?, packet_type=?, route=?,
                        payload_len=?, snr=?, rssi=?
                    WHERE id=?""",
                    (
                        fp,
                        m.group("time"),
                        m.group("date"),
                        m.group("dir"),
                        int(m.group("type")),
                        m.group("route"),
                        int(m.group("plen")),
                        float(m.group("snr")) if m.group("snr") else None,
                        int(m.group("rssi")) if m.group("rssi") else None,
                        row_id,
                    ),
                )
            else:
                cur.execute(
                    "UPDATE packet_logs SET"
                    " fingerprint=?, parse_status='raw_only'"
                    " WHERE id=?",
                    (fp, row_id),
                )
            updated += 1

        print(f"Backfilled {updated} rows")

        # Verify no NULL fingerprints remain
        null_fps = cur.execute(
            "SELECT COUNT(*) FROM packet_logs WHERE fingerprint IS NULL"
        ).fetchone()[0]
        if null_fps:
            raise RuntimeError(
                f"{null_fps} rows still have NULL fingerprint after backfill"
            )

        # Step 6: Handle fingerprint collisions
        collision_deleted = cur.execute(
            "DELETE FROM packet_logs WHERE id NOT IN"
            " (SELECT MIN(id) FROM packet_logs GROUP BY fingerprint)"
        ).rowcount
        if collision_deleted:
            print(f"Deleted {collision_deleted} fingerprint collisions")

        # Step 7: Create indexes
        cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS"
            " ix_packet_logs_fingerprint"
            " ON packet_logs(fingerprint)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS"
            " ix_packet_logs_collected_at"
            " ON packet_logs(collected_at)"
        )
        print("Created indexes")

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        remaining = cur.execute("SELECT COUNT(*) FROM packet_logs").fetchone()[0]
        print(f"Migration complete. {remaining} rows remaining.")
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate packet_logs schema")
    parser.add_argument("db_path", help="Path to SQLite database")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done",
    )
    args = parser.parse_args()
    migrate(args.db_path, dry_run=args.dry_run)
