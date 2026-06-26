#!/usr/bin/env python3
"""
scripts/diagnostics/smoke_chat_history_api.py
=================================
End-to-end tests for the chat history API endpoints.

Tests:
1. POST /chat → create new chat → verify session_id in response
2. GET /chat/sessions → verify session appears
3. GET /chat/sessions/{id}/messages → verify user + assistant messages
4. PATCH /chat/sessions/{id}/rename → rename session
5. GET /chat/sessions → verify new title
6. PATCH /chat/sessions/{id}/hide → hide session
7. GET /chat/sessions → hidden session NOT visible
8. GET /chat/sessions?include_hidden=true → hidden session IS visible

Requires:
- Backend running at http://127.0.0.1:8000
- PostgreSQL available with chat_sessions and chat_messages tables
"""

from __future__ import annotations

import json
import sys
import time

try:
    import requests
except ImportError:
    print("Installing requests...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests

BASE_URL = "http://127.0.0.1:8000"

# ANSI colors for output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"
BOLD = "\033[1m"

passed = 0
failed = 0


def ok(test_name: str, detail: str = ""):
    global passed
    passed += 1
    print(f"  {GREEN}✓{RESET} {test_name}" + (f" — {detail}" if detail else ""))


def fail(test_name: str, detail: str = ""):
    global failed
    failed += 1
    print(f"  {RED}✗{RESET} {test_name}" + (f" — {detail}" if detail else ""))


def section(title: str):
    print(f"\n{BOLD}{title}{RESET}")


def main():
    global passed, failed
    print(f"\n{'='*60}")
    print(f"{BOLD}Chat History API — End-to-End Tests{RESET}")
    print(f"{'='*60}")

    # ── 0. Health Check ──────────────────────────────────────
    section("0. Health Check")
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=5)
        assert r.status_code == 200
        ok("Backend reachable", f"status={r.json()['status']}")
    except Exception as e:
        fail("Backend reachable", str(e))
        print(f"\n{RED}Cannot reach backend. Is it running at {BASE_URL}?{RESET}")
        return 1

    # ── 1. POST /chat — Create new chat ──────────────────────
    section("1. POST /chat — Create new chat")
    session_id = None
    try:
        r = requests.post(f"{BASE_URL}/chat", json={
            "message": "Mụn trứng cá là gì? Nguyên nhân chính gây ra mụn trứng cá?",
            "user_id": None,
            "session_id": None,
            "conversation_history": [],
        }, timeout=60)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        data = r.json()
        assert "answer" in data, "Response missing 'answer'"
        assert len(data["answer"]) > 10, "Answer too short"
        assert "session_id" in data, "Response missing 'session_id'"
        session_id = data["session_id"]
        ok("POST /chat returned answer", f"session_id={session_id}")
        ok("Response includes session_id", f"{session_id}")
    except Exception as e:
        fail("POST /chat", str(e))
        return 1

    # Small delay to let DB commit
    time.sleep(0.5)

    # ── 2. GET /chat/sessions — Session appears ──────────────
    section("2. GET /chat/sessions — Session appears")
    try:
        r = requests.get(f"{BASE_URL}/chat/sessions", timeout=10)
        assert r.status_code == 200
        sessions = r.json()
        assert isinstance(sessions, list)

        session_ids = [s["id"] for s in sessions]
        if session_id in session_ids:
            ok("Session found in list", f"total sessions: {len(sessions)}")
        else:
            fail("Session found in list", f"session_id={session_id} not in {session_ids}")
    except Exception as e:
        fail("GET /chat/sessions", str(e))

    # ── 3. GET /chat/sessions/{id}/messages — Messages exist ─
    section("3. GET /chat/sessions/{id}/messages")
    try:
        r = requests.get(f"{BASE_URL}/chat/sessions/{session_id}/messages", timeout=10)
        assert r.status_code == 200
        messages = r.json()
        assert isinstance(messages, list)
        assert len(messages) >= 2, f"Expected at least 2 messages, got {len(messages)}"

        roles = [m["role"] for m in messages]
        assert "user" in roles, "Missing user message"
        assert "assistant" in roles, "Missing assistant message"

        user_msg = next(m for m in messages if m["role"] == "user")
        assistant_msg = next(m for m in messages if m["role"] == "assistant")

        ok("User message found", f"content: {user_msg['content'][:50]}...")
        ok("Assistant message found", f"content: {assistant_msg['content'][:50]}...")
        ok(f"Total messages: {len(messages)}")
    except Exception as e:
        fail("GET messages", str(e))

    # ── 4. PATCH rename ──────────────────────────────────────
    new_title = "Test Chat — Đã đổi tên"
    section("4. PATCH /chat/sessions/{id}/rename")
    try:
        r = requests.patch(
            f"{BASE_URL}/chat/sessions/{session_id}/rename",
            json={"title": new_title},
            timeout=10,
        )
        assert r.status_code == 200
        result = r.json()
        assert result.get("status") == "ok"
        ok("Rename successful", f"new title: {new_title}")
    except Exception as e:
        fail("PATCH rename", str(e))

    # ── 5. GET sessions — Verify new title ───────────────────
    section("5. GET /chat/sessions — Verify new title")
    try:
        r = requests.get(f"{BASE_URL}/chat/sessions", timeout=10)
        sessions = r.json()
        session = next((s for s in sessions if s["id"] == session_id), None)
        assert session is not None, "Session not found"
        assert session["title"] == new_title, f"Title mismatch: {session['title']} != {new_title}"
        ok("Title updated correctly", f"title: {session['title']}")
    except Exception as e:
        fail("Verify new title", str(e))

    # ── 6. PATCH hide ────────────────────────────────────────
    section("6. PATCH /chat/sessions/{id}/hide")
    try:
        r = requests.patch(f"{BASE_URL}/chat/sessions/{session_id}/hide", timeout=10)
        assert r.status_code == 200
        result = r.json()
        assert result.get("hidden") is True
        ok("Hide successful", f"hidden=True")
    except Exception as e:
        fail("PATCH hide", str(e))

    # ── 7. GET sessions — Hidden NOT visible ─────────────────
    section("7. GET /chat/sessions — Hidden NOT visible (default)")
    try:
        r = requests.get(f"{BASE_URL}/chat/sessions", timeout=10)
        sessions = r.json()
        session_ids = [s["id"] for s in sessions]
        if session_id not in session_ids:
            ok("Hidden session NOT in default list")
        else:
            fail("Hidden session still visible in default list")
    except Exception as e:
        fail("GET sessions (hidden check)", str(e))

    # ── 8. GET sessions?include_hidden=true ──────────────────
    section("8. GET /chat/sessions?include_hidden=true — Hidden IS visible")
    try:
        r = requests.get(f"{BASE_URL}/chat/sessions?include_hidden=true", timeout=10)
        sessions = r.json()
        session = next((s for s in sessions if s["id"] == session_id), None)
        assert session is not None, "Hidden session not found with include_hidden=true"
        assert session.get("hidden") is True, "Session should be marked hidden"
        ok("Hidden session visible with include_hidden=true", f"hidden={session['hidden']}")
    except Exception as e:
        fail("GET sessions?include_hidden=true", str(e))

    # ── Summary ──────────────────────────────────────────────
    print(f"\n{'='*60}")
    total = passed + failed
    if failed == 0:
        print(f"{GREEN}{BOLD}✅ All {total} tests passed!{RESET}")
    else:
        print(f"{YELLOW}{BOLD}Result: {passed}/{total} passed, {failed} failed{RESET}")
    print(f"{'='*60}\n")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
