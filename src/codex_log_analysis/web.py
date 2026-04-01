from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .analysis import (
    build_report_payload,
    build_session_detail_payload,
    default_target_date,
    parse_date,
)


def render_html(initial_date: str, initial_limit: int) -> str:
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Codex Log Analysis</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f4f1ea;
      --panel: #fffdf8;
      --ink: #1f2430;
      --muted: #5f6778;
      --line: #d8cfbf;
      --accent: #a54d2d;
      --accent-soft: #f6d8c8;
      --chip: #efe7da;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Iowan Old Style", "Hiragino Mincho ProN", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, #f9e8d8 0, transparent 28%),
        linear-gradient(180deg, #f8f4ed 0%, var(--bg) 100%);
    }}
    main {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 32px 20px 56px;
    }}
    .hero {{
      background: rgba(255, 253, 248, 0.88);
      border: 1px solid var(--line);
      border-radius: 24px;
      padding: 24px;
      box-shadow: 0 14px 40px rgba(79, 54, 31, 0.08);
      backdrop-filter: blur(8px);
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: clamp(28px, 5vw, 42px);
      line-height: 1.05;
      letter-spacing: 0.02em;
    }}
    .lede {{
      margin: 0;
      color: var(--muted);
      font-size: 15px;
    }}
    .controls {{
      display: flex;
      gap: 12px;
      flex-wrap: nowrap;
      align-items: end;
      margin-top: 20px;
    }}
    .controls-main {{
      display: flex;
      gap: 12px;
      align-items: end;
      flex: 0 0 auto;
    }}
    .quick-days {{
      margin-left: auto;
      min-width: 530px;
      padding: 12px 14px;
      border: 3px solid #f59a17;
      border-radius: 10px;
      background: rgba(255, 250, 242, 0.72);
    }}
    .quick-days-title {{
      margin: 0 0 10px;
      color: var(--muted);
      font-size: 12px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .quick-days-list {{
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 8px;
    }}
    .quick-day {{
      min-width: 0;
      padding: 10px 8px;
      border-radius: 14px;
      border: 1px solid rgba(165, 77, 45, 0.18);
      background: rgba(255, 255, 255, 0.72);
      color: var(--ink);
      text-align: center;
      transition: transform 140ms ease, border-color 140ms ease, background 140ms ease;
    }}
    .quick-day:hover {{
      transform: translateY(-1px);
      border-color: var(--accent);
      background: rgba(255, 245, 238, 0.96);
    }}
    .quick-day.active {{
      background: var(--accent);
      border-color: var(--accent);
      color: white;
      box-shadow: 0 10px 24px rgba(165, 77, 45, 0.18);
    }}
    .quick-day-day {{
      display: block;
      font-size: 17px;
      font-weight: 700;
      line-height: 1.1;
    }}
    .quick-day-label {{
      display: block;
      margin-top: 4px;
      font-size: 11px;
      opacity: 0.82;
    }}
    label {{
      display: grid;
      gap: 6px;
      font-size: 13px;
      color: var(--muted);
    }}
    input, button {{
      border-radius: 12px;
      border: 1px solid var(--line);
      padding: 10px 12px;
      font: inherit;
      background: var(--panel);
      color: var(--ink);
    }}
    button {{
      background: var(--accent);
      border-color: var(--accent);
      color: white;
      cursor: pointer;
      min-width: 120px;
    }}
    button:hover {{ filter: brightness(1.03); }}
    .checkbox {{
      display: flex;
      gap: 8px;
      align-items: center;
      padding-bottom: 10px;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 12px;
      margin: 24px 0 20px;
    }}
    .stat {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 16px;
    }}
    .stat .k {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 6px;
    }}
    .stat .v {{
      font-size: 28px;
    }}
    .tabs {{
      display: flex;
      gap: 8px;
      margin-bottom: 16px;
      flex-wrap: wrap;
    }}
    .tab {{
      border: 1px solid var(--line);
      border-radius: 999px;
      background: transparent;
      color: var(--ink);
      min-width: 0;
      padding: 10px 16px;
    }}
    .tab.active {{
      background: var(--accent-soft);
      border-color: var(--accent);
      color: var(--accent);
    }}
    .panel {{
      display: none;
    }}
    .panel.active {{
      display: block;
    }}
    .section-title {{
      margin: 20px 0 10px;
      font-size: 22px;
    }}
    .cards {{
      display: grid;
      gap: 12px;
    }}
    .card {{
      background: rgba(255, 253, 248, 0.9);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 16px;
    }}
    .card h3 {{
      margin: 0 0 10px;
      font-size: 18px;
      line-height: 1.35;
    }}
    .sensitive {{
      transition: filter 160ms ease, opacity 160ms ease;
    }}
    body.demo-mask .sensitive {{
      filter: blur(10px);
      opacity: 0.85;
      user-select: none;
    }}
    body.demo-mask .sensitive::selection {{
      background: transparent;
    }}
    .meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 10px;
    }}
    .chip {{
      background: var(--chip);
      color: var(--muted);
      padding: 4px 9px;
      border-radius: 999px;
      font-size: 12px;
    }}
    .chip.subagent {{
      background: rgba(165, 77, 45, 0.14);
      color: var(--accent);
      border: 1px solid rgba(165, 77, 45, 0.22);
    }}
    .prompt, .paths {{
      color: var(--muted);
      font-size: 14px;
      line-height: 1.55;
      margin: 8px 0 0;
      word-break: break-word;
    }}
    .session-card-link {{
      display: block;
      color: inherit;
      text-decoration: none;
    }}
    .session-card-link .card {{
      cursor: pointer;
      transition: transform 160ms ease, border-color 160ms ease, box-shadow 160ms ease;
    }}
    .session-card-link:hover .card {{
      transform: translateY(-2px);
      border-color: var(--accent);
      box-shadow: 0 16px 34px rgba(79, 54, 31, 0.12);
    }}
    .session-card-link:focus-visible {{
      outline: none;
    }}
    .session-card-link:focus-visible .card {{
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(165, 77, 45, 0.18);
    }}
    .issue-list {{
      display: grid;
      gap: 12px;
    }}
    .issue-card {{
      display: grid;
      gap: 8px;
      background: rgba(255, 253, 248, 0.9);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 16px;
    }}
    .issue-card h3 {{
      margin: 0;
      font-size: 24px;
      color: var(--accent);
    }}
    ul {{
      margin: 0;
      padding-left: 20px;
    }}
    .empty {{
      color: var(--muted);
      border: 1px dashed var(--line);
      border-radius: 18px;
      padding: 20px;
      background: rgba(255, 253, 248, 0.65);
    }}
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <h1>Codex Log Analysis</h1>
      <p class="lede">通常セッションと archived セッションをまとめて読み、一覧から会話だけに絞ったセッション詳細へも移動できるローカルレポートです。</p>
      <form class="controls" id="controls">
        <div class="controls-main">
          <label>
            日付
            <input type="date" id="dateInput" value="{initial_date}">
          </label>
          <label class="checkbox">
            <input type="checkbox" id="allInput">
            全期間
          </label>
          <label>
            最大件数
            <input type="number" id="limitInput" min="1" value="{initial_limit}">
          </label>
          <button type="submit">再読み込み</button>
        </div>
        <section class="quick-days" aria-label="直近5日フィルタ">
          <p class="quick-days-title">直近5日</p>
          <div class="quick-days-list" id="quickDays"></div>
        </section>
      </form>
    </section>

    <section class="stats" id="stats"></section>

    <nav class="tabs">
      <button class="tab active" data-tab="sessions">セッション一覧</button>
      <button class="tab" data-tab="issues">Issue別要約</button>
    </nav>

    <section class="panel active" id="panel-sessions">
      <h2 class="section-title">通常セッション</h2>
      <div id="activeSessions" class="cards"></div>
      <h2 class="section-title">archived セッション</h2>
      <div id="archivedSessions" class="cards"></div>
    </section>

    <section class="panel" id="panel-issues">
      <div id="issueGroups" class="issue-list"></div>
    </section>
  </main>

  <script>
    const statsEl = document.getElementById("stats");
    const activeSessionsEl = document.getElementById("activeSessions");
    const archivedSessionsEl = document.getElementById("archivedSessions");
    const issueGroupsEl = document.getElementById("issueGroups");
    const dateInput = document.getElementById("dateInput");
    const allInput = document.getElementById("allInput");
    const limitInput = document.getElementById("limitInput");
    const quickDaysEl = document.getElementById("quickDays");
    const searchParams = new URLSearchParams(window.location.search);
    const demoStep = searchParams.get("step");
    const demoMask = searchParams.get("mask") === "1";
    const weekDays = ["日", "月", "火", "水", "木", "金", "土"];

    function buildSessionHref(session) {{
      const params = new URLSearchParams();
      if (session.file) {{
        params.set("file", session.file);
      }}
      if (demoMask) {{
        params.set("mask", "1");
      }}
      const query = params.toString();
      const base = `/sessions/${{encodeURIComponent(session.session_id)}}`;
      return query ? `${{base}}?${{query}}` : base;
    }}

    function cardHtml(session) {{
      const issues = session.issue_refs.length ? session.issue_refs.join(", ") : "-";
      const keywords = session.keywords.length ? session.keywords.join(", ") : "-";
      return `
        <a class="session-card-link" href="${{buildSessionHref(session)}}" aria-label="${{escapeHtml(session.title)}} の詳細を開く">
          <article class="card">
            <h3 class="sensitive">${{escapeHtml(session.title)}}</h3>
            <div class="meta sensitive">
              <span class="chip">${{session.archived ? "archived" : "active"}}</span>
              <span class="chip">branch: ${{escapeHtml(session.branch)}}</span>
              <span class="chip">prompts: ${{session.user_prompts}}</span>
              <span class="chip">skill signal: ${{session.skill_signal_count}}</span>
              <span class="chip">issues: ${{escapeHtml(issues)}}</span>
            </div>
            <p class="prompt sensitive">${{escapeHtml(session.first_prompt)}}</p>
            <p class="paths sensitive">cwd: ${{escapeHtml(session.cwd)}}<br>keywords: ${{escapeHtml(keywords)}}<br>file: ${{escapeHtml(session.file)}}</p>
          </article>
        </a>`;
    }}

    function issueCardHtml(issue) {{
      const titles = issue.titles.length
        ? `<ul class=\\"sensitive\\">${{issue.titles.map((title) => `<li>${{escapeHtml(title)}}</li>`).join("")}}</ul>`
        : "<div class=\\"empty sensitive\\">関連タイトルなし</div>";
      return `
        <article class="issue-card">
          <h3 class="sensitive">${{escapeHtml(issue.issue_ref)}}</h3>
          <div class="meta sensitive">
            <span class="chip">sessions: ${{issue.sessions_count}}</span>
            <span class="chip">active: ${{issue.active_count}}</span>
            <span class="chip">archived: ${{issue.archived_count}}</span>
            <span class="chip">prompts: ${{issue.total_prompts}}</span>
          </div>
          ${{titles}}
        </article>`;
    }}

    function escapeHtml(text) {{
      return String(text)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }}

    function formatDateValue(date) {{
      const year = date.getFullYear();
      const month = String(date.getMonth() + 1).padStart(2, "0");
      const day = String(date.getDate()).padStart(2, "0");
      return `${{year}}-${{month}}-${{day}}`;
    }}

    function parseDateInputValue(value) {{
      const match = /^(\\d{{4}})-(\\d{{2}})-(\\d{{2}})$/.exec(value);
      if (!match) {{
        return null;
      }}
      return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
    }}

    function buildQuickDays(anchorValue) {{
      const anchorDate = parseDateInputValue(anchorValue) || parseDateInputValue("{initial_date}");
      if (!anchorDate) {{
        quickDaysEl.innerHTML = "";
        return;
      }}
      const items = [];
      for (let offset = 0; offset < 5; offset += 1) {{
        const target = new Date(anchorDate);
        target.setDate(anchorDate.getDate() - offset);
        const value = formatDateValue(target);
        const label = `${{String(target.getMonth() + 1).padStart(2, "0")}}/${{String(target.getDate()).padStart(2, "0")}}`;
        const weekday = weekDays[target.getDay()];
        items.push(`
          <button
            type="button"
            class="quick-day${{value === dateInput.value && !allInput.checked ? " active" : ""}}"
            data-date="${{value}}"
            title="${{value}}">
            <span class="quick-day-day">${{label}}</span>
            <span class="quick-day-label">${{weekday}}</span>
          </button>
        `);
      }}
      quickDaysEl.innerHTML = items.join("");
      quickDaysEl.querySelectorAll(".quick-day").forEach((button) => {{
        button.addEventListener("click", async () => {{
          allInput.checked = false;
          dateInput.disabled = false;
          dateInput.value = button.dataset.date;
          buildQuickDays(dateInput.value);
          await loadReport();
        }});
      }});
    }}

    function renderStats(stats, targetDate) {{
      statsEl.innerHTML = `
        <div class="stat"><span class="k">対象</span><span class="v">${{escapeHtml(targetDate)}}</span></div>
        <div class="stat"><span class="k">sessions</span><span class="v">${{stats.sessions}}</span></div>
        <div class="stat"><span class="k">active</span><span class="v">${{stats.active_sessions}}</span></div>
        <div class="stat"><span class="k">archived</span><span class="v">${{stats.archived_sessions}}</span></div>
        <div class="stat"><span class="k">prompts</span><span class="v">${{stats.user_prompts}}</span></div>
        <div class="stat"><span class="k">issues</span><span class="v">${{stats.issue_refs}}</span></div>`;
    }}

    function renderList(target, items, emptyText) {{
      if (!items.length) {{
        target.innerHTML = `<div class="empty">${{escapeHtml(emptyText)}}</div>`;
        return;
      }}
      target.innerHTML = items.map(cardHtml).join("");
    }}

    function setActiveTab(tabName) {{
      document.querySelectorAll(".tab").forEach((node) => {{
        node.classList.toggle("active", node.dataset.tab === tabName);
      }});
      document.querySelectorAll(".panel").forEach((node) => {{
        node.classList.toggle("active", node.id === `panel-${{tabName}}`);
      }});
    }}

    function applyDemoState() {{
      if (demoMask) {{
        document.body.classList.add("demo-mask");
      }}
      if (!demoStep) {{
        return;
      }}

      const steps = {{
        "sessions-top": () => {{
          setActiveTab("sessions");
          window.scrollTo({{ top: 0, behavior: "auto" }});
        }},
        "sessions-archived": () => {{
          setActiveTab("sessions");
          const top = Math.max(0, archivedSessionsEl.getBoundingClientRect().top + window.scrollY - 120);
          window.scrollTo({{ top, behavior: "auto" }});
        }},
        "issues-top": () => {{
          setActiveTab("issues");
          window.scrollTo({{ top: 0, behavior: "auto" }});
        }},
        "issues-mid": () => {{
          setActiveTab("issues");
          const top = Math.max(0, issueGroupsEl.getBoundingClientRect().top + window.scrollY + 180);
          window.scrollTo({{ top, behavior: "auto" }});
        }},
      }};

      const action = steps[demoStep];
      if (action) {{
        action();
      }}
    }}

    async function loadReport() {{
      const params = new URLSearchParams();
      if (allInput.checked) {{
        params.set("all", "1");
      }} else {{
        params.set("date", dateInput.value);
      }}
      params.set("limit", limitInput.value || "200");
      const response = await fetch(`/api/report?${{params.toString()}}`);
      if (!response.ok) {{
        const text = await response.text();
        throw new Error(text || `HTTP ${{response.status}}`);
      }}
      const payload = await response.json();
      renderStats(payload.stats, payload.target_date);
      renderList(activeSessionsEl, payload.active_sessions, "通常セッションはありません。");
      renderList(archivedSessionsEl, payload.archived_sessions, "archived セッションはありません。");
      if (!payload.issue_groups.length) {{
        issueGroupsEl.innerHTML = '<div class="empty">Issue に結びついたセッションがありません。</div>';
      }} else {{
        issueGroupsEl.innerHTML = payload.issue_groups.map(issueCardHtml).join("");
      }}
      applyDemoState();
      buildQuickDays(dateInput.value);
      document.body.classList.add("report-ready");
    }}

    document.getElementById("controls").addEventListener("submit", async (event) => {{
      event.preventDefault();
      await loadReport();
    }});

    allInput.addEventListener("change", () => {{
      dateInput.disabled = allInput.checked;
      buildQuickDays(dateInput.value);
    }});

    dateInput.addEventListener("change", () => {{
      buildQuickDays(dateInput.value);
    }});

    document.querySelectorAll(".tab").forEach((tab) => {{
      tab.addEventListener("click", () => {{
        setActiveTab(tab.dataset.tab);
      }});
    }});

    if (!dateInput.value) {{
      dateInput.value = "{initial_date}";
    }}
    buildQuickDays(dateInput.value);
    loadReport().catch((error) => {{
      statsEl.innerHTML = `<div class="empty">読み込みに失敗しました: ${{escapeHtml(error.message)}}</div>`;
    }});
  </script>
