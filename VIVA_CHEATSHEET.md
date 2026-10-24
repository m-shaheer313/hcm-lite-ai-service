# VIVA CHEATSHEET — [PROJECT NAME]

> **How to use (delete this note later):**
> - Har step complete hone ke **foran baad** (3-5 min) uska section bharo. Raat ke end par nahi.
> - Sirf wo likho jo **tum ne actually kiya**. Jo nahi kiya wo "Future Work" mein likho.
> - Simple words. Aisa likho jaise kisi non-tech dost ko samjha rahe ho.
> - `[ ]` wali jagah bharni hai. Hints (italic lines) delete kar do.

---

## 0. Project at a Glance

| | |
|---|---|
| **Project name** | HCM Lite (solo build: minimal HR backend + AI Assistant M8) |
| **One line** | An HR team has no easy way to ask questions about their own data. My app stores real attendance, leave, and payroll data, and an AI assistant answers questions from that data using tools, so that every AI answer matches the dashboard and each user only sees their own allowed data. |
| **Who is the user?** | Admin, HR, and Employees of a small company |
| **Problem in simple words** | HR data lives in tables; normal people want to ask questions in plain words (English / Urdu) and get correct, allowed answers. |
| **My solution in simple words** | One web app: a small HR backend (check-in, leave, payroll) + an AI assistant whose tools call the same code as the normal screens, so numbers always match. |
| **Hackathon track/theme** | Saylani Hackathon — HCM Lite, module M8 (AI Assistant) + thin backend |

### Tech Stack (what I used and why, one line each)

| Technology | Why I used it |
|---|---|
| OpenAI Agents SDK | Gives tools, structured output, guardrails, max_turns, and tracing in one small package. |
| Pydantic | Checks every input and output shape; bad data is rejected in code, not by hope. |
| FastAPI | Async Python web framework; the whole app (backend + AI + one page) lives in it. |
| SQLModel + Postgres (Neon) / SQLite | Real database for deployed demo; SQLite makes local dev and tests fast with no network. |
| Static HTML + Tailwind CDN | One demo page with no build step and no second deploy. |
| Deploy platform | Render free tier (Dockerfile). |

### Architecture (simple flow)

```
Browser (one page: login, role menus, AI chat panel)
   → FastAPI routes → services (all business rules + permission checks)
   → repositories (SQLModel) → Neon Postgres
AI: Agent → tools → the SAME service functions (never the DB directly)
   → answer carries "AI-generated" label
```

---

## Project Files Map (every file and folder explained)

> *Jab bhi nayi file ya folder banao, yahan ek row add karo. Viva mein judge kisi bhi file par ungli rakh sakta hai.*

### Folder tree

```
hcm-lite-ai-service/
├── app/            the application (config, schemas, main so far)
├── tests/          pytest tests (SQLite, no real API keys)
├── docs/           AI contract and notes (filled in later tasks)
├── eval/           eval/run_eval.py with the judge questions (later task)
├── .env.example    key names with no values
├── pyproject.toml  name, Python pin, dependencies
└── uv.lock         exact locked versions
```

### What each file/folder does

| File / Folder | What is it? | Why does it exist? | What is inside? | VIVA line |
|---|---|---|---|---|
| `pyproject.toml` | Project's ID card | Lists name, Python version, and libraries | Pinned to Python 3.13; deps: fastapi, sqlmodel, openai-agents, etc. | "It tells uv which libraries my project needs." |
| `uv.lock` | Exact version record | Makes sure every machine installs the same versions | Auto-generated, do not edit | "It locks versions so the project works the same everywhere." |
| `.python-version` | Python version pin | Stops "works on my machine" Python problems | `3.13` | "Everyone and Render use Python 3.13." |
| `.env` | Secret keys file | Keeps API keys out of the code | Real values, git-ignored | "Secrets stay here and never go to GitHub." |
| `.env.example` | Empty copy of `.env` | Shows which keys are needed, without real values | Key names only | "It tells others what to fill in." |
| `.gitignore` | "Do not upload" list | Stops `.env`, `.mimosa/`, local DBs going to GitHub | File and folder names | "It protects my secrets." |
| `README.md` | Project front page | Explains what it is and how to run it | Filled in Task 11 | "First thing a new person reads." |
| `spec.md` / `plan.md` / `tasks.md` | Planning documents | Plan before code (Spec-Driven Development) | User stories, architecture, 12 tasks | "I wrote the plan before the code." |
| `app/main.py` | Entry point | The file that starts the FastAPI app | App + lifespan + `/health` | "This is where the app starts." |
| `app/config.py` | Settings | One place for env names and limits | pydantic-settings; fails fast if required vars are missing | "Change settings here, not all over the code." |
| `app/schemas.py` | Data shapes | Fixed format for API bodies | Pydantic models (HealthResponse so far) | "It forces answers into a clean format." |
| `app/models.py` | Database tables | One SQLModel class per table | users, employees, departments, leave_types, leave_requests, attendance, payroll_runs, payslips, ai_logs, settings, holidays | "The rules live in the database: one attendance per day, one payroll per month, money as integer paisa." |
| `app/db.py` | Database connection | Builds the engine and creates tables | `make_engine`, `init_db` (create_all, no Alembic), session dependency | "Postgres on Render, SQLite in tests — same code." |
| `tests/conftest.py` | Test setup | Gives every test a fresh in-memory SQLite DB | `engine` and `session` fixtures; dummy secret only | "Each test gets a clean database in memory." |
| `tests/` | Test files | Check that things still work | SQLite + dummy secret in conftest; no real keys | "It catches bugs before the demo." |
| `docs/` | Notes folder | Contract and design notes | Filled in later tasks | "Where I keep my design promises." |
| `eval/` | Eval scripts | Judge questions as PASS/FAIL | Filled in Task 10 | "It checks the AI answers like a judge." |

