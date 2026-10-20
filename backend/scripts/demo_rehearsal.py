"""Timed dry run of the five minute LinkPulse demo.

    cd backend && python -m scripts.demo_rehearsal

The script drives a running instance through the two scenarios of the demo
protocol and prints how long each step took:

1. link creation to analytics
2. CSV import to admin disable

It only uses the standard library, so it runs wherever the backend runs.
The credentials default to the ones written by
``python -m scripts.seed_demo_data`` and can be overridden with
``LINKPULSE_DEMO_EMAIL``, ``LINKPULSE_DEMO_PASSWORD``,
``LINKPULSE_DEMO_ADMIN_EMAIL`` and ``LINKPULSE_DEMO_ADMIN_PASSWORD``.
"""

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_DEMO_EMAIL = "demo@linkpulse.local"
DEFAULT_DEMO_PASSWORD = "demo-password-123"
DEFAULT_ADMIN_EMAIL = "admin@linkpulse.local"
DEFAULT_ADMIN_PASSWORD = "admin-password-123"
FIVE_MINUTES_SECONDS = 300


class DemoFailure(RuntimeError):
    """Raised when a demo step did not behave as the script expects."""


@dataclass(frozen=True, slots=True)
class Response:
    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8")) if self.body else None

    @property
    def location(self) -> str:
        return self.headers.get("location", "")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Keeps the 302 visible instead of following it."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


class HttpClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.opener = urllib.request.build_opener(_NoRedirect)

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> Response:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers=headers or {},
        )
        try:
            with self.opener.open(request, timeout=20) as raw:
                return Response(
                    status=raw.status,
                    headers={key.lower(): value for key, value in raw.headers.items()},
                    body=raw.read(),
                )
        except urllib.error.HTTPError as error:
            return Response(
                status=error.code,
                headers={key.lower(): value for key, value in error.headers.items()},
                body=error.read(),
            )

    def get(self, path: str, headers: dict[str, str] | None = None) -> Response:
        return self.request("GET", path, headers=headers)

    def post_json(
        self,
        path: str,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> Response:
        merged = {"Content-Type": "application/json", **(headers or {})}
        return self.request(
            "POST",
            path,
            body=json.dumps(payload).encode("utf-8"),
            headers=merged,
        )

    def post_form(
        self,
        path: str,
        fields: dict[str, str],
        headers: dict[str, str] | None = None,
    ) -> Response:
        merged = {"Content-Type": "application/x-www-form-urlencoded", **(headers or {})}
        encoded = "&".join(
            f"{key}={urllib.parse.quote(value)}" for key, value in fields.items()
        )
        return self.request("POST", path, body=encoded.encode("utf-8"), headers=merged)

    def patch_json(
        self,
        path: str,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> Response:
        merged = {"Content-Type": "application/json", **(headers or {})}
        return self.request(
            "PATCH",
            path,
            body=json.dumps(payload).encode("utf-8"),
            headers=merged,
        )

    def post_multipart(
        self,
        path: str,
        filename: str,
        content: bytes,
        content_type: str = "text/csv",
        headers: dict[str, str] | None = None,
    ) -> Response:
        boundary = f"----linkpulse{uuid.uuid4().hex}"
        body = b"".join(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                (
                    f'Content-Disposition: form-data; name="file"; '
                    f'filename="{filename}"\r\n'
                ).encode("utf-8"),
                f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
                content,
                f"\r\n--{boundary}--\r\n".encode("utf-8"),
            ]
        )
        merged = {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            **(headers or {}),
        }
        return self.request("POST", path, body=body, headers=merged)


def sign_in(client: HttpClient, email: str, password: str) -> dict[str, str]:
    response = client.post_json(
        "/api/v1/auth/login",
        {"email": email, "password": password},
    )
    if response.status != 200:
        raise DemoFailure(f"login for {email} failed with {response.status}: {response.body!r}")
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


class Rehearsal:
    def __init__(self, client: HttpClient) -> None:
        self.client = client
        self.elapsed: dict[str, float] = {}

    def timed(self, name: str, action):  # type: ignore[no-untyped-def]
        start = time.monotonic()
        result = action()
        self.elapsed[name] = time.monotonic() - start
        print(f"  {name:<38} {self.elapsed[name]:>6.2f}s")
        return result


def run_scenario_one(rehearsal: Rehearsal, headers: dict[str, str]) -> None:
    """Link creation to analytics."""

    print("Scenario 1: link creation to analytics")
    suffix = uuid.uuid4().hex[:8]
    alias = f"demo-live-{suffix}"

    created = rehearsal.timed(
        "create the link",
        lambda: rehearsal.client.post_json(
            "/api/v1/links",
            {
                "destination_url": "https://example.com/live-demo",
                "custom_alias": alias,
                "rules": {"click_limit": 100},
            },
            headers=headers,
        ),
    )
    if created.status != 201:
        raise DemoFailure(f"link creation returned {created.status}: {created.body!r}")
    link_id = created.json()["id"]

    def click() -> None:
        for _ in range(5):
            response = rehearsal.client.get(f"/{alias}")
            if response.status != 302:
                raise DemoFailure(f"redirect returned {response.status}: {response.body!r}")

    rehearsal.timed("click the link five times", click)

    overview = rehearsal.timed(
        "read the analytics overview",
        lambda: rehearsal.client.get("/api/v1/analytics/overview", headers=headers),
    )
    if overview.status != 200:
        raise DemoFailure(f"analytics returned {overview.status}: {overview.body!r}")
    summary = overview.json()["summary"]
    print(
        f"    total clicks {summary['total_clicks']}, "
        f"active links {summary['active_links']}, "
        f"unique visitors {summary['unique_visitors']}"
    )

    link_analytics = rehearsal.timed(
        "read the per link analytics",
        lambda: rehearsal.client.get(f"/api/v1/links/{link_id}/analytics", headers=headers),
    )
    if link_analytics.status != 200:
        raise DemoFailure(f"link analytics returned {link_analytics.status}")


def run_scenario_two(
    rehearsal: Rehearsal,
    user_headers: dict[str, str],
    admin_headers: dict[str, str],
) -> None:
    """CSV import to admin disable."""

    print("Scenario 2: CSV import to admin disable")
    suffix = uuid.uuid4().hex[:8]
    csv_content = (
        "destination_url,custom_alias\n"
        f"https://example.com/imported-one,import-{suffix}-one\n"
        f"https://example.com/imported-two,import-{suffix}-two\n"
        "not-a-url,import-broken\n"
    )

    imported = rehearsal.timed(
        "import the CSV file",
        lambda: rehearsal.client.post_multipart(
            "/api/v1/links/bulk",
            "links.csv",
            csv_content.encode("utf-8"),
            headers=user_headers,
        ),
    )
    if imported.status != 200:
        raise DemoFailure(f"bulk import returned {imported.status}: {imported.body!r}")
    body = imported.json()
    print(
        f"    imported {body['successful_imports']} of {body['total_processed']} rows, "
        f"{body['failed_imports']} rejected"
    )

    alias = f"import-{suffix}-one"
    before = rehearsal.timed(
        "follow the imported link",
        lambda: rehearsal.client.get(f"/{alias}"),
    )
    if before.status != 302:
        raise DemoFailure(f"imported link returned {before.status}: {before.body!r}")

    managed = rehearsal.timed(
        "open the admin link list",
        lambda: rehearsal.client.get("/api/v1/admin/links", headers=admin_headers),
    )
    if managed.status != 200:
        raise DemoFailure(f"admin list returned {managed.status}: {managed.body!r}")
    target = next(
        (item for item in managed.json() if item["short_code"] == alias),
        None,
    )
    if target is None:
        raise DemoFailure(f"the imported link {alias} is not in the admin list")

    disabled = rehearsal.timed(
        "disable the link with the kill switch",
        lambda: rehearsal.client.patch_json(
            f"/api/v1/admin/links/{target['id']}/status",
            payload={"is_active": False, "reason": "rehearsal kill switch"},
            headers=admin_headers,
        ),
    )
    if disabled.status != 200:
        raise DemoFailure(f"kill switch returned {disabled.status}: {disabled.body!r}")
    if disabled.json()["cache_cleared"] is not True:
        raise DemoFailure("the kill switch did not clear the routing cache")

    after = rehearsal.timed(
        "confirm the redirect is gone",
        lambda: rehearsal.client.get(f"/{alias}"),
    )
    if after.status != 410:
        raise DemoFailure(f"disabled link returned {after.status}, expected 410")

    analytics = rehearsal.timed(
        "confirm the history survived",
        lambda: rehearsal.client.get(
            f"/api/v1/links/{target['id']}/analytics",
            headers=admin_headers,
        ),
    )
    if analytics.status != 200:
        raise DemoFailure(f"analytics after disable returned {analytics.status}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rehearse the LinkPulse demo")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("LINKPULSE_DEMO_BASE_URL", DEFAULT_BASE_URL),
        help="Base URL of the running LinkPulse API",
    )
    parser.add_argument(
        "--email",
        default=os.environ.get("LINKPULSE_DEMO_EMAIL", DEFAULT_DEMO_EMAIL),
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("LINKPULSE_DEMO_PASSWORD", DEFAULT_DEMO_PASSWORD),
    )
    parser.add_argument(
        "--admin-email",
        default=os.environ.get("LINKPULSE_DEMO_ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL),
    )
    parser.add_argument(
        "--admin-password",
        default=os.environ.get("LINKPULSE_DEMO_ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = HttpClient(args.base_url)
    rehearsal = Rehearsal(client)

    print(f"LinkPulse demo rehearsal against {args.base_url}")
    start = time.monotonic()

    health = rehearsal.timed(
        "check the health endpoint",
        lambda: client.get("/health"),
    )
    if health.status != 200:
        print(f"  the API is not healthy: {health.body!r}")
        return 1
    print(f"    checks: {health.json()['checks']}")

    try:
        user_headers = sign_in(client, args.email, args.password)
        admin_headers = sign_in(client, args.admin_email, args.admin_password)
        run_scenario_one(rehearsal, user_headers)
        run_scenario_two(rehearsal, user_headers, admin_headers)
    except DemoFailure as error:
        print(f"\nrehearsal failed: {error}")
        return 1

    total = time.monotonic() - start
    print(f"\ntotal {total:.2f}s of the {FIVE_MINUTES_SECONDS}s budget")
    if total > FIVE_MINUTES_SECONDS:
        print("the rehearsal does not fit into five minutes")
        return 1
    print("rehearsal passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
