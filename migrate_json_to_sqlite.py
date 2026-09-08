"""
migrate_json_to_sqlite.py
--------------------------
One-time script: copies every account (and its saved dashboards) from the
old users.json file into the new users.db SQLite database used by the
rewritten auth.py.

Run this ONCE, right after updating to the SQLite version of auth.py:

    python migrate_json_to_sqlite.py

Safe to re-run — any username that already exists in users.db is skipped
(so running it twice won't duplicate or overwrite anything). users.json
itself is never modified or deleted; delete it by hand afterwards once
you've confirmed users.db looks right.

This inserts the password_hash directly (it's already a bcrypt hash, not
a plain-text password) so every user's existing password keeps working —
nobody has to reset anything.
"""

import json
import os
import sys

from auth import get_connection, init_db

USERS_JSON = "users.json"


def main():
    if not os.path.exists(USERS_JSON):
        print(f"No {USERS_JSON} found in this folder — nothing to migrate.")
        sys.exit(0)

    with open(USERS_JSON, "r", encoding="utf-8") as f:
        users = json.load(f)

    if not users:
        print(f"{USERS_JSON} is empty — nothing to migrate.")
        sys.exit(0)

    init_db()

    migrated, skipped = [], []

    with get_connection() as conn:
        for username, record in users.items():
            existing = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
            if existing:
                skipped.append(username)
                continue

            conn.execute(
                "INSERT INTO users (username, password_hash, tier) VALUES (?, ?, ?)",
                (username, record["password_hash"], record.get("tier", "free")),
            )

            saved_dashboards = record.get("saved_dashboards", {})
            for name, view in saved_dashboards.items():
                conn.execute(
                    """
                    INSERT INTO saved_dashboards (username, name, crop, regions, start_date, end_date)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(username, name) DO NOTHING
                    """,
                    (username, name, view["crop"], json.dumps(view["regions"]), view["start_date"], view["end_date"]),
                )

            migrated.append(username)

    print(f"✅ Migrated {len(migrated)} user(s): {migrated}")
    if skipped:
        print(f"⏭️  Skipped {len(skipped)} user(s) already in users.db: {skipped}")
    print("\nusers.json was left untouched. Once you've confirmed users.db is correct "
          "(e.g. by logging in with an existing account), you can delete users.json.")


if __name__ == "__main__":
    main()