*Jo file tumhare project mein nahi hai wo row delete kar do. Jo extra hai wo add kar do.*

---

## STEP TEMPLATE (copy this for every step)

## Step [N]: [Heading — e.g. "Adding a Guardrail"]

**What is it?**
*1-2 simple lines. Jargon ho to bracket mein samjhao.*
[ ]

**Simple analogy (for non-tech people)**
*Roz marra ki misaal. Example: Guardrail = mall ka security gate.*
[ ]

**Why did I use it?**
*Ye na hota to kya masla hota?*
[ ]

**How did I do it?**
*3-5 chhote steps. Zaroorat ho to ek chhota code snippet.*
1. [ ]
2. [ ]
3. [ ]

**Problem it solves**
[ ]

**Key points to remember**
- [ ] *(1 line definition)*
- [ ] *(1 important detail)*
- [ ] *(1 limitation / trade-off)*

**VIVA answer (30 seconds)**
> [Definition] → [Why I used it] → [What happened in my project]

---

## EXAMPLE (delete after reading) — Step 6: Output Guardrail

**What is it?**
A safety check that looks at the agent's final answer before the user sees it.

**Simple analogy**
Like a bill check at the mall exit. Even if you are inside, someone checks before you leave.

**Why did I use it?**
The AI can sometimes say things it should not. Without a check, a mistake goes straight to the user.

**How did I do it?**
1. Wrote a small function that checks the answer text.
2. Attached it to the agent as an output guardrail.
3. If the check fails, the system stops and shows a clear message.

**Problem it solves**
Stops the agent from leaking solved practice answers to students.

**Key points to remember**
- Input guardrail checks before the work, output guardrail checks after.
- Costs a little extra time on every request.
- Simple rule-based checks are more reliable than asking another AI.

**VIVA answer (30 seconds)**
> A guardrail is a safety check on the agent. I used an output guardrail because the AI can make mistakes, and I did not want it to leak solved answers. In my project, if the answer contains a solved practice question, the guardrail blocks it.

---

## STEPS OF MY PROJECT (fill in build order)

*Neeche ke steps copy-paste karke bharo. Jo step apne project mein nahi hai wo delete kar do.*

## Step 1–2: Planning (spec / plan / tasks) and Project Setup

**What is it?**
Planning docs written before code (spec = what, plan = how and why, tasks = small ordered steps), then a runnable FastAPI skeleton: pinned Python, dependencies, settings from env, and a `/health` endpoint.

**Simple analogy (for non-tech people)**
Building a house: first the drawing (spec), the materials list (plan), and the work order (tasks). `/health` is like the doorbell — a tiny button to prove the house is alive.

**Why did I use it?**
It is a 9-hour night. Without a plan I would guess mid-build; with tasks I always know the next small step. Failing fast on missing settings stops the classic "works here, crashes on Render" bug.

**How did I do it?**
1. Wrote `spec.md`, `plan.md`, `tasks.md` and got approval before any code.
2. `uv python pin 3.13`, renamed the project, added dependencies with `uv add` (locked in `uv.lock`).
3. Made `app/config.py` with pydantic-settings — the app refuses to start if `DATABASE_URL` or `JWT_SECRET` is missing.
4. Made `app/main.py` with `GET /health`, plus two tests (health works; missing env var fails startup).
5. Committed the original scaffold, then the setup, then the docs.

**Problem it solves**
No surprises at deploy time: wrong or missing settings crash at startup, not during the demo. Every machine and Render use the same Python and library versions.

**Key points to remember**
- Spec-driven development: plan first, code second; every task has an acceptance check.
- Fail fast: required settings are checked at startup, with a clear message.
- `llm` pytest marker: tests never call the real AI model by default (`pytest -m llm` only).
- Python pinned to 3.13 (`>=3.13,<3.14`) for stable library support.