</body>
</html>
"""


def render_session_detail_html(session_id: str, file_hint: str | None) -> str:
    session_id_json = json.dumps(session_id, ensure_ascii=False)
    file_hint_json = json.dumps(file_hint, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Codex Log Analysis</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f4f1ea;
      --panel: #fffdf8;
      --panel-alt: #f7efe4;
      --ink: #1f2430;
      --muted: #5f6778;
      --line: #d8cfbf;
      --accent: #a54d2d;
      --assistant: #335c81;
      --accent-soft: #f6d8c8;
      --chip: #efe7da;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Iowan Old Style", "Hiragino Mincho ProN", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, #f9e8d8 0, transparent 28%),
        linear-gradient(180deg, #f8f4ed 0%, var(--bg) 100%);
    }}
    body.demo-mask .sensitive {{
      filter: blur(10px);
      opacity: 0.85;
      user-select: none;
    }}
    body.demo-mask .sensitive::selection {{
      background: transparent;
    }}
    main {{
      max-width: 960px;
      margin: 0 auto;
      padding: 28px 20px 56px;
    }}
    .topbar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 16px;
      flex-wrap: wrap;
    }}
    .back-link {{
      color: var(--accent);
      text-decoration: none;
      font-size: 14px;
      font-weight: 600;
    }}
    .back-link:hover {{
      text-decoration: underline;
    }}
    .hero {{
      background: rgba(255, 253, 248, 0.9);
      border: 1px solid var(--line);
      border-radius: 24px;
      padding: 24px;
      box-shadow: 0 14px 40px rgba(79, 54, 31, 0.08);
      backdrop-filter: blur(8px);
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: clamp(28px, 5vw, 40px);
      line-height: 1.08;
      letter-spacing: 0.02em;
    }}
    .lede {{
      margin: 0;
      color: var(--muted);
      font-size: 15px;
    }}
    .meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 18px;
    }}
    .chip {{
      background: var(--chip);
      color: var(--muted);
      padding: 4px 9px;
      border-radius: 999px;
      font-size: 12px;
    }}
    .detail-strip {{
      display: flex;
      gap: 10px;
      margin: 14px 0 20px;
      align-items: stretch;
      overflow-x: auto;
      padding-bottom: 4px;
    }}
    .detail-pill {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      min-width: 0;
      padding: 10px 14px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255, 253, 248, 0.92);
      box-shadow: 0 8px 20px rgba(79, 54, 31, 0.05);
      white-space: nowrap;
    }}
    .detail-pill .k {{
      color: var(--muted);
      font-size: 12px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }}
    .detail-pill .v {{
      font-size: 14px;
      max-width: 280px;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .section-title {{
      margin: 14px 0 12px;
      font-size: 22px;
    }}
    .conversation {{
      display: grid;
      gap: 14px;
      padding: 26px 22px;
      border-radius: 28px;
      border: 1px solid rgba(140, 164, 117, 0.35);
      background:
        linear-gradient(180deg, rgba(236, 247, 220, 0.92) 0%, rgba(249, 245, 237, 0.96) 100%),
        repeating-linear-gradient(
          -45deg,
          rgba(255, 255, 255, 0.22) 0,
          rgba(255, 255, 255, 0.22) 12px,
          rgba(233, 242, 220, 0.12) 12px,
          rgba(233, 242, 220, 0.12) 24px
        );
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.35);
    }}
    .message-row {{
      display: flex;
    }}
    .message-row.user {{
      justify-content: flex-end;
    }}
    .message-row.assistant {{
      justify-content: flex-start;
    }}
    .bubble-wrap {{
      display: grid;
      gap: 6px;
      max-width: 72%;
    }}
    .bubble-meta {{
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 0 6px;
      color: var(--muted);
      font-size: 11px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }}
    .message-row.user .bubble-meta {{
      justify-content: flex-end;
    }}
    .bubble-role {{
      font-weight: 700;
    }}
    .bubble {{
      position: relative;
      padding: 14px 16px;
      border-radius: 22px;
      white-space: pre-wrap;
      word-break: break-word;
      line-height: 1.72;
      font-size: 15px;
      box-shadow: 0 10px 22px rgba(73, 52, 36, 0.08);
    }}
    .message-row.assistant .bubble {{
      background: rgba(255, 255, 255, 0.96);
      color: var(--ink);
      border: 1px solid rgba(191, 198, 204, 0.65);
      border-bottom-left-radius: 8px;
    }}
    .message-row.user .bubble {{
      background: linear-gradient(180deg, #d4fb72 0%, #b8ef41 100%);
      color: #163109;
      border: 1px solid rgba(137, 181, 41, 0.5);
      border-bottom-right-radius: 8px;
    }}
    .message-row.assistant .bubble-role {{
      color: var(--assistant);
    }}
    .message-row.user .bubble-role {{
      color: var(--accent);
    }}
    .timestamp {{
      color: var(--muted);
    }}
    .empty {{
      color: var(--muted);
      border: 1px dashed var(--line);
      border-radius: 18px;
      padding: 20px;
      background: rgba(255, 253, 248, 0.65);
    }}
  </style>
</head>
<body>
  <main>
    <div class="topbar">
      <a class="back-link" href="/">一覧に戻る</a>
    </div>

    <section class="hero">
      <h1 id="title">会話詳細</h1>
      <p class="lede">このページでは、セッション内の `user` / `assistant` メッセージ本文だけを時系列で表示します。</p>
      <div class="meta sensitive" id="sessionMeta"></div>
    </section>

    <section class="detail-strip" id="sessionStats"></section>

    <section>
      <h2 class="section-title">会話ログ</h2>
      <div class="conversation" id="conversation"></div>
    </section>
  </main>

  <script>
    const sessionId = {session_id_json};
    const fileHint = {file_hint_json};
    const titleEl = document.getElementById("title");
    const sessionMetaEl = document.getElementById("sessionMeta");
    const sessionStatsEl = document.getElementById("sessionStats");
    const conversationEl = document.getElementById("conversation");
    const searchParams = new URLSearchParams(window.location.search);
    const demoMask = searchParams.get("mask") === "1";

    function escapeHtml(text) {{
      return String(text)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }}

    function messageHtml(message) {{
      const timestamp = message.timestamp ? escapeHtml(message.timestamp) : "-";
      const roleLabel = message.display_role ? escapeHtml(message.display_role) : (message.role === "user" ? "user" : "assistant");
      return `
        <article class="message-row ${{message.role}}">
          <div class="bubble-wrap sensitive">
            <div class="bubble-meta">
              <span class="bubble-role">${{roleLabel}}</span>
              <span class="timestamp">${{timestamp}}</span>
            </div>
            <div class="bubble">${{escapeHtml(message.text)}}</div>
          </div>
        </article>`;
    }}

    function statPill(label, value) {{
      return `
        <article class="detail-pill sensitive" title="${{escapeHtml(value)}}">
          <span class="k">${{escapeHtml(label)}}</span>
          <span class="v">${{escapeHtml(value)}}</span>
        </article>`;
    }}

    function renderSession(session, stats) {{
      const title = session.full_title || session.title || session.session_id;
      document.title = `${{title}} | Codex Log Analysis`;
      titleEl.textContent = title;
      const issues = session.issue_refs.length ? session.issue_refs.join(", ") : "-";
      const metaChips = [
        `<span class="chip">${{session.archived ? "archived" : "active"}}</span>`,
        `<span class="chip">session: ${{escapeHtml(session.session_id)}}</span>`,
        `<span class="chip">branch: ${{escapeHtml(session.branch)}}</span>`,
        `<span class="chip">issues: ${{escapeHtml(issues)}}</span>`,
      ];
      if (session.is_subagent_session) {{
        metaChips.push('<span class="chip subagent">sub agent session</span>');
        if (session.subagent_nickname) {{
          metaChips.push(`<span class="chip subagent">nickname: ${{escapeHtml(session.subagent_nickname)}}</span>`);
        }}
        if (session.subagent_role) {{
          metaChips.push(`<span class="chip subagent">role: ${{escapeHtml(session.subagent_role)}}</span>`);
        }}
      }}
      sessionMetaEl.innerHTML = metaChips.join("");
      const statItems = [
        statPill("messages", `${{stats.messages}}`),
        statPill("user / assistant", `${{stats.user_messages}} / ${{stats.assistant_messages}}`),
        statPill("cwd", session.cwd),
        statPill("log file", session.file),
      ];
      if (session.is_subagent_session && session.subagent_parent_session_id) {{
        statItems.unshift(statPill("parent session", session.subagent_parent_session_id));
      }}
      sessionStatsEl.innerHTML = statItems.join("");
    }}

    async function loadSessionDetail() {{
      if (demoMask) {{
        document.body.classList.add("demo-mask");
      }}
      const params = new URLSearchParams();
      if (fileHint) {{
        params.set("file", fileHint);
      }}
      if (demoMask) {{
        params.set("mask", "1");
      }}
      const query = params.toString();
      const response = await fetch(`/api/sessions/${{encodeURIComponent(sessionId)}}${{query ? `?${{query}}` : ""}}`);
      if (!response.ok) {{
        const text = await response.text();
        throw new Error(text || `HTTP ${{response.status}}`);
      }}
      const payload = await response.json();
      renderSession(payload.session, payload.stats);
      if (!payload.conversation.length) {{
        conversationEl.innerHTML = '<div class="empty">会話本文を持つメッセージはありません。</div>';
        return;
      }}
      conversationEl.innerHTML = payload.conversation.map(messageHtml).join("");
    }}

    loadSessionDetail().catch((error) => {{
      conversationEl.innerHTML = `<div class="empty">読み込みに失敗しました: ${{escapeHtml(error.message)}}</div>`;
    }});
  </script>
</body>
</html>
"""


