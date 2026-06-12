"""
Locust load test for realtime-hub.

Usage:
    # Start the app first (with a real DB + Redis):
    #   docker-compose up db redis
    #   DATABASE_URL=postgresql://hub:hub@localhost/realtime_hub \\
    #   REDIS_URL=redis://localhost:6379/0 python app.py

    # Headless (CI) — 100 users, 10 spawn/s, run for 60 seconds:
    locust -f load_test.py --headless -u 100 -r 10 -t 60s --host http://localhost:5000

    # Web UI:
    locust -f load_test.py --host http://localhost:5000
"""

import random
from locust import HttpUser, task, between, events


class RealtimeHubUser(HttpUser):
    """Simulates a user who registers, creates a channel, and posts/reads messages."""

    wait_time = between(0.5, 2.0)

    channel_id: int | None = None
    token: str | None = None
    headers: dict | None = None

    def on_start(self) -> None:
        uid = random.randint(1, 10_000_000)
        username = f"loaduser_{uid}"

        # Register and get auth token
        resp = self.client.post(
            "/auth/register",
            json={
                "username": username,
                "email": f"{username}@loadtest.example",
                "password": "loadtest_secret",
            },
            name="/auth/register",
        )
        if resp.status_code != 201:
            self.token = None
            return

        data = resp.json()
        self.token = data["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

        # Create a private channel for this user
        ch_resp = self.client.post(
            "/channels",
            json={"name": f"ch_{uid}"},
            headers=self.headers,
            name="/channels [POST]",
        )
        if ch_resp.status_code == 201:
            self.channel_id = ch_resp.json()["id"]

    # ---- tasks ----------------------------------------------------------------

    @task(4)
    def post_message(self) -> None:
        if not self.channel_id or not self.headers:
            return
        self.client.post(
            f"/channels/{self.channel_id}/messages",
            json={"content": f"load test msg {random.randint(1, 100_000)}"},
            headers=self.headers,
            name="/channels/[id]/messages [POST]",
        )

    @task(2)
    def read_messages(self) -> None:
        if not self.channel_id or not self.headers:
            return
        self.client.get(
            f"/channels/{self.channel_id}/messages?limit=20",
            headers=self.headers,
            name="/channels/[id]/messages [GET]",
        )

    @task(1)
    def read_messages_desc(self) -> None:
        if not self.channel_id or not self.headers:
            return
        self.client.get(
            f"/channels/{self.channel_id}/messages?limit=20&order=desc",
            headers=self.headers,
            name="/channels/[id]/messages?order=desc",
        )

    @task(1)
    def health_check(self) -> None:
        self.client.get("/health", name="/health")


# ---- Event hooks (print summary stats) --------------------------------------

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs) -> None:
    stats = environment.stats.total
    print(
        f"\n=== Load Test Summary ===\n"
        f"  Requests:      {stats.num_requests}\n"
        f"  Failures:      {stats.num_failures}\n"
        f"  Failure rate:  {stats.fail_ratio * 100:.1f}%\n"
        f"  Avg latency:   {stats.avg_response_time:.1f} ms\n"
        f"  p95 latency:   {stats.get_response_time_percentile(0.95):.1f} ms\n"
        f"  p99 latency:   {stats.get_response_time_percentile(0.99):.1f} ms\n"
        f"  Throughput:    {stats.total_rps:.1f} req/s\n"
    )
