#!/usr/bin/env python3
"""
Nexus AI – Integration Test Suite
Tests complete flows across all services.
Run after `docker compose up --build` with: python tests/integration/test_integration.py
"""

import os
import sys
import time
import json
import uuid
import requests

BASE_URL = os.getenv("NEXUS_BASE_URL", "http://localhost")
API = f"{BASE_URL}/api/v1"

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"

results = []


def check(name: str, passed: bool, detail: str = ""):
    status = PASS if passed else FAIL
    print(f"  {status} {name}" + (f" — {detail}" if detail else ""))
    results.append((name, passed))


def section(title: str):
    print(f"\n{'─'*50}\n  {title}\n{'─'*50}")


# ── Health ────────────────────────────────────────────────────────────────────

section("Health Checks")

r = requests.get(f"{API}/health", timeout=10)
check("Backend /health responds 200", r.status_code == 200)
if r.status_code == 200:
    body = r.json()
    check("Health status field present", "status" in body)
    check("Backend reports healthy or degraded", body.get("status") in ("healthy", "degraded"))

# ── Auth ──────────────────────────────────────────────────────────────────────

section("Authentication")

test_email = f"test_{uuid.uuid4().hex[:8]}@nexus-test.local"
test_password = "TestPass123!"
test_name = "Integration Tester"

r = requests.post(f"{API}/auth/register", json={
    "email": test_email,
    "password": test_password,
    "full_name": test_name,
    "organization_name": "Integration Test Organization",
}, timeout=10)
check("Register new user (201)", r.status_code == 201, f"got {r.status_code}")

token = None
if r.status_code == 201:
    body = r.json()
    check("Register returns user object", body.get("email") == test_email)

r = requests.post(f"{API}/auth/login", json={
    "email": test_email,
    "password": test_password,
}, timeout=10)
check("Login (200)", r.status_code == 200, f"got {r.status_code}")
if r.status_code == 200:
    token = r.json().get("access_token")
    check("Login returns access_token", token is not None)

r = requests.post(f"{API}/auth/login", json={
    "email": test_email,
    "password": "wrong_password",
}, timeout=10)
check("Login with wrong password (401)", r.status_code == 401)

headers = {"Authorization": f"Bearer {token}"} if token else {}

r = requests.get(f"{API}/auth/me", headers=headers, timeout=10)
check("GET /auth/me (200)", r.status_code == 200)
if r.status_code == 200:
    me = r.json()
    check("Me returns correct email", me.get("email") == test_email)

r = requests.get(f"{API}/auth/me", timeout=10)
check("GET /auth/me without token (401)", r.status_code == 401)

# ── Data Sources ──────────────────────────────────────────────────────────────

section("Data Sources")

r = requests.get(f"{API}/sources", headers=headers, timeout=10)
check("GET /sources (200)", r.status_code == 200)
if r.status_code == 200:
    body = r.json()
    check("Sources response has items array", "items" in body)
    check("Sources response has total", "total" in body)

r = requests.post(f"{API}/sources", headers=headers, json={
    "name": "Integration Test Source",
    "type": "txt",
    "config": {},
}, timeout=10)
check("POST /sources create (201)", r.status_code == 201, f"got {r.status_code}")

source_id = None
if r.status_code == 201:
    source = r.json()
    source_id = source.get("id")
    check("Source has id", source_id is not None)
    check("Source has correct type", source.get("type") == "txt")

if source_id:
    r = requests.get(f"{API}/sources/{source_id}", headers=headers, timeout=10)
    check("GET /sources/{id} (200)", r.status_code == 200)

    r = requests.get(f"{API}/sources/{uuid.uuid4()}", headers=headers, timeout=10)
    check("GET /sources/{nonexistent} (404)", r.status_code == 404)

# ── File Upload ───────────────────────────────────────────────────────────────

section("File Upload")

test_content = b"This is a test document for Nexus AI integration testing."
r = requests.post(
    f"{API}/upload",
    headers=headers,
    files={"files": ("test.txt", test_content, "text/plain")},
    timeout=30,
)
check("POST /upload (202)", r.status_code == 202, f"got {r.status_code}")

job_id = None
if r.status_code == 202:
    body = r.json()
    job_id = body.get("job", {}).get("id")
    check("Upload returns job id", job_id is not None)
    check("Upload returns source_id", body.get("source_id") is not None)

# ── Ingestion Job ─────────────────────────────────────────────────────────────

section("Ingestion Job")

if job_id:
    r = requests.get(f"{API}/jobs/{job_id}", headers=headers, timeout=10)
    check("GET /jobs/{id} (200)", r.status_code == 200)
    if r.status_code == 200:
        job = r.json()
        check("Job has status field", "status" in job)
        check("Job status is valid", job.get("status") in ("queued", "running", "completed", "failed"))

# ── Chat ──────────────────────────────────────────────────────────────────────

section("Chat (non-streaming)")

r = requests.post(f"{API}/chat", headers=headers, json={
    "query": "What is Nexus AI?",
    "stream": False,
}, timeout=60)
check("POST /chat non-streaming (200)", r.status_code == 200, f"got {r.status_code}")
if r.status_code == 200:
    msg = r.json()
    check("Chat response has content", bool(msg.get("content")))
    check("Chat response has role=assistant", msg.get("role") == "assistant")

section("Chat Sessions")

r = requests.get(f"{API}/chat/sessions", headers=headers, timeout=10)
check("GET /chat/sessions (200)", r.status_code == 200)
if r.status_code == 200:
    body = r.json()
    check("Sessions response has items", "items" in body)

# ── Summary ───────────────────────────────────────────────────────────────────

section("Results")
passed = sum(1 for _, p in results if p)
total = len(results)
print(f"\n  {passed}/{total} checks passed\n")

if passed < total:
    failed = [name for name, p in results if not p]
    print("  Failed:")
    for name in failed:
        print(f"    {FAIL} {name}")
    sys.exit(1)

sys.exit(0)
