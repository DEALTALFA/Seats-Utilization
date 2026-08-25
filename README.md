# seat-utilization

FastAPI service for recording office seat occupancy and reporting utilization
against a target, packaged with Docker and a GitHub Actions pipeline.

Occupancy is stored in memory — the interesting parts here are the reporting
logic and the delivery pipeline, not persistence. `SeatStore` is the seam to
replace if you need a real database.

## Layout

```
app/
  main.py              app factory + /health
  config.py            APP_*-prefixed settings
  models.py            request/response models
  web.py               server-rendered homepage at /
  api/routes.py        seats, occupancy, reporting endpoints
  api/deps.py          dependency wiring (store singleton)
  services/
    utilization.py     floor plan, occupancy store, rate calculations
.github/workflows/     lint -> test -> build/smoke-test/push image
```

## Local development

```bash
python -m venv .venv && source .venv/Scripts/activate   # Linux/macOS: .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload
```

Homepage at http://localhost:8000/, docs at http://localhost:8000/docs, health at
http://localhost:8000/health.

With Docker instead:

```bash
docker compose up --build     # hot-reload via a bind mount over the installed package
```

## Checks

```bash
ruff check . && ruff format --check .
mypy app
```

`make check` runs all three — the same set CI runs. Coverage is enforced at 85%.

## API

All endpoints are under `/api/v1`. Dates are `YYYY-MM-DD`; ranges are inclusive
on both ends. `GET /` serves a homepage — a snapshot of the trailing 14 days
(hero rate, seat counts, per-day chart, table view) plus links to the docs; it is
server-rendered from the same store and carries no client-side JavaScript. It is
excluded from the OpenAPI schema.

| Method | Path                  | Notes                                              |
| ------ | --------------------- | -------------------------------------------------- |
| GET    | `/`                   | Homepage. HTML, not in the schema.                 |
| GET    | `/health`             | Liveness. No downstream calls.                     |
| GET    | `/seats`              | Optional `floor` filter.                           |
| GET    | `/seats/{seat_id}`    | 404 on unknown seat.                               |
| POST   | `/occupancy`          | Upsert one seat-day. 404 on unknown seat.          |
| GET    | `/utilization`        | Aggregate over `start`/`end`, optional `floor`.     |
| GET    | `/utilization/daily`  | Same range, one row per day.                       |

```bash
curl -X POST localhost:8000/api/v1/occupancy \
  -H 'content-type: application/json' \
  -d '{"seat_id": "1-N01", "day": "2026-08-03"}'

curl "localhost:8000/api/v1/utilization?start=2026-08-03&end=2026-08-07&floor=1"
```

`utilization_rate` is `occupied_seat_days / (seat_count * days)`. A `floor`
filter scopes both the numerator and the denominator, so per-floor rates stay
comparable to the overall one. `meets_target` compares the rate to
`APP_TARGET_UTILIZATION`.

## Configuration

| Variable                  | Default | Purpose                                     |
| ------------------------- | ------- | ------------------------------------------- |
| `APP_ENV`                 | `local` | Reported by `/health`.                      |
| `APP_LOG_LEVEL`           | `INFO`  | Root logger level.                          |
| `APP_TARGET_UTILIZATION`  | `0.75`  | Threshold behind `meets_target`.            |
| `APP_SEED_HISTORY_DAYS`   | `14`    | Days of demo history to seed; `0` disables. |

## Pipeline

`.github/workflows/ci.yml` runs on pushes to `main`, version tags, and PRs:

1. **lint** — ruff lint, ruff format check, mypy.
3. **image** — build with buildx (GHA layer cache), start the container and
   assert `/health` responds, then push to `ghcr.io/<owner>/<repo>` on push
   events. PRs build and smoke-test without pushing.

CD ends at a published, smoke-tested image. There is no rollout step because no
cloud or cluster target is configured — add one when there's an environment to
deploy to.