**VIVA answer (30 seconds)**
> Before coding I wrote a spec, a plan, and a task list, because in a 9-hour hackathon guessing is expensive. Then I set up the project with uv, pinned Python 3.13, and built the smallest possible FastAPI app: one `/health` endpoint and settings that come only from environment variables — the app refuses to start if a required one is missing, so deployment problems appear immediately, not during the demo.

## Step 2b: Data Models (Task 2)

**What is it?**
The database tables of the app, written as SQLModel classes: users, employees, departments, leave types, leave requests, attendance, payroll runs, payslips, AI logs, settings, holidays.

**Simple analogy (for non-tech people)**
It is the set of registers (straight, clean ledgers) an office keeps: one attendance register with exactly one line per person per day, one payroll register with one sheet per month.

**Why did I use it?**
The whole app depends on these shapes. Putting the hard rules in the database itself (not only in Python) means even a bug cannot create two attendance rows for one day or two payroll runs for one month.

**How did I do it?**
1. Wrote one SQLModel class per table in `app/models.py`.
2. Money is stored as **integer paisa** (1 PKR = 100 paisa) — no floats, so amounts are always exact.
3. Added DB constraints: unique (employee, day) on attendance (backs the 409), unique employee code and user email, one payroll run per month, and leave `start <= end` as a CHECK.
4. `app/db.py` builds the engine and runs `create_all` (no Alembic migrations).
5. Tests use in-memory SQLite; a smoke check proved the same code creates tables and inserts rows on a real file DB (Postgres-compatible types only).

**Problem it solves**
Data integrity with zero trust in code paths: the 409 (second check-in) and one-run-per-month rules are enforced by the database, and money can never lose precision.

**Key points to remember**
- SQLModel table names are lowercase singular (`Employee` → `employee`); foreign keys must match that exactly.
- Money = integer minor units (`*_minor`), never float.
- Tests create data only in tests; the real app starts empty (no seed data).
- `create_all` only creates missing tables — simple, fine for a hackathon, no migrations.

**VIVA answer (30 seconds)**
> I defined every table with SQLModel and pushed the business-critical rules into database constraints — for example a unique index on (employee, day) is what physically backs the "second check-in is rejected with 409" rule. All money is stored as integer paisa so there is never a float rounding error, and the same models run on SQLite for tests and Neon Postgres in production.

- [x] Step 1: Spec / Plan (spec.md, plan.md, tasks.md)
- [x] Step 2: Project Setup (uv, .env, API key test)
- [x] Step 2b: Data Models (Task 2)
- [ ] Step 3: First Agent (instructions + model)
- [ ] Step 4: Tools (what actions the agent can do)
- [ ] Step 5: Structured Output (Pydantic)
- [ ] Step 6: Guardrails (input / output)
- [ ] Step 7: Handoffs / Multi-agent (Router / Supervisor)
- [ ] Step 8: Memory (session / long-term)
- [ ] Step 9: Tracing / Hooks (observability)
- [ ] Step 10: UI (Chainlit / Next.js)
- [ ] Step 11: Deployment (Docker / Render / HF Spaces / Vercel)

---

## Likely Judge Questions (fill your own answers)

| Question | My answer (2-3 lines) |
|---|---|
| Why this problem? Who is the user? | [ ] |
| Why an agent, not a simple LLM call? | [ ] |
| Why this framework / model? | [ ] |
| How do you stop wrong or harmful answers? | [ ] |
| Why structured output? | [ ] |
| Handoff vs tool: what is the difference? | [ ] |
| What is MCP / RAG / memory (if used or not)? | [ ] |
| What if 10x more users come? | [ ] |
| What would you add with more time? | [ ] |

---

## Limitations (be honest, judges like it)

1. [ ]
2. [ ]
3. [ ]

## Future Work (what I did NOT build, but would)

- [ ]
- [ ]

---

## 2-Minute Demo Script

1. **Problem (15 sec):** [ ]
2. **Live demo, happy path (60 sec):** [ ]
3. **One "wow" feature (30 sec):** [ ]
4. **Tech and why (15 sec):** [ ]

*Backup: demo video saved at [ ]*

---

## Glossary (simple words)

| Word | Simple meaning |
|---|---|
| Agent | An AI that can think and also take actions using tools |
| Tool | A function the agent can ask to run |
| Handoff | One agent passes the job to a specialist agent |
| Guardrail | A safety check on input or output |
| Structured output | Answer in a fixed format that code can use |
| MCP | A standard way to connect AI to tools and data |
| RAG | AI looks up your documents first, then answers |
| Memory | How the agent remembers past messages |
| Tracing | A record of what the agent did, step by step |