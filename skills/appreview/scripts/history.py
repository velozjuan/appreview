#!/usr/bin/env python3
"""Keep a local history of the account's App Store rejections.

The submission check uses it to test a project against what App Review rejected
before, in this app and in the developer's other apps.

    python history.py import report.json      # add rejections from an /appreview report
    python history.py list                    # show what's stored
    python history.py path                    # print where the history lives

Stored at ~/.appreview/history.json (override with --file or APPREVIEW_HISTORY).
Only what's needed is kept: app, bundle ID, version, date, guideline, title, the
reviewer's words and the cause. No credentials, contact details or account IDs.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

DEFAULT = Path(os.environ.get("APPREVIEW_HISTORY", "~/.appreview/history.json")).expanduser()
KEEP = ("app", "bundle_id", "version", "date", "guideline", "title", "said", "why", "fix_type")


def load(path: Path) -> Dict[str, Any]:
    if path.is_file():
        try:
            data = json.loads(path.read_text())
            if isinstance(data, dict) and isinstance(data.get("rejections"), list):
                return data
        except ValueError:
            pass
    return {"version": 1, "updated": None, "rejections": []}


def key(r: Dict[str, Any]) -> tuple:
    return ((r.get("bundle_id") or r.get("app") or "").lower(), r.get("version") or "", r.get("guideline") or "")


def from_report(rep: Dict[str, Any]) -> List[Dict[str, Any]]:
    if rep.get("kind") != "rejections":
        raise ValueError("Only rejection reports can be imported (kind: rejections).")
    out = []
    for g in rep.get("groups", []):
        for f in g.get("findings", []):
            if not f.get("guideline"):
                continue
            entry = {
                "app": g.get("name"),
                "bundle_id": g.get("bundle_id"),
                "version": f.get("version") or g.get("version"),
                "date": f.get("date") or rep.get("generated"),
                "guideline": f.get("guideline"),
                "title": f.get("title"),
                "said": (f.get("said") or "")[:1500],
                "why": (f.get("why") or "")[:800],
                "fix_type": f.get("fix_type"),
            }
            out.append({k: v for k, v in entry.items() if v})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["import", "list", "path"])
    ap.add_argument("report", nargs="?", help="report JSON for import")
    ap.add_argument("--file", default=str(DEFAULT), help=f"history file (default {DEFAULT})")
    args = ap.parse_args(argv)
    path = Path(args.file).expanduser()

    if args.command == "path":
        print(path)
        return 0
    hist = load(path)
    if args.command == "list":
        if not hist["rejections"]:
            print("No rejection history yet. Run /appreview on the account first.")
        for r in sorted(hist["rejections"], key=lambda r: r.get("date") or "", reverse=True):
            print(f"{r.get('date', '?'):10}  {r.get('app', '?')} {r.get('version', '')}  {r.get('guideline')}  {r.get('title', '')}")
        return 0

    if not args.report:
        print("import needs a report JSON path", file=sys.stderr)
        return 2
    try:
        new = from_report(json.loads(Path(args.report).read_text()))
    except (ValueError, OSError) as err:
        print(f"Could not import: {err}", file=sys.stderr)
        return 2
    by_key = {key(r): r for r in hist["rejections"]}
    added = 0
    for r in new:
        k = key(r)
        if k not in by_key:
            added += 1
        by_key[k] = {**by_key.get(k, {}), **{x: r[x] for x in KEEP if x in r}}
    hist["rejections"] = list(by_key.values())
    hist["updated"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(hist, indent=2, ensure_ascii=False))
    print(f"Saved {added} new rejection(s), {len(hist['rejections'])} total, to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
