# spec.md — HCM Lite (solo build: minimal HR backend + AI Assistant M8)

One FastAPI app in the repo root. I am building alone: a **minimal backend**
(thin slice, only what the AI and the 5-minute demo need) plus the **AI
Assistant (M8)**. The app starts **empty** — every number comes from what users
do in the app. No seeded or dummy data in the real app (test fixtures may create
data in tests only).

## 1. The demo story this app must support (5-minute script from the brief)

1. Fresh install: Admin account is created on first run (`ADMIN_EMAIL` /
   `ADMIN_PASSWORD` env vars, or a first-run setup form).
2. Admin creates a department; default leave types exist (brief rules).
3. HR registers two or three employees (each gets a login with a temporary
   password). One signs in, changes the password, checks in.
4. Employee types a leave request in plain words, confirms the pre-filled form;
   HR approves it.
5. HR opens the dashboard, clicks Summarize, asks the assistant who is on leave;
   runs payroll; Admin finalizes it.
6. Employee downloads (views) the payslip and asks for a colleague's salary
   (refused). Admin sees the numbers match the dashboard.

## 2. User stories and acceptance criteria

### Admin (company level)

| # | Story | Acceptance |
|---|---|---|
| A1 | First run creates my Admin account and the company. | Second first-run attempt is rejected (4xx); admin can log in. |
| A2 | I create departments; default leave types (annual 14, sick 8, casual 10, unpaid unlimited) exist from first run. | CRUD works for departments; leave type quotas match the brief. |
| A3 | I create HR logins. | HR can sign in with the temp password and must change it. |
| A4 | I ask "How many active employees are in {department}?" | AI answer matches the dashboard KPI. |
| A5 | I click Summarize and get 3–5 bullets. | Every number in the bullets exists in the KPI JSON I sent. |
| A6 | I finalize the monthly payroll. | After finalize, the run is locked (no edits, re-run rejected). |

### HR (people operations)

| # | Story | Acceptance |
|---|---|---|
| H1 | I register an employee with job details and salary; the employee gets a login. | Temporary password returned once; employee must change it at first sign-in. |
| H2 | I search the employee directory. | Server-side search by name/code; results scoped to my role. |
| H3 | I see the daily attendance board. | Present / late / absent for a date, from real records only. |
| H4 | I approve or reject a leave request with a comment. | Approved leave reduces balance; rejected does not; only pending can be decided. |
| H5 | I create the monthly payroll draft. | Gross = 1.5 × basic; deductions and tax slab per the brief; joiners prorated. |
| H6 | I ask "Who came late most often this month?" and "What is this month's attendance rate?" | Answers match the dashboard numbers. |

### Employee (self-service)

| # | Story | Acceptance |
|---|---|---|
| E1 | I check in and check out on the web. | Server stamps the time. Second check-in same day → 409. Check-in after 09:15 → late. Worked < 5 h → half day. |
| E2 | I apply for leave and see my balance. | Working days only (Sat–Sun skipped); overlap or over-balance → 422. |
| E3 | I type "I need next Monday and Tuesday off for my sister's wedding" and get a pre-filled draft. | Draft `{type, start, end, reason}` with correct ISO dates; type `casual`. Nothing is saved until I confirm. |
| E4 | I ask "How many sick leaves do I have left?" | Correct own balance after approved leaves. |
| E5 | I ask for a colleague's salary. | Polite refusal. I have no tool that can fetch it. |
| E6 | I view my own payslip for a month. | Only my own; another employee's id → 403. |

### All roles (AI + platform)

| # | Story | Acceptance |
|---|---|---|
| R1 | I chat in English, Urdu, or Roman Urdu. | Answer comes back in my language. |
| R2 | Someone hides a prompt injection in tool data. | Ignored; tool output is wrapped in delimiters marked as data. |
| R3 | The LLM times out or fails. | Friendly message within 15 s; service never crashes or leaks a stack trace. |
| R4 | I send more than ~20 AI requests in an hour. | HTTP 429 with a clear message. |
| R5 | — | Every AI call logged in `ai_logs` (no salaries, tokens, or full prompts). Every AI response carries `"label": "AI-generated"`. |
| R6 | Role checks are server-side on every route and every tool. | Employee token cannot read another employee's data or company KPIs (403). |

