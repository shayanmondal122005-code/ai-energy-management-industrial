#!/usr/bin/env python3
"""Post-deploy production verifier with automatic rollback.

Run by .github/workflows/verify-deploy.yml after CI passes on main and the
platforms (Railway / Vercel) have had time to publish the new version.

What it does:
  1. Polls  <PROD_URL>/health/ready  repeatedly.
  2. If the new version becomes healthy  -> exit 0  (deploy confirmed good).
  3. If it stays unhealthy past the grace window -> roll the backend back to
     the previous successful Railway deployment and exit 1 (so GitHub notifies
     you). The bad update is cancelled automatically.

Why both this AND the Railway healthcheck?
  Railway's healthcheck already stops a deploy that fails /health/ready from
  ever receiving traffic. This script is the SECOND net: it catches a deploy
  that *passes* the healthcheck but is still broken at runtime (a logic
  regression, a bad query, a climbing error rate) and reverts it.

Environment variables (only PROD_URL is required):
  PROD_URL                 e.g. https://ai-energy-managementat12.up.railway.app
  RAILWAY_API_TOKEN        Railway token            (enables auto-rollback)
  RAILWAY_SERVICE_ID       backend service id
  RAILWAY_ENVIRONMENT_ID   production environment id
"""
import os
import sys
import time

import httpx

PROD_URL = os.environ.get("PROD_URL", "").rstrip("/")
RAILWAY_API_TOKEN = os.environ.get("RAILWAY_API_TOKEN")
RAILWAY_SERVICE_ID = os.environ.get("RAILWAY_SERVICE_ID")
RAILWAY_ENVIRONMENT_ID = os.environ.get("RAILWAY_ENVIRONMENT_ID")

RAILWAY_API = "https://backboard.railway.app/graphql/v2"

ATTEMPTS = 10    # number of health polls
INTERVAL = 30    # seconds between polls -> ~5 min grace window
TIMEOUT = 10     # per-request timeout


def check_ready() -> bool:
    """True only if /health/ready returns 200 with ready=true."""
    try:
        r = httpx.get(f"{PROD_URL}/health/ready", timeout=TIMEOUT)
        return r.status_code == 200 and r.json().get("ready") is True
    except Exception as e:
        print(f"  health check error: {e}")
        return False


def railway_graphql(query: str, variables: dict) -> dict:
    r = httpx.post(
        RAILWAY_API,
        json={"query": query, "variables": variables},
        headers={"Authorization": f"Bearer {RAILWAY_API_TOKEN}"},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]


def rollback_railway() -> bool:
    """Roll the service back to the most recent previously-successful deploy."""
    if not (RAILWAY_API_TOKEN and RAILWAY_SERVICE_ID and RAILWAY_ENVIRONMENT_ID):
        print("Railway rollback secrets not set — skipping auto-rollback.")
        print("Roll back manually: Railway dashboard -> service -> Deployments -> previous -> Rollback.")
        return False
    query = """
    query($serviceId: String!, $environmentId: String!) {
      deployments(first: 5, input: { serviceId: $serviceId, environmentId: $environmentId }) {
        edges { node { id status createdAt } }
      }
    }"""
    data = railway_graphql(query, {
        "serviceId": RAILWAY_SERVICE_ID,
        "environmentId": RAILWAY_ENVIRONMENT_ID,
    })
    nodes = [e["node"] for e in data["deployments"]["edges"]]  # newest first
    # nodes[0] is the current (bad) deploy; find the next one that succeeded.
    target = next((n for n in nodes[1:] if n["status"] == "SUCCESS"), None)
    if not target:
        print("No previous successful deployment found to roll back to.")
        return False
    mutation = "mutation($id: String!) { deploymentRollback(id: $id) }"
    railway_graphql(mutation, {"id": target["id"]})
    print(f"Rolled back to deployment {target['id']} (created {target['createdAt']}).")
    return True


def main() -> int:
    if not PROD_URL:
        print("PROD_API_URL secret not set — skipping production verification.")
        print("Set PROD_API_URL (and the RAILWAY_* secrets) to enable post-deploy")
        print("health checks and automatic rollback. See docs/CICD.md.")
        return 0  # not-yet-configured is not a failure
    print(f"Verifying {PROD_URL}/health/ready  ({ATTEMPTS} polls, {INTERVAL}s apart)")
    for i in range(1, ATTEMPTS + 1):
        if check_ready():
            print(f"[{i}/{ATTEMPTS}] ready OK — deploy confirmed healthy.")
            return 0
        print(f"[{i}/{ATTEMPTS}] not ready yet...")
        if i < ATTEMPTS:
            time.sleep(INTERVAL)
    print("Production never became ready within the grace window.")
    print("Triggering automatic rollback...")
    rollback_railway()
    return 1  # always fail the job so you get notified


if __name__ == "__main__":
    sys.exit(main())
