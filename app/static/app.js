/* HCM Lite web page. Plain JS, no build step, no CDN.
   Security rule: every dynamic string is rendered with textContent;
   the HTML-injection property is never used (a test checks this). */
"use strict";

const state = { token: sessionStorage.getItem("token") || "", me: null };

/* ---------- tiny DOM helpers (textContent only) ---------- */
function el(tag, text, cls) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = text;
  if (cls) node.className = cls;
  return node;
}
function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
function msg(parent, text, kind) {
  const box = el("div", text, "msg " + (kind || "err"));
  parent.prepend(box);
  return box;
}

/* ---------- API helper with friendly errors and a client timeout ---------- */
async function api(path, options) {
  const opts = Object.assign({ method: "GET", headers: {} }, options || {});
  if (state.token) opts.headers["Authorization"] = "Bearer " + state.token;
  if (opts.body) opts.headers["Content-Type"] = "application/json";
  const controller = new AbortController();
  opts.signal = controller.signal;
  const timer = setTimeout(() => controller.abort(), 25000);
  let response;
  try {
    response = await fetch(path, opts);
  } catch (err) {
    throw new Error("The request took too long or failed. Please try again.");
  } finally {
    clearTimeout(timer);
  }
  let body = {};
  try { body = await response.json(); } catch (e) { /* non-JSON (e.g. payslip HTML) */ }
  if (!response.ok) {
    const detail = body && body.error ? body.error.message : "";
    if (response.status === 401) throw new Error(detail || "Please log in again.");
    if (response.status === 403) throw new Error(detail || "Your role cannot do this.");
    if (response.status === 429) throw new Error(detail || "Too many AI requests this hour. Try later.");
    throw new Error(detail || "Request failed (" + response.status + ").");
  }
  return body;
}

/* ---------- views ---------- */
const main = document.getElementById("main");
const menu = document.getElementById("menu");

function showLogin() {
  clear(main); menu.style.display = "none";
  const card = el("div", null, "card");
  card.appendChild(el("h2", "Log in"));
  const email = el("input"); email.type = "email"; email.placeholder = "Email";
  const pass = el("input"); pass.type = "password"; pass.placeholder = "Password";
  const btn = el("button", "Log in", "primary"); btn.type = "submit";
  const form = el("form");
  form.append(el("label", "Email"), email, el("label", "Password"), pass, btn);
  card.appendChild(form);
  main.appendChild(card);
  form.onsubmit = async (event) => {
    event.preventDefault();
    try {
      const out = await api("/auth/login", {
        method: "POST", body: JSON.stringify({ email: email.value.trim(), password: pass.value })
      });
      state.token = out.access_token;
      sessionStorage.setItem("token", state.token);
      await afterLogin();
    } catch (err) { msg(card, err.message); }
  };
}

function showSetup() {
  clear(main); menu.style.display = "none";
  const card = el("div", null, "card");
  card.appendChild(el("h2", "First-run setup"));
  card.appendChild(el("p", "Create the Admin account. This works only once.", "muted"));
  const company = el("input"); company.placeholder = "Company name";
  const email = el("input"); email.type = "email"; email.placeholder = "Admin email";
  const pass = el("input"); pass.type = "password"; pass.placeholder = "Password (min 8 chars)";
  const btn = el("button", "Create Admin", "primary");
  const form = el("form");
  form.append(el("label", "Company"), company, el("label", "Email"), email, el("label", "Password"), pass, btn);
  card.appendChild(form);
  main.appendChild(card);
  form.onsubmit = async (event) => {
    event.preventDefault();
    try {
      const out = await api("/setup", {
        method: "POST",
        body: JSON.stringify({ company_name: company.value.trim(), email: email.value.trim(), password: pass.value })
      });
      state.token = out.access_token;
      sessionStorage.setItem("token", state.token);
      await afterLogin();
    } catch (err) { msg(card, err.message); }
  };
}

