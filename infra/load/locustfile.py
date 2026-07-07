"""Load test: 50 users listing, searching, and checking health.

Run (rate limiting must be disabled on the target API):
    cd api && uv run locust -f ../infra/load/locustfile.py \
        --host http://localhost:8000 -u 50 -r 5 --run-time 3m --headless

Pass criteria: p95 < 300 ms on list/search; failure rate < 1%.
"""

import uuid

from locust import HttpUser, between, task


class IdmsUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self) -> None:
        """Each simulated user registers its own org, then reuses the token."""
        suffix = uuid.uuid4().hex[:10]
        resp = self.client.post(
            "/api/v1/auth/register",
            json={
                "org_name": f"Load Org {suffix}",
                "email": f"load-{suffix}@example.com",
                "password": "loadtest-password-1234",
            },
        )
        resp.raise_for_status()
        token = resp.json()["access_token"]
        self.client.headers["Authorization"] = f"Bearer {token}"

    @task(5)
    def list_documents(self) -> None:
        self.client.get("/api/v1/documents", name="/documents [list]")

    @task(3)
    def search(self) -> None:
        self.client.get(
            "/api/v1/search",
            params={"q": "invoice payment terms"},
            name="/search",
        )

    @task(1)
    def health(self) -> None:
        self.client.get("/healthz", name="/healthz")
