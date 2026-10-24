# plan.md — HCM Lite (solo build: minimal HR backend + AI Assistant M8)

## 1. Architecture

One FastAPI app in the repo root. Three layers, strict direction:

```
Browser (one static page: HTML + Tailwind CDN + small JS, served by FastAPI)
   │  JWT in Authorization header
   ▼
routes/          HTTP only: parse, auth dependency, call a service, return model
   ▼
services/        ALL business rules + permission checks (the same functions
   ▼             the AI tools call)
repositories/    SQLModel queries. Parameterized only; no string-built SQL.
   ▼
Neon Postgres (DATABASE_URL) — SQLite for local dev and tests. create_all.
```

AI side:

```
agents/         OpenAI Agents SDK: chat agent, smart-leave agent, summary agent
tools/          7 tools + role allowlist. A tool calls ONE service function.
                A tool NEVER queries the database directly.
guardrails/     input guardrail, rate limit (20/user/hour), number grounding
policy/policy.md  loaded into the system prompt
logging_db.py   ai_logs table (same DB; DB down → stdout, request still works)
```

Key decisions:

- **Tools reuse services.** This is the whole security story: the AI has the
  same access as the user, because it runs the same service functions with the
  same permission checks as the REST routes. The tool's context carries the
  verified user (role, employee_id) — never a role from the client.
- **No mock client, no team contract.** That part of the old plan is deleted.
  Test fixtures create data in tests; the real app starts empty.
- **First run**: `POST /setup` works only while no user exists; it creates the
  company, the Admin (from env or form), and default leave types from the
  brief rules. Defaults are configuration, not dummy data.
- **JWT**: HS256, secret from env, bcrypt password hashing. Temporary password
  flag forces a change at first sign-in.
- **The seven AI tools**: `get_headcount`, `get_attendance_summary`,
  `get_late_comers`, `get_leave_summary`, `get_my_leave_balance`,
  `get_payroll_summary`, `search_employees`. Allowlist: Admin/HR get all;
  Employee gets only `get_my_leave_balance`. The model physically has no tool
  it must not use.

## 2. What I chose and why

| Choice | Why |
|---|---|
| One app, three layers | Solo, 9 hours. Fewer moving parts than a separate AI service; tools calling the same services guarantees AI answers match the dashboard. |
| SQLModel + create_all, no Alembic | Spec requirement. Fast; fine for a hackathon schema. |
| Neon Postgres + SQLite fallback | Neon free tier for the deployed demo; SQLite makes tests fast with no network. |
| OpenAI Agents SDK 0.24.0 | One package gives tools, structured output, guardrails, max_turns, tracing — every feature the spec lists. |
| Role allowlist per request | Build the agent with only that role's tools. Refusal needs no prompt trick. |
| Pure functions for `resolve_dates`, leave validation, tax, number grounding | Easy to test; the LLM never does date maths (Asia/Karachi). |
| In-memory rate limiter | Enough for one instance. Code comment: multi-instance needs Redis. |
| Static page served by FastAPI | No build step, no second deploy, works on Render free tier. |
| Early deploy (end of Task 3) | Find Render/Neon problems on night one, not at 4 AM. |

## 3. Verified SDK notes (openai-agents 0.24.0, official docs — not guessed)

- Import root is `agents`; requires Python ≥3.10.
- **Tools**: `@function_tool` (options: `name_override`, `timeout`,
  `failure_error_function`). Docstring + Pydantic `Field` build the schema;
  attach via `Agent(tools=[...])`.
- **Structured output**: `Agent(output_type=SomePydanticModel)`; read
  `result.final_output`.
- **Guardrails**: `@input_guardrail` returns
  `GuardrailFunctionOutput(output_info=..., tripwire_triggered=...)`; attach via
  `Agent(input_guardrails=[...])`; trips raise `InputGuardrailTripwireTriggered`.