function showChangePassword() {
  clear(main); menu.style.display = "none";
  const card = el("div", null, "card");
  card.appendChild(el("h2", "Change your temporary password"));
  const oldPass = el("input"); oldPass.type = "password"; oldPass.placeholder = "Temporary password";
  const newPass = el("input"); newPass.type = "password"; newPass.placeholder = "New password (min 8 chars)";
  const btn = el("button", "Save", "primary");
  const form = el("form");
  form.append(el("label", "Old password"), oldPass, el("label", "New password"), newPass, btn);
  card.appendChild(form);
  main.appendChild(card);
  form.onsubmit = async (event) => {
    event.preventDefault();
    try {
      await api("/auth/change-password", {
        method: "POST",
        body: JSON.stringify({ old_password: oldPass.value, new_password: newPass.value })
      });
      await afterLogin();
    } catch (err) { msg(card, err.message); }
  };
}

async function afterLogin() {
  state.me = await api("/me");
  document.getElementById("brand").textContent = state.me.company_name || "HCM Lite";
  document.getElementById("who").textContent = state.me.email + " · " + state.me.role;
  document.getElementById("logoutBtn").style.display = "";
  if (state.me.must_change_password) return showChangePassword();
  buildMenu(state.me.role);
  const first = menu.querySelector("button");
  if (first) first.click();
}

function logout() {
  state.token = ""; state.me = null;
  sessionStorage.removeItem("token");
  showLogin();
}

/* ---------- panels ---------- */
function panel(title) {
  const card = el("div", null, "card panel");
  card.appendChild(el("h2", title));
  return card;
}

function buildMenu(role) {
  clear(menu); menu.style.display = "";
  const items = [];
  items.push(["Chat", chatPanel]);
  items.push(["Smart leave", smartLeavePanel]);
  if (role === "admin" || role === "hr") items.push(["KPIs & Summary", kpiPanel]);
  if (role === "admin") {
    items.push(["Departments", departmentPanel]);
    items.push(["Create HR login", hrLoginPanel]);
    items.push(["Finalize payroll", finalizePanel]);
  }
  if (role === "hr") {
    items.push(["Register employee", registerPanel]);
    items.push(["Leave approvals", approvalsPanel]);
    items.push(["Attendance board", boardPanel]);
    items.push(["Payroll draft", draftPanel]);
  }
  if (role === "employee") {
    items.push(["My attendance", myAttendancePanel]);
    items.push(["My leave", myLeavePanel]);
    items.push(["My payslip", payslipPanel]);
  }
  items.forEach(([label, builder], index) => {
    const btn = el("button", label, "small" + (index === 0 ? " active" : ""));
    btn.type = "button";
    btn.onclick = () => {
      menu.querySelectorAll("button").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      main.querySelectorAll(".panel").forEach((p) => p.classList.remove("show"));
      const existing = main.querySelector("#panel-" + label.replace(/\W+/g, "-"));
      if (existing) existing.classList.add("show");
      else { const p = builder(); p.id = "panel-" + label.replace(/\W+/g, "-"); main.appendChild(p); }
    };
    menu.appendChild(btn);
  });
}

/* --- AI chat --- */
function chatPanel() {
  const card = panel("AI Assistant");
  const log = el("div", null, "chat");
  const note = el("div", null, "muted");
  note.textContent = "Ask in English, Urdu, or Roman Urdu. Numbers come from live data.";
  const input = el("input"); input.placeholder = "Ask about attendance, leave, payroll…";
  const btn = el("button", "Send", "primary"); btn.type = "button";
  btn.onclick = async () => {
    const question = input.value.trim();
    if (!question) return;
    input.value = "";
    log.appendChild(el("div", question, "bubble you"));
    const wait = el("div", "Thinking…", "bubble ai muted");
    log.appendChild(wait); log.scrollTop = log.scrollHeight;
    try {
      const out = await api("/ai/chat", { method: "POST", body: JSON.stringify({ message: question }) });
      wait.remove();
      const answer = el("div", null, "bubble ai");
      answer.appendChild(document.createTextNode(out.answer + " "));
      answer.appendChild(el("span", "AI-generated", "badge"));
      log.appendChild(answer);
    } catch (err) {
      wait.remove();
      log.appendChild(el("div", err.message, "bubble ai"));
    }
    log.scrollTop = log.scrollHeight;
  };
  input.onkeydown = (e) => { if (e.key === "Enter") btn.click(); };
  card.append(note, log, input, btn);
  return card;
}

