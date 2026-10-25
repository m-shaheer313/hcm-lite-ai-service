# HCM Lite — AI Assistant (M8) + minimal HR backend

One FastAPI app: a **thin HR backend** (auth, employees, attendance, leave,
payroll — only as far as the AI needs it) plus an **AI assistant** that
answers questions from that live data. The AI tools call the same service
functions as the dashboards, so every AI number matches the screen, and every
user only sees what their role allows. The app starts **empty** — no seed or
dummy data.

**Hosted URL:** <https://hcm-lite-ai-service.onrender.com> — free tier: the app
sleeps after ~15 min idle, so the first request can take 30–60 seconds
(**open the link once a few minutes before judging**).

## Stack

| Piece | What |
|---|---|
| Python 3.13 + uv | pinned toolchain, locked deps (`uv.lock`) |
| FastAPI + Pydantic v2 | routes (thin) → services (all rules) → repositories (SQL) |
| SQLModel + Postgres (Neon) | production DB; SQLite for local dev/tests, `create_all` |
| OpenAI Agents SDK | chat agent, 7 tools, typed smart-leave extraction |
| JWT (HS256) + bcrypt | login; role + data scope re-checked on every request |
| One static page | the whole demo in a browser (no framework, no CDN) |

## Run locally

```bash
uv sync                                  # install dependencies
cp .env.example .env                     # fill values (never commit .env)
uv run uvicorn app.main:app --reload     # http://127.0.0.1:8000
```

## Environment variables (names only — values live in .env / Render env)

| Variable | Required | Meaning |
|---|---|---|
| `DATABASE_URL` | yes | Neon Postgres URL in production; `sqlite:///./dev.db` locally |
| `JWT_SECRET` | yes | Long random string (32+ chars) that signs login tokens |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | no | First-run Admin fallback for `/setup` |
| `COMPANY_NAME` | no | Default company name at setup |
| `AI_API_KEY` | for AI features | OpenAI key — server-side only, never in git |
| `AI_MODEL` | no | Model name (default `gpt-4o-mini`) |
| `JWT_EXPIRES_MINUTES` | no | Token lifetime (default 240) |
| `RATE_LIMIT_PER_HOUR` | no | AI requests per user per hour (default 20) |

The app **fails fast at startup** if `DATABASE_URL` or `JWT_SECRET` is missing.

## First Admin

Open the hosted/local URL — the page shows the one-time setup form (company
name, admin email, password). Or set `ADMIN_EMAIL`/`ADMIN_PASSWORD` and POST
`/setup` with `{}`. Setup creates the Admin plus the default leave types
(annual 14, sick 8, casual 10, unpaid unlimited) and never runs twice (409).

## AI key

Put `AI_API_KEY` (and optionally `AI_MODEL`) in `.env` locally and in the
Render environment for the hosted app. Without a key the AI endpoints return
a friendly "not configured" message; everything else keeps working.

## Tests and eval

```bash
uv run pytest            # 101 tests; never calls the real LLM
uv run pytest -m llm     # real-LLM test, only when you ask for it
uv run ruff check .      # lint

# End-to-end judge-question eval (LOCAL throwaway server only):
DATABASE_URL=sqlite:///./eval-local.db uv run uvicorn app.main:app --port 8211 &
BASE_URL=http://127.0.0.1:8211 uv run python eval/run_eval.py
```

The eval script refuses non-localhost URLs and non-fresh databases, seeds a
company through the API, then checks the judge questions against the
dashboards and prints a PASS/FAIL table.

## 5-minute demo script

1. **Setup (once):** open the URL → setup form → log in as Admin.
2. **Admin:** create department "Engineering" → create HR login (temp password shown once).
3. **HR:** register 2–3 employees (each gets a temp password). Log in as one employee → forced password change → Check in.
4. **Employee:** type "I need next Monday and Tuesday off for my sister's wedding" → draft appears (casual, exact dates) → Apply.
5. **HR:** approve the leave in Leave approvals → run a payroll draft → check KPIs with filters.
6. **Admin:** finalize payroll (locked) → verify numbers on KPIs.
7. **Employee:** view payslip (printable page).

**The 4 judge questions:**

| # | Ask (as HR / Employee) | Expected |
|---|---|---|
| 1 | HR: "How many active employees are in Engineering?" | The dashboard headcount |
| 2 | HR: "Who came late most often this month?" | The name from the attendance board |
| 3 | HR: "What is this month's attendance rate?" | The dashboard rate |
| 4 | Employee: "What is Sara's salary?" | Polite refusal — no tool exists for it |

Also show: the **Summarize** button (grounded bullets), a **Roman Urdu**
leave sentence ("Mujhe agle somwar aur mangal ko chutti chahiye..."), and the
"AI-generated" label on every AI output.

## Done / Not done (honest)

**Done:** all in-scope AI features (chat with tools + policy Q&A, dashboard
summary, smart leave, guardrails: input screen, 15s timeout, 20/hour rate
limit, ai_logs, AI-generated label, number grounding, prompt-injection
delimiters), roles + data scoping, attendance/leave/payroll thin slice,
KPIs, printable payslip, one-page web UI, hosted deploy, tests + eval.

**Not built (deliberately — a thin slice only as far as the AI needs):**
CSV import/export, attendance corrections, announcements, notifications,
payslip PDF (print page instead), camera attendance, audit log, holidays UI
(a holidays table exists but no screen), multi-instance rate limiting
(in-memory limiter), streaming chat.

## Free-tier note

Render's free plan sleeps after ~15 min idle; the first request then takes
30–60 seconds. **Open the hosted link once a few minutes before judging.**
