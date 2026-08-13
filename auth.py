"""
auth.py
-------
Week 5, Day 1: Auth foundation.

Handles user accounts for the dashboard: creating accounts, verifying
logins, and storing everything in a local JSON file (users.json).

WHY A LOCAL JSON FILE, NOT A REAL DATABASE?
This is an MVP — you don't need Postgres/Firebase yet just to prove the
concept of "accounts + saved dashboards + tiers" works. A JSON file is
plenty for a handful of test users. If this ever needs to support real
concurrent users, swap this file for a real database — but the function
signatures below (create_user, authenticate, etc.) would stay the same,
so nothing else in app.py would need to change.

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
import bcrypt

USERS_FILE = "users.json"


def load_users():
    """Returns the users dict: {username: {"password_hash": ..., "tier": ...}}"""
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, "r") as f:
        return json.load(f)


def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)


def hash_password(password):
    """Turns a plain-text password into a bcrypt hash (bytes -> string for JSON storage)."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password, password_hash):
    """Checks a plain-text password against a stored hash. Returns True/False."""
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


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

    users = load_users()
    if username in users:
        return False, "That username is already taken."

    users[username] = {"password_hash": hash_password(password), "tier": tier}
    save_users(users)
    return True, "Account created successfully."


def authenticate(username, password):
    """
    Checks login credentials. Returns (success: bool, message: str).
    Deliberately gives the SAME generic error for "user doesn't exist"
    and "wrong password" — telling an attacker which one is wrong would
    leak which usernames exist on the system.
    """
    users = load_users()
    username = username.strip()

    if username not in users:
        return False, "Incorrect username or password."

    if not verify_password(password, users[username]["password_hash"]):
        return False, "Incorrect username or password."

    return True, "Login successful."


def get_user_tier(username):
    """Returns the user's tier ('free' or 'premium'), or 'free' if not found."""
    users = load_users()
    return users.get(username, {}).get("tier", "free")


def set_user_tier(username, tier):
    """Updates a user's tier — used by the Day 4 'upgrade to premium' button."""
    users = load_users()
    if username in users:
        users[username]["tier"] = tier
        save_users(users)
        return True
    return False


# ---------------------------------------------------------------------------
# SAVED DASHBOARDS (Week 5, Day 3)
# ---------------------------------------------------------------------------
# Each user can save their current filter setup (crop, regions, date range)
# under a name, and reload it later without re-picking filters. Stored
# inside the same users.json file, nested under each user's own record —
# so one user never sees another user's saved views.

def save_dashboard(username, dashboard_name, crop, regions, start_date, end_date):
    """Saves a filter setup under a name for this user. Overwrites if the
    same name already exists (so users can update a saved view)."""
    users = load_users()
    if username not in users:
        return False, "User not found."

    if "saved_dashboards" not in users[username]:
        users[username]["saved_dashboards"] = {}

    users[username]["saved_dashboards"][dashboard_name] = {
        "crop": crop,
        "regions": regions,
        "start_date": str(start_date),
        "end_date": str(end_date),
    }
    save_users(users)
    return True, f"Saved '{dashboard_name}'."


def get_saved_dashboards(username):
    """Returns this user's saved dashboards as a dict: {name: {crop, regions, start_date, end_date}}"""
    users = load_users()
    return users.get(username, {}).get("saved_dashboards", {})


def delete_saved_dashboard(username, dashboard_name):
    users = load_users()
    if username in users and dashboard_name in users[username].get("saved_dashboards", {}):
        del users[username]["saved_dashboards"][dashboard_name]
        save_users(users)
        return True
    return False


# ---------------------------------------------------------------------------
# Standalone test — run this file directly to verify account creation and
# login work correctly before wiring any of this into app.py.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== auth.py standalone test ===\n")

    # Clean slate for repeatable testing
    if os.path.exists(USERS_FILE):
        os.remove(USERS_FILE)
        print("(removed old users.json so this test starts fresh)\n")

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
    users = load_users()
    stored_hash = users["dania"]["password_hash"]
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

    # Test 9: delete a saved dashboard
    deleted = delete_saved_dashboard("dania", "My Potato Watch")
    print(f"Deleted 'My Potato Watch': {deleted}")
    assert deleted
    assert "My Potato Watch" not in get_saved_dashboards("dania")

    print("\n✅ All tests passed. auth.py is working correctly.")
    print(f"(A real users.json file was created in this folder — delete it if you want a clean start before using the real app.)")