/* --- Smart leave --- */
function smartLeavePanel() {
  const card = panel("Smart leave");
  const note = el("p", "Type a sentence like: I need next Monday and Tuesday off for my sister's wedding. Review the draft, then apply yourself.", "muted");
  const text = el("textarea"); text.placeholder = "Your leave sentence (English or Roman Urdu)";
  const btn = el("button", "Draft my leave", "primary"); btn.type = "button";
  const result = el("div");
  card.append(note, text, btn, result);
  btn.onclick = async () => {
    clear(result);
    const wait = msg(result, "Thinking…", "ok");
    try {
      const out = await api("/ai/smart-leave", { method: "POST", body: JSON.stringify({ message: text.value }) });
      wait.remove();
      const line = el("div");
      line.appendChild(el("span", "AI-generated", "badge"));
      if (out.fallback || !out.draft) {
        line.appendChild(document.createTextNode(" I could not draft this. Please use the leave form instead."));
        result.appendChild(line);
        return;
      }
      line.appendChild(document.createTextNode(
        " Draft: " + out.draft.leave_type + " from " + out.draft.start + " to " + out.draft.end +
        " — " + out.draft.reason));
      result.appendChild(line);
      if (state.me.role === "employee") {
        const apply = el("button", "Apply this draft", "primary"); apply.type = "button";
        apply.onclick = async () => {
          try {
            await api("/leaves", {
              method: "POST",
              body: JSON.stringify({
                leave_type_code: out.draft.leave_type,
                start_day: out.draft.start,
                end_day: out.draft.end,
                reason: out.draft.reason
              })
            });
            msg(result, "Leave request sent for approval.", "ok");
            apply.remove();
          } catch (err) { msg(result, err.message); }
        };
        result.appendChild(apply);
      }
    } catch (err) { wait.remove(); msg(result, err.message); }
  };
  return card;
}

/* --- KPIs + Summarize --- */
async function departmentOptions(select) {
  const departments = await api("/departments");
  departments.forEach((d) => {
    const option = el("option", d.name);
    option.value = d.id;
    select.appendChild(option);
  });
}

function kpiPanel() {
  const card = panel("KPIs & AI summary");
  const row = el("div", null, "row");
  const startBox = el("div"); const endBox = el("div"); const deptBox = el("div");
  const start = el("input"); start.type = "date";
  const end = el("input"); end.type = "date";
  const dept = el("select");
  dept.appendChild(el("option", "All departments")).value = "";
  startBox.append(el("label", "From"), start);
  endBox.append(el("label", "To"), end);
  deptBox.append(el("label", "Department"), dept);
  row.append(startBox, endBox, deptBox);
  const load = el("button", "Show KPIs", "primary"); load.type = "button";
  const summarize = el("button", "Summarize", "primary"); summarize.type = "button";
  const out = el("div");
  card.append(row, load, summarize, out);
  departmentOptions(dept).catch(() => {});
  async function query() {
    const params = new URLSearchParams();
    if (start.value) params.set("start", start.value);
    if (end.value) params.set("end", end.value);
    if (dept.value) params.set("department_id", dept.value);
    return params;
  }
  load.onclick = async () => {
    clear(out);
    try {
      const data = await api("/analytics/kpis?" + (await query()).toString());
      const table = el("table");
      Object.entries(data.kpis).forEach(([key, value]) => {
        table.appendChild(el("tr")).append(el("td", key), el("td", String(value)));
      });
      out.appendChild(table);
    } catch (err) { msg(out, err.message); }
  };
  summarize.onclick = async () => {
    clear(out);
    const wait = msg(out, "Summarizing…", "ok");
    try {
      const params = await query();
      const data = await api("/ai/dashboard-summary?" + params.toString(), { method: "POST" });
      wait.remove();
      const head = el("div");
      head.appendChild(el("span", "AI-generated", "badge"));
      if (data.fallback) head.appendChild(document.createTextNode(" (built from live numbers, writer skipped)"));
      out.appendChild(head);
      data.summary.forEach((line) => out.appendChild(el("div", "• " + line)));
    } catch (err) { wait.remove(); msg(out, err.message); }
  };
  return card;
}

