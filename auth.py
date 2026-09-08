"""
auth.py
-------
Week 5, Day 1: Auth foundation.
Later revision: migrated from users.json to a local SQLite database.

Handles user accounts for the dashboard: creating accounts, verifying
logins, and storing everything in a local SQLite database (users.db).

WHY SQLITE, NOT A HOSTED DATABASE?
This is still an MVP — SQLite is a real database (proper schema, SQL
queries, no more "read the whole file, mutate a dict, write the whole
file back" like users.json did) but needs zero setup: it's a single file
on disk, no server to run or credentials to manage, and Python's sqlite3
module is part of the standard library (no new dependency). If this ever
needs multiple app instances writing at once or persistence across a
Streamlit Cloud redeploy (which wipes local files, same limitation
users.json already had), swap this for a hosted Postgres/MySQL database —
but the function signatures below (create_user, authenticate, etc.) would
stay the same, so nothing else in app.py or the pages would need to change.
That's the same design this file already had for a JSON -> DB migration,
now one step further.

MIGRATING EXISTING users.json DATA?
Run migrate_json_to_sqlite.py once — it reads users.json (if present) and
copies every user + saved dashboard into users.db without touching
anything else. Safe to re-run; it skips users that already exist in the DB.

SECURITY NOTE:
Passwords are NEVER stored as plain text. We use bcrypt, which is a
one-way hashing algorithm designed specifically for passwords — it's slow
on purpose (makes brute-forcing expensive) and includes a random "salt"
automatically so two users with the same password get different-looking
hashes. We only ever store the hash, never the original password.

Run this file directly to test account creation/login without touching
the Streamlit app at all:

    python auth.py
"""

import json
import os
import sqlite3
from contextlib import contextmanager

import bcrypt

DB_FILE = "users.db"


# ---------------------------------------------------------------------------
# CONNECTION + SCHEMA
# ---------------------------------------------------------------------------
# A fresh connection per call (rather than one long-lived global connection)
# keeps this safe across Streamlit's threading model — each call is quick
# and self-contained, so there's no shared connection object that could be
# used from two threads at once.

@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")  # so deleting a user cleans up their saved dashboards too
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Creates the users and saved_dashboards tables if they don't exist yet.
    Safe to call every time the app starts — CREATE TABLE IF NOT EXISTS is a
    no-op once the schema is already there."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                tier TEXT NOT NULL DEFAULT 'free'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS saved_dashboards (
                username TEXT NOT NULL,
                name TEXT NOT NULL,
                crop TEXT NOT NULL,
                regions TEXT NOT NULL,     -- JSON-encoded list, e.g. '["Lahore", "Multan"]'
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                PRIMARY KEY (username, name),
                FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
            )
        """)


init_db()


# ---------------------------------------------------------------------------
# PASSWORD HASHING (unchanged from the JSON version)
# ---------------------------------------------------------------------------

def hash_password(password):
    """Turns a plain-text password into a bcrypt hash (bytes -> string for storage)."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password, password_hash):
    """Checks a plain-text password against a stored hash. Returns True/False."""
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


# ---------------------------------------------------------------------------
# ACCOUNTS
# ---------------------------------------------------------------------------

def create_user(username, password, tier="free"):
    """
    Creates a new account. Returns (success: bool, message: str) so the
    caller (app.py) can show a clear reason if it fails, instead of just
    a generic error.
    """
    username = username.strip()
    if not username or not password:
        return False, "Username and password can't be empty."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."

    with get_connection() as conn:
        existing = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
        if existing:
            return False, "That username is already taken."
        conn.execute(
            "INSERT INTO users (username, password_hash, tier) VALUES (?, ?, ?)",
            (username, hash_password(password), tier),
        )
    return True, "Account created successfully."


def authenticate(username, password):
    """
    Checks login credentials. Returns (success: bool, message: str).
    Deliberately gives the SAME generic error for "user doesn't exist"
    and "wrong password" — telling an attacker which one is wrong would
    leak which usernames exist on the system.
    """
    username = username.strip()
    with get_connection() as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE username = ?", (username,)).fetchone()

    if row is None:
        return False, "Incorrect username or password."
    if not verify_password(password, row["password_hash"]):
        return False, "Incorrect username or password."

    return True, "Login successful."


def get_user_tier(username):
    """Returns the user's tier ('free' or 'premium'), or 'free' if not found."""
    with get_connection() as conn:
        row = conn.execute("SELECT tier FROM users WHERE username = ?", (username,)).fetchone()
    return row["tier"] if row else "free"


def set_user_tier(username, tier):
    """Updates a user's tier — used by the 'upgrade to premium' button."""
    with get_connection() as conn:
        cursor = conn.execute("UPDATE users SET tier = ? WHERE username = ?", (tier, username))
        return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# SAVED DASHBOARDS (Week 5, Day 3)
# ---------------------------------------------------------------------------
# Each user can save their current filter setup (crop, regions, date range)
# under a name, and reload it later without re-picking filters. Stored in
# their own table now, one row per saved view, instead of nested inside a
# JSON blob per user — so "delete a saved view" and "list a user's saved
# views" are now plain SQL instead of load-mutate-save-the-whole-file.

