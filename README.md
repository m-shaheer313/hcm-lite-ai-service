# HCM Lite — AI Service (M8) + minimal HR backend

One FastAPI app: a thin HR backend (auth, employees, attendance, leave,
payroll) plus an AI assistant that answers questions from the same real data.
The app starts **empty** — no seed or dummy data.

Status and full docs: `spec.md`, `plan.md`, `tasks.md`.

## Run locally (needs Python 3.13 and [uv](https://docs.astral.sh/uv/))

```bash
uv sync                       # install dependencies
cp .env.example .env          # fill in values (never commit .env)
uv run uvicorn app.main:app --reload
```

Then open http://127.0.0.1:8000/health — you should get `{"status": "ok"}`.

### First run

The database starts empty. Create the Admin once:

```bash
curl -X POST http://127.0.0.1:8000/setup \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "ChooseAPassword", "company_name": "My Co"}'
```

If `ADMIN_EMAIL` and `ADMIN_PASSWORD` are set in the environment, `POST /setup`
also works with an empty body `{}`. Default leave types are created by setup:
annual 14, sick 8, casual 10, unpaid unlimited.

## Environment variables

| Variable | Required | Meaning |
|---|---|---|
| `DATABASE_URL` | yes | Postgres (Neon) in production, `sqlite:///./dev.db` locally |
| `JWT_SECRET` | yes | Long random string used to sign tokens (32+ bytes) |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | no | First-run Admin fallback for `/setup` |
| `COMPANY_NAME` | no | Default company name at setup |
| `AI_API_KEY` | no (AI tasks) | OpenAI key; server-side only |
| `AI_MODEL` | no | Model name (small, cheap default) |
| `JWT_EXPIRES_MINUTES` | no | Token lifetime, default 240 |
| `RATE_LIMIT_PER_HOUR` | no | AI requests per user per hour, default 20 |

## Deploy to Render + Neon (test deploy)

1. **Neon**: create a project → copy the connection string (it includes
   `sslmode=require`). This is `DATABASE_URL`.
2. **GitHub**: push this repo (branch `main`).
3. **Render**: New → Web Service → connect the repo.
   - Runtime: **Python 3** (set env var `PYTHON_VERSION=3.13`)
   - Build command: `pip install uv && uv sync --frozen`
   - Start command: `uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Environment variables: `DATABASE_URL`, `JWT_SECRET` (long random),
     optionally `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `COMPANY_NAME`.
4. Wait for the first deploy, then check `https://<your-app>.onrender.com/health`.
5. `POST /setup` once (or rely on the env Admin). Tables are created
   automatically on startup (`create_all`).

## Tests

```bash
uv run pytest        # all tests; never calls the real LLM
uv run ruff check .  # lint
```

Tests that need the real LLM are behind a marker and never run by default:
`uv run pytest -m llm`.