/* --- Admin: departments, HR login, finalize --- */
function departmentPanel() {
  const card = panel("Departments");
  const name = el("input"); name.placeholder = "Department name";
  const btn = el("button", "Create", "primary"); btn.type = "button";
  const list = el("div");
  card.append(el("label", "New department"), name, btn, list);
  async function refresh() {
    clear(list);
    try { (await api("/departments")).forEach((d) => list.appendChild(el("div", "• " + d.name))); }
    catch (err) { msg(list, err.message); }
  }
  btn.onclick = async () => {
    try { await api("/departments", { method: "POST", body: JSON.stringify({ name: name.value.trim() }) }); name.value = ""; refresh(); }
    catch (err) { msg(card, err.message); }
  };
  refresh();
  return card;
}

function hrLoginPanel() {
  const card = panel("Create HR login");
  const email = el("input"); email.type = "email"; email.placeholder = "hr@company.com";
  const btn = el("button", "Create", "primary"); btn.type = "button";
  const out = el("div");
  card.append(el("label", "HR email"), email, btn, out);
  btn.onclick = async () => {
    clear(out);
    try {
      const made = await api("/users", { method: "POST", body: JSON.stringify({ email: email.value.trim() }) });
      const once = el("div", null, "msg ok");
      once.appendChild(document.createTextNode("Temporary password (shown once): " + made.temporary_password));
      out.appendChild(once);
    } catch (err) { msg(out, err.message); }
  };
  return card;
}

function finalizePanel() {
  const card = panel("Finalize payroll");
  const month = el("input"); month.placeholder = "YYYY-MM";
  const check = el("button", "Check status", "small"); check.type = "button";
  const btn = el("button", "Finalize", "primary"); btn.style.display = "none"; btn.type = "button";
  const out = el("div");
  card.append(el("label", "Month"), month, check, btn, out);
  check.onclick = async () => {
    clear(out); btn.style.display = "none";
    try {
      const s = await api("/payroll/summary?month=" + month.value.trim());
      out.appendChild(el("div", "Status: " + s.status + " · employees " + s.employee_count +
        " · net PKR " + (s.net_minor / 100).toFixed(2)));
      if (s.status === "draft") { btn.style.display = ""; btn.dataset.runId = s.id; }
    } catch (err) { msg(out, err.message); }
  };
  btn.onclick = async () => {
    try {
      const done = await api("/payroll/runs/" + btn.dataset.runId + "/finalize", { method: "POST", body: "{}" });
      msg(out, "Finalized and locked: " + done.month, "ok");
      btn.style.display = "none";
    } catch (err) { msg(out, err.message); }
  };
  return card;
}

/* --- HR: register employee, approvals, board, draft --- */
function registerPanel() {
  const card = panel("Register employee");
  const fields = {};
  ["full_name", "email", "designation", "join_date"].forEach((key) => {
    const input = el("input");
    if (key === "email") input.type = "email";
    if (key === "join_date") { input.type = "date"; input.value = new Date().toISOString().slice(0, 10); }
    fields[key] = input;
  });
  const salary = el("input"); salary.type = "number"; salary.min = "1"; salary.placeholder = "e.g. 80000";
  const dept = el("select");
  const btn = el("button", "Register", "primary"); btn.type = "button";
  const out = el("div");
  card.append(
    el("label", "Full name"), fields.full_name,
    el("label", "Email (login)"), fields.email,
    el("label", "Designation"), fields.designation,
    el("label", "Join date"), fields.join_date,
    el("label", "Basic salary (PKR per month)"), salary,
    el("label", "Department"), dept, btn, out
  );
  departmentOptions(dept).catch(() => {});
  btn.onclick = async () => {
    clear(out);
    const rupees = Number(salary.value);
    if (!Number.isInteger(rupees) || rupees <= 0) return msg(out, "Salary must be a whole number of rupees.");
    try {
      const made = await api("/employees", {
        method: "POST",
        body: JSON.stringify({
          full_name: fields.full_name.value.trim(),
          email: fields.email.value.trim(),
          designation: fields.designation.value.trim(),
          join_date: fields.join_date.value,
          basic_salary_minor: Math.round(rupees * 100),
          department_id: dept.value ? Number(dept.value) : null
        })
      });
      const once = el("div", null, "msg ok");
      once.appendChild(document.createTextNode(
        "Registered " + made.employee.code + ". Temporary password (shown once): " + made.temporary_password));
      out.appendChild(once);
    } catch (err) { msg(out, err.message); }
  };
  return card;
}

