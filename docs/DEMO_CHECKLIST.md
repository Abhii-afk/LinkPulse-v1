# LinkPulse Five Minute Demo Checklist

Two scenarios, five minutes, one running stack. Every command below has been
run against the local Docker Compose environment.

| | |
| --- | --- |
| Backend API | http://127.0.0.1:8000 |
| Frontend | http://127.0.0.1:5173 |
| Demo user | `demo@linkpulse.local` / `demo-password-123` |
| Admin | `admin@linkpulse.local` / `admin-password-123` |
| Password on `demo-protected` | `link-password-123` |
| CSV to upload | `demo/links.csv` |

## Before the stage

Run this ten minutes before the demo. It is the same script the rehearsal
uses, so a green run means the stage is ready.

```bash
docker compose up -d --build
cd backend && python -m scripts.seed_demo_data --reset
cd backend && python -m scripts.demo_rehearsal
```

The rehearsal prints the time of every step and fails if the whole run does
not fit into five minutes. Open a second terminal with the frontend on
http://127.0.0.1:5173 and keep it ready.

## Timeline

| Minute | What | Where |
| --- | --- | --- |
| 0:00 - 0:30 | Setup and one line of framing | - |
| 0:30 - 2:30 | Scenario 1: link creation to analytics | Frontend + terminal |
| 2:30 - 4:30 | Scenario 2: CSV import to admin disable | Frontend + terminal |
| 4:30 - 5:00 | Architecture and close | - |

---

## Scenario 1: link creation to analytics (0:30 - 2:30)

**1. Sign in and show the seeded workspace (0:30 - 0:45)**

Open http://127.0.0.1:5173. Sign in with `demo@linkpulse.local` and
`demo-password-123` using the form in the top right. The dashboard then
shows two weeks of history: total clicks, active links, bots filtered and
unique visitors, plus the traffic chart, the device and browser breakdowns
and the managed links table with the expired, disabled and limited links in
their states.

*Say:* "Every number here comes from click events that were written by a
background worker, not by the redirect request."

**2. Create a link with the wizard (0:45 - 1:15)**

Click **Create new link**, fill in the first step:

* Destination URL: `https://example.com/live-demo`
* Custom alias: `live-demo`

Turn on the click limit and set it to `100`. Confirm.

**3. Show the short link and the rules (1:15 - 1:30)**

The toast shows the short URL. Point out that the alias is validated, the
destination was checked against the domain blocklist, and creation is rate
limited to 30 calls per minute per IP.

**4. Send real traffic (1:30 - 1:45)**

Open the short link in a new tab. It redirects immediately. Repeat four
times so the counter moves visibly.

```bash
for i in 1 2 3 4 5; do curl -s -o /dev/null -w "%{http_code} -> %{redirect_url}\n" http://127.0.0.1:8000/live-demo; done
```

**5. Show the analytics move (1:45 - 2:15)**

Return to the dashboard. It polls every 30 seconds; hit refresh and watch
the total clicks and the traffic chart pick the new visits up.

*Say:* "The redirect path never touched PostgreSQL. It resolved the link
from Redis, ran the rule waterfall and pushed one event into a Redis stream.
The worker batched those events into the database."

**6. Show the password challenge (2:15 - 2:30)**

Open http://127.0.0.1:8000/demo-protected. The password challenge appears.
Enter `link-password-123`, and the link opens. Mention that the challenge
cookie is signed and short lived, and that guessing is rate limited.

---

## Scenario 2: CSV import to admin disable (2:30 - 4:30)

**7. Import the CSV (2:30 - 3:15)**

In the terminal, sign in and import `demo/links.csv`:

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@linkpulse.local","password":"demo-password-123"}' \
  | python -c "import json,sys; print(json.load(sys.stdin)['access_token'])")

curl -s -X POST http://127.0.0.1:8000/api/v1/links/bulk \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@demo/links.csv"
```

The response reports six successful imports and one rejected row, with the
row number and the reason. Point at the `broken-row` entry: the parser
reports what went wrong instead of failing the whole file.

**8. Follow an imported link (3:15 - 3:25)**

```bash
curl -s -o /dev/null -w "%{http_code} -> %{redirect_url}\n" http://127.0.0.1:8000/launch-2026
```

**9. Disable a link as the administrator (3:25 - 3:50)**

```bash
ADMIN=$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@linkpulse.local","password":"admin-password-123"}' \
  | python -c "import json,sys; print(json.load(sys.stdin)['access_token'])")

curl -s http://127.0.0.1:8000/api/v1/admin/links -H "Authorization: Bearer $ADMIN"

curl -s -X PATCH http://127.0.0.1:8000/api/v1/admin/links/<LINK_ID>/status \
  -H "Authorization: Bearer $ADMIN" -H "Content-Type: application/json" \
  -d '{"is_active": false, "reason": "phishing confirmed"}'
```

The response contains `"cache_cleared": true`.

**10. Show that the redirect stops immediately (3:50 - 4:05)**

Run the same redirect command again. It returns `410` and the body says the
link is inactive or suspended.

*Say:* "The kill switch deleted the routing cache key, so the next request
never reached a live link. No restart, no deploy."

**11. Show that the history survived (4:05 - 4:30)**

Ask for the analytics of the disabled link:

```bash
curl -s "http://127.0.0.1:8000/api/v1/links/<LINK_ID>/analytics" -H "Authorization: Bearer $ADMIN"
```

The status reads `disabled` and the historical click counts are still there.

*Say:* "Nothing is ever hard deleted. A disabled link keeps its history, so
you can still see what it did before you pulled it."

---

## 4:30 - 5:00: architecture and close

One slide, four numbers:

1. **The hot path never touches the database.** Redis for resolution, one
   `XADD` per click, 302 back.
2. **The worker owns the writes.** Batches of 100, idempotent on the stream
   message id, one bad record cannot block a batch.
3. **The cache is the source of truth for the redirect.** The kill switch
   invalidates it immediately.
4. **Every rule is enforced on the server.** The alias format, the domain
   blocklist, the rate limits, the role checks and the password challenge
   are all backend decisions, not frontend ones.

Close on: *"LinkPulse tells you what your links are doing, and lets you stop
them the second they turn bad."*

---

## If something breaks

| Symptom | Command | Likely cause |
| --- | --- | --- |
| The dashboard is empty | `cd backend && python -m scripts.seed_demo_data --reset` | The database was reseeded |
| The API is down | `docker compose ps` and `docker compose logs api` | The migration failed, so the API never started |
| The worker is not writing | `docker compose logs worker` | The worker cannot reach Redis or PostgreSQL |
| "LinkPulse could not reach the API" | `curl -i -X OPTIONS http://127.0.0.1:8000/api/v1/links -H "Origin: http://127.0.0.1:5173" -H "Access-Control-Request-Method: POST"` | The browser is blocked by CORS. The answer has to contain `access-control-allow-origin: http://127.0.0.1:5173`. Add the origin to `CORS_ALLOWED_ORIGINS` and rebuild the API image |
| The frontend shows no data | check `VITE_API_BASE_URL` and rebuild the image | The bundle points at the wrong API origin |
| The demo port is taken | `docker compose down` and `docker compose up -d` | A host process is holding 8000 or 5173 |

Full stack down, venue internet broken: the whole environment is local, so
the demo still works. That is the contingency in BLUEPRINT section 19.
