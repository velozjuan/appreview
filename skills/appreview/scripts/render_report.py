#!/usr/bin/env python3
"""Render an /appreview report JSON into a self-contained HTML page for publishing.

    python render_report.py report.json --out appreview-report.html

The JSON format is described in references/report-format.md. All text is
HTML-escaped (reviewer messages and code snippets are third-party data). The page
follows the artifact contract: no <html>/<head>/<body>, tokens for both themes,
Google Fonts only, no external scripts.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from html import escape
from pathlib import Path
from typing import Any, Dict, List

SEVERITY_LABEL = {"high": "High", "medium": "Medium", "low": "Low"}
STATUS_LABEL = {"open": "Open", "past": "Past", "likely": "Likely", "possible": "Possible", "clean": "Clean",
                "repeat": "Same problem found", "manual": "Check by hand", "fixed": "Looks fixed"}

CSS = """
/* Layout: one reading column; each finding is a row with the guideline number as a mono marker on the left. */
:root {
  --bg: #F3F5F7; --surface: #FFFFFF; --ink: #17212B; --muted: #5A6674; --line: #DAE0E6;
  --accent: #0E6F77; --accent-soft: #E1F0F1;
  --crit: #B4332A; --crit-soft: #FBE9E7; --warn: #9A5B00; --warn-soft: #FBF0DD;
  --ok: #2B7A4B; --ok-soft: #E3F3E9; --quiet-soft: #ECEFF3;
  --f-display: "Bricolage Grotesque", "Avenir Next", "Segoe UI", sans-serif;
  --f-body: "IBM Plex Sans", -apple-system, "Segoe UI", Roboto, sans-serif;
  --f-mono: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #0E1317; --surface: #151C21; --ink: #E4EAEE; --muted: #96A2AD; --line: #26313A;
  --accent: #56B7BE; --accent-soft: #15353A;
  --crit: #F2786D; --crit-soft: #3A1C1A; --warn: #E9A847; --warn-soft: #3A2A12;
  --ok: #63C28E; --ok-soft: #16301F; --quiet-soft: #1D252C; color-scheme: dark; } }
:root[data-theme="dark"] {
  --bg: #0E1317; --surface: #151C21; --ink: #E4EAEE; --muted: #96A2AD; --line: #26313A;
  --accent: #56B7BE; --accent-soft: #15353A;
  --crit: #F2786D; --crit-soft: #3A1C1A; --warn: #E9A847; --warn-soft: #3A2A12;
  --ok: #63C28E; --ok-soft: #16301F; --quiet-soft: #1D252C; color-scheme: dark; }
body { background: var(--bg); color: var(--ink); font: 15px/1.6 var(--f-body);
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }
.wrap { max-width: 920px; margin: 0 auto; padding-block: 40px 64px; display: grid; gap: 40px; }
.wrap > *, dl > div, dd, .group > * { min-width: 0; }
h1, h2, h3 { font-family: var(--f-display); text-wrap: balance; margin: 0; line-height: 1.15; }
h1 { font-size: clamp(28px, 5vw, 40px); font-weight: 700; letter-spacing: -0.01em; }
h2 { font-size: 22px; font-weight: 650; }
h3 { font-size: 17px; font-weight: 600; }
a { color: var(--accent); }
a:focus-visible, button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 4px; }
.eyebrow { font: 500 12px/1.4 var(--f-mono); letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); }
header { display: grid; gap: 14px; }
.stats { display: flex; flex-wrap: wrap; gap: 8px 22px; margin: 4px 0 0; padding: 0; list-style: none; color: var(--muted); }
.stats b { font: 600 20px/1 var(--f-display); color: var(--ink); font-variant-numeric: tabular-nums; margin-right: 6px; }
.filters { display: flex; flex-wrap: wrap; gap: 8px; }
.filters button { font: 500 13px var(--f-body); color: var(--ink); background: var(--surface); border: 1px solid var(--line);
  border-radius: 999px; padding: 6px 14px; cursor: pointer; }
