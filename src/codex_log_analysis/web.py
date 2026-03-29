from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .analysis import build_report_payload, default_target_date, parse_date


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
      flex-wrap: wrap;
      align-items: end;
      margin-top: 20px;
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
    .prompt, .paths {{
      color: var(--muted);
      font-size: 14px;
      line-height: 1.55;
      margin: 8px 0 0;
      word-break: break-word;
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
    @media (max-width: 720px) {{
      main {{ padding: 20px 14px 40px; }}
      .hero {{ padding: 18px; border-radius: 18px; }}
      .stats {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <h1>Codex Log Analysis</h1>
      <p class="lede">通常セッションと archived セッションをまとめて読み、Issue 別の束ねも同じ画面で見られるローカルレポートです。</p>
      <form class="controls" id="controls">
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

    function cardHtml(session) {{
      const issues = session.issue_refs.length ? session.issue_refs.join(", ") : "-";
      const keywords = session.keywords.length ? session.keywords.join(", ") : "-";
      return `
        <article class="card">
          <h3>${{escapeHtml(session.title)}}</h3>
          <div class="meta">
            <span class="chip">${{session.archived ? "archived" : "active"}}</span>
            <span class="chip">branch: ${{escapeHtml(session.branch)}}</span>
            <span class="chip">prompts: ${{session.user_prompts}}</span>
            <span class="chip">skill signal: ${{session.skill_signal_count}}</span>
            <span class="chip">issues: ${{escapeHtml(issues)}}</span>
          </div>
          <p class="prompt">${{escapeHtml(session.first_prompt)}}</p>
          <p class="paths">cwd: ${{escapeHtml(session.cwd)}}<br>keywords: ${{escapeHtml(keywords)}}<br>file: ${{escapeHtml(session.file)}}</p>
        </article>`;
    }}

    function issueCardHtml(issue) {{
      const titles = issue.titles.length
        ? `<ul>${{issue.titles.map((title) => `<li>${{escapeHtml(title)}}</li>`).join("")}}</ul>`
        : "<div class=\\"empty\\">関連タイトルなし</div>";
      return `
        <article class="issue-card">
          <h3>${{escapeHtml(issue.issue_ref)}}</h3>
          <div class="meta">
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
    }}

    document.getElementById("controls").addEventListener("submit", async (event) => {{
      event.preventDefault();
      await loadReport();
    }});

    allInput.addEventListener("change", () => {{
      dateInput.disabled = allInput.checked;
    }});

    document.querySelectorAll(".tab").forEach((tab) => {{
      tab.addEventListener("click", () => {{
        document.querySelectorAll(".tab").forEach((node) => node.classList.remove("active"));
        document.querySelectorAll(".panel").forEach((node) => node.classList.remove("active"));
        tab.classList.add("active");
        document.getElementById(`panel-${{tab.dataset.tab}}`).classList.add("active");
      }});
    }});

    if (!dateInput.value) {{
      dateInput.value = "{initial_date}";
    }}
    loadReport().catch((error) => {{
      statsEl.innerHTML = `<div class="empty">読み込みに失敗しました: ${{escapeHtml(error.message)}}</div>`;
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
            if parsed.path == "/":
                target_date = initial_date.isoformat() if initial_date is not None else default_target_date().isoformat()
                body = render_html(target_date, limit).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if parsed.path == "/api/report":
                query = parse_qs(parsed.query)
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