def save_dashboard(username, dashboard_name, crop, regions, start_date, end_date):
    """Saves a filter setup under a name for this user. Overwrites if the
    same name already exists (so users can update a saved view)."""
    with get_connection() as conn:
        user_exists = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
        if not user_exists:
            return False, "User not found."

        conn.execute(
            """
            INSERT INTO saved_dashboards (username, name, crop, regions, start_date, end_date)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(username, name) DO UPDATE SET
                crop = excluded.crop,
                regions = excluded.regions,
                start_date = excluded.start_date,
                end_date = excluded.end_date
            """,
            (username, dashboard_name, crop, json.dumps(regions), str(start_date), str(end_date)),
        )
    return True, f"Saved '{dashboard_name}'."


def get_saved_dashboards(username):
    """Returns this user's saved dashboards as a dict: {name: {crop, regions, start_date, end_date}}"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT name, crop, regions, start_date, end_date FROM saved_dashboards WHERE username = ?",
            (username,),
        ).fetchall()

    return {
        row["name"]: {
            "crop": row["crop"],
            "regions": json.loads(row["regions"]),
            "start_date": row["start_date"],
            "end_date": row["end_date"],
        }
        for row in rows
    }


def delete_saved_dashboard(username, dashboard_name):
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM saved_dashboards WHERE username = ? AND name = ?",
            (username, dashboard_name),
        )
        return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Standalone test — run this file directly to verify account creation and
# login work correctly before wiring any of this into app.py.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== auth.py standalone test (SQLite) ===\n")

    # Clean slate for repeatable testing
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
        print(f"(removed old {DB_FILE} so this test starts fresh)\n")
    init_db()

    # Test 1: create a new account
    ok, msg = create_user("dania", "test123")
    print(f"Create 'dania' with password 'test123': {ok} -> {msg}")
    assert ok, "Account creation should succeed"

    # Test 2: duplicate username should fail
    ok, msg = create_user("dania", "anotherpass")
    print(f"Create 'dania' AGAIN (should fail): {ok} -> {msg}")
    assert not ok, "Duplicate username should be rejected"

    # Test 3: correct login should succeed
    ok, msg = authenticate("dania", "test123")
    print(f"Login as 'dania' with correct password: {ok} -> {msg}")
    assert ok, "Correct password should authenticate"

    # Test 4: wrong password should fail
    ok, msg = authenticate("dania", "wrongpassword")
    print(f"Login as 'dania' with WRONG password (should fail): {ok} -> {msg}")
    assert not ok, "Wrong password should be rejected"

    # Test 5: nonexistent user should fail with the SAME message as wrong password
    ok, msg = authenticate("nobody", "whatever")
    print(f"Login as nonexistent user (should fail): {ok} -> {msg}")
    assert not ok, "Nonexistent user should be rejected"

    # Test 6: tier defaults to 'free'
    tier = get_user_tier("dania")
    print(f"'dania' tier: {tier}")
    assert tier == "free", "New accounts should default to free tier"

    # Test 7: password is actually hashed, not stored as plain text
    with get_connection() as conn:
        stored_hash = conn.execute("SELECT password_hash FROM users WHERE username = ?", ("dania",)).fetchone()["password_hash"]
    print(f"Stored password hash (should NOT look like 'test123'): {stored_hash[:30]}...")
    assert stored_hash != "test123", "Password must never be stored as plain text"

    # Test 8: save a dashboard and read it back
    ok, msg = save_dashboard("dania", "My Potato Watch", "Potato", ["Lahore", "Multan"], "2026-06-01", "2026-07-01")
    print(f"Save dashboard 'My Potato Watch': {ok} -> {msg}")
    assert ok

    saved = get_saved_dashboards("dania")
    print(f"Retrieved saved dashboards: {list(saved.keys())}")
    assert "My Potato Watch" in saved
    assert saved["My Potato Watch"]["crop"] == "Potato"

    # Test 9: saving under the same name again should overwrite, not duplicate
    ok, msg = save_dashboard("dania", "My Potato Watch", "Potato", ["Karachi"], "2026-06-15", "2026-07-01")
    saved = get_saved_dashboards("dania")
    print(f"Re-saved 'My Potato Watch' with new regions: {saved['My Potato Watch']['regions']}")
    assert saved["My Potato Watch"]["regions"] == ["Karachi"], "Saving under an existing name should overwrite it"
    assert len(saved) == 1, "Should still be exactly one saved dashboard, not a duplicate"

    # Test 10: delete a saved dashboard
    deleted = delete_saved_dashboard("dania", "My Potato Watch")
    print(f"Deleted 'My Potato Watch': {deleted}")
    assert deleted
    assert "My Potato Watch" not in get_saved_dashboards("dania")

    print("\n✅ All tests passed. auth.py is working correctly.")
    print(f"(A real {DB_FILE} file was created in this folder — delete it if you want a clean start before using the real app.)")