- **User context**: `Runner.run(..., context=my_obj)`; tools take
  `RunContextWrapper[T]` as first parameter, read `wrapper.context`; context is
  never sent to the LLM; one context type per run. Plan: a dataclass with
  `user_id`, `employee_id`, `role`, `db session`, `services`.
- **Limits**: `Runner.run(..., max_turns=N)` (raise `MaxTurnsExceeded`);
  `RunConfig(model_settings=ModelSettings(max_tokens=..., timeout=...))`.
- **Tracing**: on by default; disable with `OPENAI_AGENTS_DISABLE_TRACING=1`;
  set `OPENAI_AGENTS_TRACE_INCLUDE_SENSITIVE_DATA=false` so tool data never
  leaves in traces.

## 4. Assumptions (open)

| # | Assumption | If wrong |
|---|---|---|
| A1 | `AI_MODEL` = a small, cheap OpenAI model; free tier is enough per the brief. | Config-only change. |
| A2 | Python pinned to 3.13 unless Task 1 verifies 3.14 with every dependency. | One line. |
| A3 | Neon + Render free tiers are enough for the demo (single instance). | Rate limiter/limiter comments already note the multi-instance caveat. |
| A4 | Holidays: the brief's leave rules need working days; I use weekend Sat–Sun only. Public holidays are out of the thin slice (documented as not done). | Quota math may over-count a holiday as a working day; acceptable for the demo, listed in README. |
| A5 | Payslip is a printable HTML page (print-friendly CSS; browser Print → PDF). No PDF library. JSON variant only if trivial. | Fine per scope. |

## 5. Config (env vars — `.env.example` lists names, never values)

| Var | Meaning |
|---|---|
| `DATABASE_URL` | Neon Postgres; SQLite file for local dev/tests. |
| `JWT_SECRET` | HS256 signing secret. Required; fail fast if missing. |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | First-run Admin bootstrap. |
| `COMPANY_NAME` | Default company name at first run. |
| `AI_API_KEY` | OpenAI key (mapped to the SDK's `OPENAI_API_KEY` in config). |
| `AI_MODEL` | Model name. |
| `CORS_ORIGINS` | Not needed (same-origin page). Kept only if a separate frontend appears. |
| `RATE_LIMIT_PER_HOUR` | Default 20. |
| `AI_TIMEOUT_SECONDS` | Default 15. |
| `MAX_TURNS` | Default small (5). |

## 6. Errors, limits, logging

- Exceptions: `AuthError` (401), `ForbiddenError` (403), `NotFound` (404),
  `Conflict` (409), `RuleViolation` (422), `RateLimitError` (429),
  `AiTimeoutError` (504). Mapped in one place; client sees
  `{"error": {"code", "message"}}`, never a stack trace.
- Structured JSON logs: request id, endpoint, role, status, latency, tool
  names, token usage. Same facts into `ai_logs`. Never log tokens, keys, full
  prompts, or raw salary values.
- Every AI response: `"label": "AI-generated"`.

## 7. Testing strategy

- Tests with each task, not at the end. SQLite in-memory; fixtures create
  users/employees in tests only. Real-LLM tests sit behind a pytest marker
  `llm` and are excluded by default (`addopts = -m 'not llm'`); they run only
  with `pytest -m llm`. All other tests run without any API key.
- Rule tests: late/half-day/409, leave overlap + balance 422 + working days,
  payroll math + tax slab + proration, role/scope 401/403, allowlist,
  `resolve_dates`, number grounding, rate limiter.
- `eval/run_eval.py`: brief's judge questions incl. Roman Urdu and one
  prompt-injection case, PASS/FAIL.
- Final pass: `ruff`, `bandit`, `pip-audit`, `gitleaks`.

## 8. Future work (documented, not built)

Public holidays + attendance corrections, CSV, announcements, notifications,
payslip PDF, audit log, camera attendance, Redis rate limit, streaming chat,
semantic cache.