def serve(
    *,
    root: Path,
    archived_root: Path,
    sqlite_path: Path | None,
    host: str,
    port: int,
    initial_date,
    limit: int,
) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            if parsed.path == "/":
                target_date = initial_date.isoformat() if initial_date is not None else default_target_date().isoformat()
                body = render_html(target_date, limit).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if parsed.path.startswith("/sessions/"):
                session_id = unquote(parsed.path.removeprefix("/sessions/"))
                if not session_id:
                    self.send_error(HTTPStatus.BAD_REQUEST, "missing session id")
                    return
                file_hint = query.get("file", [""])[0] or None
                body = render_session_detail_html(session_id, file_hint).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if parsed.path == "/api/report":
                all_mode = query.get("all", ["0"])[0] == "1"
                date_value = query.get("date", [""])[0]
                target_date = None if all_mode else parse_date(date_value or default_target_date().isoformat())
                limit_value = int(query.get("limit", [str(limit)])[0])
                payload = build_report_payload(
                    root=root,
                    archived_root=archived_root,
                    sqlite_path=sqlite_path,
                    target_date=target_date,
                    limit=limit_value,
                )
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if parsed.path.startswith("/api/sessions/"):
                session_id = unquote(parsed.path.removeprefix("/api/sessions/"))
                if not session_id:
                    self.send_error(HTTPStatus.BAD_REQUEST, "missing session id")
                    return
                file_hint = query.get("file", [""])[0] or None
                try:
                    payload = build_session_detail_payload(
                        root=root,
                        archived_root=archived_root,
                        sqlite_path=sqlite_path,
                        session_id=session_id,
                        file_hint=file_hint,
                    )
                except FileNotFoundError as exc:
                    self.send_error(HTTPStatus.NOT_FOUND, str(exc))
                    return
                except ValueError as exc:
                    self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                    return
                except RuntimeError as exc:
                    self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
                    return

                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if parsed.path == "/favicon.ico":
                self.send_response(HTTPStatus.NO_CONTENT)
                self.end_headers()
                return

            self.send_error(HTTPStatus.NOT_FOUND, "not found")

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Serving on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