.filters button[aria-pressed="true"] { background: var(--ink); color: var(--bg); border-color: var(--ink); }
.callout { background: var(--accent-soft); border-radius: 10px; padding: 18px 20px; display: grid; gap: 10px; }
.callout ul { margin: 0; padding-left: 20px; display: grid; gap: 6px; }
.group { display: grid; gap: 4px; }
.group-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 14px; padding-bottom: 10px; border-bottom: 2px solid var(--ink); }
.group-head .sub { color: var(--muted); font-size: 14px; }
.group-head a { font-size: 14px; margin-left: auto; }
.finding { display: grid; grid-template-columns: 120px minmax(0, 1fr); gap: 4px 20px; padding-block: 22px; border-bottom: 1px solid var(--line); }
.gnum { font: 600 19px/1.3 var(--f-mono); color: var(--accent); font-variant-numeric: tabular-nums; min-width: 0; }
.gnum > span { white-space: nowrap; display: inline-block; }
.finding[data-sev="high"] .gnum { color: var(--crit); }
.finding[data-sev="medium"] .gnum { color: var(--warn); }
.fbody { display: grid; gap: 12px; min-width: 0; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip { font: 500 12px/1 var(--f-body); padding: 5px 9px; border-radius: 6px; background: var(--quiet-soft); color: var(--muted); }
.chip.high, .chip.open, .chip.repeat { background: var(--crit-soft); color: var(--crit); }
.chip.medium, .chip.likely, .chip.manual { background: var(--warn-soft); color: var(--warn); }
.chip.low, .chip.past, .chip.clean, .chip.fixed { background: var(--ok-soft); color: var(--ok); }
.chip.history { background: var(--accent-soft); color: var(--accent); }
.finding[data-status="repeat"] .gnum { color: var(--crit); }
.finding[data-status="manual"] .gnum { color: var(--warn); }
.finding[data-status="fixed"] .gnum { color: var(--ok); }
dl { margin: 0; display: grid; gap: 12px; }
dt { font: 600 12px/1.3 var(--f-body); letter-spacing: 0.05em; text-transform: uppercase; color: var(--muted); margin-bottom: 4px; }
dd { margin: 0; max-width: 68ch; }
dd ol { margin: 0; padding-left: 20px; display: grid; gap: 4px; }
blockquote { margin: 0; padding-left: 14px; border-left: 2px solid var(--line); color: var(--ink); font-style: italic; }
.evidence { overflow-x: auto; background: var(--quiet-soft); border-radius: 8px; padding: 10px 12px; }
.evidence code { display: block; font: 13px/1.6 var(--f-mono); white-space: pre; }
.evidence .loc { color: var(--muted); }
.reply { background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 14px 16px; display: grid; gap: 10px; }
.reply p { margin: 0; white-space: pre-wrap; }
.reply button { justify-self: start; font: 500 13px var(--f-body); color: var(--accent); background: none; border: 1px solid var(--accent);
  border-radius: 6px; padding: 5px 12px; cursor: pointer; }
.clean-note { color: var(--muted); padding-block: 14px; }
.steps ol { margin: 0; padding-left: 22px; display: grid; gap: 8px; max-width: 68ch; }
footer { color: var(--muted); font-size: 13px; display: grid; gap: 6px; border-top: 1px solid var(--line); padding-top: 16px; }
footer ul { margin: 0; padding-left: 18px; }
@media (max-width: 560px) {
  .finding { grid-template-columns: minmax(0, 1fr); }
  .group-head a { margin-left: 0; }
}
@media (prefers-reduced-motion: no-preference) { .filters button { transition: background .15s, color .15s; } }
"""

JS = """
(function(){
  var btns = document.querySelectorAll('.filters button');
  function apply(f){
    btns.forEach(function(b){ b.setAttribute('aria-pressed', String(b.dataset.f === f)); });
    document.querySelectorAll('.finding').forEach(function(el){
      el.hidden = !(f === 'all' || el.dataset.status === f || el.dataset.sev === f);
    });
    document.querySelectorAll('.group').forEach(function(g){
      var any = g.querySelectorAll('.finding:not([hidden])').length > 0 || (f === 'all' && g.querySelector('.clean-note'));
      g.hidden = !any;
    });
  }
  btns.forEach(function(b){ b.addEventListener('click', function(){ apply(b.dataset.f); }); });
  document.querySelectorAll('.reply button').forEach(function(b){
    b.addEventListener('click', function(){
      var p = b.parentElement.querySelector('p');
      var done = function(){ b.textContent = 'Copied'; setTimeout(function(){ b.textContent = 'Copy reply'; }, 1600); };
      var fallback = function(){ var r = document.createRange(); r.selectNodeContents(p); var s = getSelection(); s.removeAllRanges(); s.addRange(r); b.textContent = 'Selected, press Copy'; };
      try { navigator.clipboard.writeText(p.innerText).then(done, fallback); } catch (e) { fallback(); }
    });
  });
})();
"""


def e(v: Any) -> str:
    return escape("" if v is None else str(v))


def guideline_html(g: str) -> str:
    """Each guideline number stays on one line; combined ones ("5.6.1 / 5.6.3",
    "2.1, 2.3") break between numbers so they never run into the title."""
    parts = [x for x in re.split(r"\s*([/,&+])\s*", str(g)) if x]
    out, i = [], 0
    while i < len(parts):
        tok = parts[i]
        if i + 1 < len(parts) and parts[i + 1] in "/,&+":
            tok += (" " if parts[i + 1] != "," else "") + parts[i + 1]
            i += 1
        out.append(f"<span>{e(tok)}</span>")
        i += 1
    return " ".join(out)


def render_finding(f: Dict[str, Any]) -> str:
    sev = (f.get("severity") or "").lower()
    status = (f.get("status") or "").lower()
    chips = []
    if status:
        chips.append(f'<span class="chip {e(status)}">{e(STATUS_LABEL.get(status, status.title()))}</span>')
    if sev:
        chips.append(f'<span class="chip {e(sev)}">{e(SEVERITY_LABEL.get(sev, sev.title()))} risk</span>')
    if f.get("fix_type"):
        chips.append(f'<span class="chip">{e(f["fix_type"])}</span>')
    for pr in (f.get("previously_rejected") or [])[:2]:
        label = " ".join(x for x in [pr.get("app"), pr.get("version")] if x)
        chips.append(f'<span class="chip history">Rejected before: {e(label)}</span>')
    parts = []
    if f.get("said"):
        said_label = "What the reviewer said then" if f.get("status") in ("repeat", "manual", "fixed") else "What the reviewer said"
        parts.append(f'<div><dt>{said_label}</dt><dd><blockquote>{e(f["said"])}</blockquote></dd></div>')
    if f.get("why"):
        why_label = "In this project" if f.get("status") in ("repeat", "manual", "fixed") else ("Why" if f.get("said") else "What we found")
        parts.append(f'<div><dt>{why_label}</dt><dd>{e(f["why"])}</dd></div>')
    ev = f.get("evidence") or []
    if ev:
        lines = []
        for x in ev:
            loc = x.get("file", "")
            if x.get("line"):
                loc += f":{x['line']}"
            lines.append(f'<code><span class="loc">{e(loc)}</span>  {e(x.get("snippet", ""))}</code>')
        parts.append(f'<div><dt>Where</dt><dd><div class="evidence">{"".join(lines)}</div></dd></div>')
    fix = f.get("fix") or []
    if fix:
        items = "".join(f"<li>{e(s)}</li>" for s in fix)
        parts.append(f'<div><dt>How to fix</dt><dd><ol>{items}</ol></dd></div>')
    if f.get("reply"):
        parts.append('<div><dt>Reply to App Review</dt><dd><div class="reply">'
                     f'<p>{e(f["reply"])}</p><button type="button">Copy reply</button></div></dd></div>')
    return (f'<article class="finding" data-sev="{e(sev)}" data-status="{e(status)}">'
            f'<div class="gnum">{guideline_html(f.get("guideline") or "—")}</div>'
            f'<div class="fbody"><h3>{e(f.get("title", ""))}</h3>'
            f'<div class="chips">{"".join(chips)}</div><dl>{"".join(parts)}</dl></div></article>')


def render(rep: Dict[str, Any]) -> str:
    kind = rep.get("kind", "rejections")
    title = rep.get("title") or ("App Review Check" if kind == "preflight" else "App Review Report")
    groups = rep.get("groups") or []
    findings = [f for g in groups for f in g.get("findings", [])]

    stats = rep.get("stats")
    if not stats:
        if kind == "preflight":
            stats = [[sum(1 for f in findings if f.get("severity") == s), f"{SEVERITY_LABEL[s].lower()} risk"] for s in ("high", "medium", "low")]
        else:
            stats = [[len(groups), "apps with issues"],
                     [sum(1 for f in findings if f.get("status") == "open"), "open now"],
                     [sum(1 for f in findings if f.get("status") == "past"), "past"]]
    stats_html = "".join(f"<li><b>{e(n)}</b>{e(label)}</li>" for n, label in stats)

    present = {f.get("status") for f in findings} | {f.get("severity") for f in findings}
    order = ["repeat", "manual", "high", "medium", "low"] if kind == "preflight" else ["open", "past"]
    short = {"repeat": "Repeats", "manual": "Check by hand"}
    filt = [("all", "All")] + [(k, short.get(k) or SEVERITY_LABEL.get(k) or STATUS_LABEL.get(k)) for k in order if k in present]
    filters_html = ""
    if len(filt) > 2:
        filters_html = '<nav class="filters" aria-label="Filter findings">' + "".join(
            f'<button type="button" data-f="{k}" aria-pressed="{str(k == "all").lower()}">{e(label)}</button>' for k, label in filt) + "</nav>"

    patterns = rep.get("patterns") or []
    patterns_html = ""
    if patterns:
        items = "".join(f'<li><b>{e(p.get("guideline"))}</b> in {e(", ".join(p.get("apps", [])))}: {e(p.get("cause"))} '
                        f'<span>→ {e(p.get("fix"))}</span></li>' for p in patterns)
        patterns_html = f'<section class="callout"><h2>Patterns across apps</h2><ul>{items}</ul></section>'

    groups_html = []
    for g in groups:
        link = f'<a href="{e(g["link"])}" target="_blank" rel="noopener">Open in App Store Connect</a>' if g.get("link", "").startswith("https://") else ""
        body = "".join(render_finding(f) for f in g.get("findings", [])) or \
            f'<p class="clean-note">{e(g.get("clean_note") or "Nothing found.")}</p>'
        groups_html.append(f'<section class="group"><div class="group-head"><h2>{e(g.get("name"))}</h2>'
                           f'<span class="sub">{e(g.get("subtitle", ""))}</span>{link}</div>{body}</section>')

    steps = rep.get("next_steps") or []
    steps_html = ""
    if steps:
        steps_html = '<section class="steps"><h2>Next steps</h2><ol>' + "".join(f"<li>{e(s)}</li>" for s in steps) + "</ol></section>"

    notes = rep.get("notes") or []
    notes_html = "<ul>" + "".join(f"<li>{e(n)}</li>" for n in notes) + "</ul>" if notes else ""
    eyebrow = " · ".join(x for x in [("Pre-submission check" if kind == "preflight" else "App Review rejections"),
                                      rep.get("generated"), rep.get("source")] if x)
    return f"""<title>{e(title)}</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,700&family=IBM+Plex+Mono:wght@500;600&family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;1,400&display=swap">
<style>{CSS}</style>
<div class="wrap">
<header><div class="eyebrow">{e(eyebrow)}</div><h1>{e(title)}</h1>
{f'<p style="margin:0;max-width:68ch">{e(rep["summary"])}</p>' if rep.get("summary") else ""}
<ul class="stats">{stats_html}</ul>{filters_html}</header>
{patterns_html}
{"".join(groups_html)}
{steps_html}
<footer>{notes_html}<div>Generated with /appreview. Guideline references: <a href="https://developer.apple.com/app-store/review/guidelines/" target="_blank" rel="noopener">App Review Guidelines</a>.</div></footer>
</div>
<script>{JS}</script>
"""


def main(argv: List[str] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("report", help="report JSON (see references/report-format.md)")
    ap.add_argument("--out", default="appreview-report.html")
    args = ap.parse_args(argv)
    rep = json.loads(Path(args.report).read_text())
    Path(args.out).write_text(render(rep))
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