function approvalsPanel() {
  const card = panel("Leave approvals");
  const btn = el("button", "Refresh", "small"); btn.type = "button";
  const list = el("div");
  card.append(btn, list);
  async function refresh() {
    clear(list);
    try {
      const pending = await api("/leaves/pending");
      if (!pending.length) return list.appendChild(el("p", "Nothing pending.", "muted"));
      pending.forEach((item) => {
        const rowEl = el("div");
        rowEl.appendChild(el("div", item.employee_name + " (" + item.employee_code + "): " +
          item.leave_type + " " + item.start_day + " → " + item.end_day +
          " (" + item.working_days + " day(s)) — " + item.reason));
        const approve = el("button", "Approve", "small"); approve.type = "button";
        const reject = el("button", "Reject", "small"); reject.type = "button";
        const done = (text) => { clear(rowEl); rowEl.appendChild(el("div", text, "muted")); };
        approve.onclick = async () => {
          try { await api("/leaves/" + item.id + "/approve", { method: "POST", body: JSON.stringify({ comment: "ok" }) }); done("Approved."); }
          catch (err) { done(err.message); }
        };
        reject.onclick = async () => {
          try { await api("/leaves/" + item.id + "/reject", { method: "POST", body: JSON.stringify({ comment: "no" }) }); done("Rejected."); }
          catch (err) { done(err.message); }
        };
        rowEl.append(approve, reject);
        list.appendChild(rowEl);
      });
    } catch (err) { msg(list, err.message); }
  }
  btn.onclick = refresh;
  refresh();
  return card;
}

function boardPanel() {
  const card = panel("Attendance board");
  const day = el("input"); day.type = "date"; day.value = new Date().toISOString().slice(0, 10);
  const btn = el("button", "Show", "primary"); btn.type = "button";
  const table = el("table");
  card.append(el("label", "Date"), day, btn, table);
  btn.onclick = async () => {
    clear(table);
    try {
      const rows = await api("/attendance?day=" + day.value);
      rows.forEach((row) => table.appendChild(el("tr")).append(
        el("td", row.code), el("td", row.full_name), el("td", row.status)));
    } catch (err) { msg(card, err.message); }
  };
  btn.click();
  return card;
}

function draftPanel() {
  const card = panel("Payroll draft");
  const month = el("input"); month.placeholder = "YYYY-MM";
  const btn = el("button", "Create draft", "primary"); btn.type = "button";
  const out = el("div");
  card.append(el("label", "Month"), month, btn, out);
  btn.onclick = async () => {
    clear(out);
    try {
      await api("/payroll/runs", { method: "POST", body: JSON.stringify({ month: month.value.trim() }) });
      const s = await api("/payroll/summary?month=" + month.value.trim());
      out.appendChild(el("div", "Draft created: " + s.employee_count + " employees · gross PKR " +
        (s.gross_minor / 100).toFixed(2) + " · net PKR " + (s.net_minor / 100).toFixed(2)));
      out.appendChild(el("div", "Admin can finalize it from the Finalize payroll tab.", "muted"));
    } catch (err) { msg(out, err.message); }
  };
  return card;
}