## 3. Endpoints

One error shape everywhere: `{"error": {"code": "...", "message": "..."}}`.
Every route checks role AND data scope server-side.

### Health / page
- `GET /health` — no auth, `{"status": "ok"}`.
- `GET /` — serves the single web page (static HTML + Tailwind CDN + small JS).

### Auth
- `POST /setup` — first run only: company name + Admin account (uses
  `ADMIN_EMAIL` / `ADMIN_PASSWORD` env when set). Also creates default leave
  types from the brief rules.
- `POST /auth/login` — `{email, password}` → JWT. First sign-in with a
  temporary password forces a change.
- `POST /auth/change-password`.
- `GET /me` — my profile + role + employee link.

### Organization (thin)
- `POST /departments`, `GET /departments` — Admin manages; all roles view.

### Employees
- `POST /employees` — HR/Admin. Creates employee + login (temporary password).
- `GET /employees?search=&department=` — directory search (Admin/HR). Employee
  gets only their own profile via `GET /me`.

### Attendance
- `POST /attendance/check-in` — server stamps time; second same-day → 409;
  after 09:15 → late.
- `POST /attendance/check-out` — missing checkout rule; < 5 h → half day.
- `GET /attendance/me` — my records.
- `GET /attendance?date=` — daily board (Admin/HR).

### Leave
- `POST /leaves` — apply. Working days only; overlap or over-balance → 422.
- `GET /leaves/balance` — my balance per leave type.
- `GET /leaves/pending` — approval inbox (HR/Admin).
- `POST /leaves/{id}/approve` and `POST /leaves/{id}/reject` — HR/Admin, with
  comment. Employee → 403.

### Payroll
- `POST /payroll/runs` — HR creates the monthly draft (computes all lines).
- `POST /payroll/runs/{id}/finalize` — Admin only; locks the run.
- `GET /payroll/summary?month=` — totals (Admin/HR).
- `GET /payroll/me?month=` — my own payslip as a **printable HTML page**
  (print-friendly CSS; browser Print → PDF).

### Analytics
- `GET /analytics/kpis?from=&to=` — role-scoped KPIs: Admin/HR company (and
  department filter), Employee personal (hours, late count, leave left).

### AI (M8)
- `POST /ai/chat` — all roles. Role-based tool allowlist. Policy Q&A from
  `app/policy/policy.md`.
- `POST /ai/dashboard-summary` — Admin/HR. KPI JSON in, 3–5 number-grounded
  bullets out.
- `POST /ai/smart-leave` — Employee. Plain sentence → validated `LeaveDraft`
  or `{"fallback": true}`. Never saves.

## 4. Business rules encoded (from the brief, section 3)

- Late after 09:15 (grace 15 min from 09:00); half day under 5 h; weekend
  Sat–Sun; one attendance record per employee per day (second → 409).
- Leave: working days only; quotas annual 14, sick 8, casual 10, unpaid
  unlimited; overlap or over-balance → 422.
- Payroll: gross = 1.5 × basic (HRA 40%, medical 10% of basic); per-day =
  gross ÷ working days; deduct absent + unpaid + 0.5 × half days; joiners
  prorated; tax slab on gross × 12 (0–600k 0%; 30k+15% to 2.4M; 210k+25% to
  3.6M; 510k+35% above); Admin finalizes; finalized is locked.

## 5. Out of scope (documented, not built)

CSV import/export, attendance corrections, announcements, notifications,
payslip PDF, audit log (but see the optional Task 12 in tasks.md), camera
attendance, mobile app. Listed as "not done" in the README.
