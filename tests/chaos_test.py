#!/usr/bin/env python3
"""
Chaos Test: Kill Redis/PG mid-request, verifikasi graceful degrade.

Jalankan:
  python tests/chaos_test.py

Butuh: PostgreSQL & Redis jalan, server API di port 8080.
"""

import subprocess
import sys
import time
import requests
from typing import List, Dict, Any

API_BASE = "http://localhost:8080"
SESSION_ID = "chaos_test_001"


def check_service(name: str, check_fn) -> bool:
    """Cek service, return True jika healthy."""
    try:
        return check_fn()
    except Exception as e:
        print(f"  ✗ {name}: {e}")
        return False


def pg_check() -> bool:
    import psycopg2
    from src.config.routing_keywords_pg import DATABASE_URL
    conn = psycopg2.connect(DATABASE_URL, connect_timeout=3)
    conn.close()
    return True


def redis_check() -> bool:
    import redis
    r = redis.from_url("redis://localhost:6379/0", socket_connect_timeout=2, socket_timeout=2)
    return r.ping()


def api_health() -> bool:
    r = requests.get(f"{API_BASE}/health", timeout=5)
    return r.status_code == 200 and r.json().get("postgres", {}).get("status") == "up"


def send_chat(message: str, session_id: str = SESSION_ID) -> Dict[str, Any]:
    """Kirim pesan ke API, return response JSON atau error."""
    try:
        r = requests.post(
            f"{API_BASE}/chat",
            json={"message": message, "session_id": session_id},
            timeout=30,
        )
        return {"status": r.status_code, "data": r.json()}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def run_chaos_scenario(name: str, kill_fn, restore_fn, test_messages: List[str]) -> Dict[str, Any]:
    """Jalankan satu skenario chaos."""
    print(f"\n=== {name} ===")
    results = []

    # Baseline: pastikan service healthy
    for msg in test_messages:
        print(f"  Baseline: '{msg[:40]}...'")
        r = send_chat(msg)
        results.append({"phase": "baseline", "msg": msg, **r})
        time.sleep(1)

    # Kill service
    print(f"  Killing service...")
    kill_fn()
    time.sleep(2)

    # Test during outage
    for msg in test_messages:
        print(f"  During outage: '{msg[:40]}...'")
        r = send_chat(msg)
        results.append({"phase": "outage", "msg": msg, **r})
        time.sleep(1)

    # Restore service
    print(f"  Restoring service...")
    restore_fn()
    time.sleep(3)

    # Test after restore
    for msg in test_messages:
        print(f"  After restore: '{msg[:40]}...'")
        r = send_chat(msg)
        results.append({"phase": "restored", "msg": msg, **r})
        time.sleep(1)

    # Analisis
    baseline_ok = all(r.get("status") == 200 for r in results if r["phase"] == "baseline")
    outage_graceful = all(
        r.get("status") in (200, 503, 504) and "error" not in str(r.get("data", "")).lower()
        for r in results if r["phase"] == "outage"
    )
    restored_ok = all(r.get("status") == 200 for r in results if r["phase"] == "restored")

    print(f"  Baseline OK: {baseline_ok}")
    print(f"  Outage graceful: {outage_graceful}")
    print(f"  Restored OK: {restored_ok}")

    return {
        "scenario": name,
        "baseline_ok": baseline_ok,
        "outage_graceful": outage_graceful,
        "restored_ok": restored_ok,
        "details": results,
    }


def main():
    print("=== CHAOS TEST: Graceful Degradation ===")
    print(f"Target API: {API_BASE}")

    # Pre-check
    print("\nPre-check services...")
    if not check_service("PostgreSQL", pg_check):
        print("PostgreSQL not available, skipping")
        return 1
    if not check_service("Redis", redis_check):
        print("Redis not available, skipping")
        return 1
    if not check_service("API", api_health):
        print("API not healthy, start server first")
        return 1
    print("All services healthy")

    test_messages = [
        "halo, apa kabar?",
        "jelaskan REST API singkat",
        "carikan harga emas hari ini",
    ]

    all_results = []

    # Scenario 1: Kill Redis
    def kill_redis():
        subprocess.run(["docker", "stop", "redis"], capture_output=True)
    def restore_redis():
        subprocess.run(["docker", "start", "redis"], capture_output=True)

    # Cek apakah Redis jalan di Docker
    try:
        subprocess.run(["docker", "ps", "--filter", "name=redis"], check=True, capture_output=True)
        all_results.append(run_chaos_scenario("Kill Redis", kill_redis, restore_redis, test_messages))
    except subprocess.CalledProcessError:
        print("Skipping Redis kill (not in Docker)")

    # Scenario 2: Kill PostgreSQL
    def kill_pg():
        subprocess.run(["docker", "stop", "postgres"], capture_output=True)
    def restore_pg():
        subprocess.run(["docker", "start", "postgres"], capture_output=True)

    try:
        subprocess.run(["docker", "ps", "--filter", "name=postgres"], check=True, capture_output=True)
        all_results.append(run_chaos_scenario("Kill PostgreSQL", kill_pg, restore_pg, test_messages))
    except subprocess.CalledProcessError:
        print("Skipping PostgreSQL kill (not in Docker)")

    # Scenario 3: Network partition (block API -> Redis)
    # Skip - complex, but conceptually similar

    # Summary
    print("\n=== SUMMARY ===")
    for r in all_results:
        status = "✓" if all([r["baseline_ok"], r["outage_graceful"], r["restored_ok"]]) else "✗"
        print(f"  {status} {r['scenario']}: baseline={r['baseline_ok']}, outage_graceful={r['outage_graceful']}, restored={r['restored_ok']}")

    return 0 if all_results else 1


if __name__ == "__main__":
    sys.exit(main())