/* --- Employee: attendance, leave, payslip --- */
function myAttendancePanel() {
  const card = panel("My attendance");
  const inBtn = el("button", "Check in", "primary"); inBtn.type = "button";
  const outBtn = el("button", "Check out", "primary"); outBtn.type = "button";
  const status = el("div", "Loading…", "muted");
  card.append(inBtn, outBtn, status);
  async function refresh() {
    const today = new Date().toISOString().slice(0, 10);
    try {
      const rows = await api("/attendance/me?start=" + today + "&end=" + today);
      clear(status);
      if (!rows.length) return status.appendChild(el("div", "No check-in yet today.", "muted"));
      const r = rows[0];
      status.appendChild(el("div", "Today: " + r.status +
        (r.check_out_at ? " (checked out)" : " (working)")));
    } catch (err) { clear(status); status.appendChild(el("div", err.message)); }
  }
  inBtn.onclick = async () => { try { await api("/attendance/check-in", { method: "POST" }); await refresh(); } catch (err) { msg(card, err.message); } };
  outBtn.onclick = async () => { try { await api("/attendance/check-out", { method: "POST" }); await refresh(); } catch (err) { msg(card, err.message); } };
  refresh();
  return card;
}

function myLeavePanel() {
  const card = panel("My leave");
  const balance = el("div");
  const type = el("select");
  const start = el("input"); start.type = "date";
  const end = el("input"); end.type = "date";
  const reason = el("input"); reason.placeholder = "Reason";
  const btn = el("button", "Apply", "primary"); btn.type = "button";
  const out = el("div");
  card.append(balance, el("label", "Leave type"), type, el("label", "From"), start,
    el("label", "To"), end, el("label", "Reason"), reason, btn, out);
  (async () => {
    try {
      const items = await api("/leaves/balance");
      const table = el("table");
      items.forEach((b) => {
        table.appendChild(el("tr")).append(
          el("td", b.name),
          el("td", b.remaining_days === null ? "unlimited" : b.remaining_days + " of " + b.quota_days + " left"));
        const option = el("option", b.name);
        option.value = b.code;
        type.appendChild(option);
      });
      balance.appendChild(table);
    } catch (err) { msg(balance, err.message); }
  })();
  btn.onclick = async () => {
    clear(out);
    try {
      await api("/leaves", {
        method: "POST",
        body: JSON.stringify({
          leave_type_code: type.value, start_day: start.value, end_day: end.value, reason: reason.value.trim()
        })
      });
      msg(out, "Request sent for approval.", "ok");
    } catch (err) { msg(out, err.message); }
  };
  return card;
}

function payslipPanel() {
  const card = panel("My payslip");
  const month = el("input"); month.placeholder = "YYYY-MM";
  const btn = el("button", "View / print", "primary"); btn.type = "button";
  const out = el("div");
  card.append(el("label", "Month"), month, btn, out);
  btn.onclick = async () => {
    clear(out);
    try {
      const response = await fetch("/payroll/me?month=" + encodeURIComponent(month.value.trim()), {
        headers: { Authorization: "Bearer " + state.token }
      });
      if (!response.ok) {
        let detail = "";
        try { detail = (await response.json()).error.message; } catch (e) {}
        return msg(out, detail || "Could not load the payslip (" + response.status + ").");
      }
      const html = await response.text();
      const win = window.open("", "_blank");
      if (win) { win.document.open(); win.document.write(html); win.document.close(); }
      else msg(out, "Pop-up blocked. Allow pop-ups to view the payslip.");
    } catch (err) { msg(out, "The request took too long or failed."); }
  };
  return card;
}

/* ---------- boot ---------- */
document.getElementById("logoutBtn").onclick = logout;
(async () => {
  try {
    const statusData = await api("/setup/status");
    if (!statusData.setup_done) return showSetup();
    if (!state.token) return showLogin();
    await afterLogin();
  } catch (err) {
    clear(main);
    main.appendChild(el("p", "Cannot reach the server. Please refresh.", "msg err"));
  }
})();
