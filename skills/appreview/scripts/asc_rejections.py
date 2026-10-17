#!/usr/bin/env python3
"""List every app in an App Store Connect account and find its rejections.

What the public API can tell us (read-only GETs):
  * review submissions per app and their state (UNRESOLVED_ISSUES = rejected /
    needs developer action) plus the items inside each submission
  * App Store version states (REJECTED, METADATA_REJECTED, INVALID_BINARY)
  * the build attached to a version and the App Review Information you submitted

What it CANNOT tell us: the Resolution Center message (guideline number and
reviewer explanation). Apple does not expose it in the public API. The report
marks every finding with `needs_resolution_center_text: true` so the next step
(reading the message in the browser, or the user pasting it) is explicit.

Usage:
    python asc_rejections.py [--app NAME_OR_BUNDLE_OR_ID ...] [--since-days 730]
                             [--no-history] [--out DIR] [--json]

Writes DIR/rejections.json and DIR/rejections.md (default ./asc-rejections-report)
and prints a short summary. Exit codes: 0 ok, 2 config/credentials, 3 API error.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from asc_auth import AscApiError, AscClient, AscConfigError, load_credentials  # noqa: E402

ITEM_INCLUDE_CHAIN = [
    "appStoreVersion,appCustomProductPageVersion,appEvent,appStoreVersionExperimentV2,"
    "inAppPurchaseVersion,subscriptionVersion,subscriptionGroupVersion",
    "appStoreVersion",
    None,  # last resort: no include, kind stays unknown
]


# --------------------------------------------------------------------------- helpers
def looks_rejected_version_state(state: Optional[str]) -> bool:
    """True for states App Review produced. DEVELOPER_REJECTED means the developer
    withdrew the submission themselves, so it is not a rejection."""
    s = (state or "").upper()
    if s == "DEVELOPER_REJECTED":
        return False
    return "REJECT" in s or s == "INVALID_BINARY"


def submission_needs_attention(state: Optional[str]) -> bool:
    return "UNRESOLVED" in (state or "").upper()


def parse_date(value: Optional[str]) -> Optional[dt.datetime]:
    if not value:
        return None
    try:
        d = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return None


def within(value: Optional[str], since: Optional[dt.datetime]) -> bool:
    d = parse_date(value)
    return True if (since is None or d is None) else d >= since


def index_included(included: List[Dict[str, Any]]) -> Dict[tuple, Dict[str, Any]]:
    return {(r.get("type"), r.get("id")): r for r in included}


def matches(app: Dict[str, Any], needles: List[str]) -> bool:
    if not needles:
        return True
    a = app.get("attributes", {})
    hay = [app.get("id", ""), a.get("name", ""), a.get("bundleId", ""), a.get("sku", "")]
    return any(n.lower() in h.lower() for n in needles for h in hay if h)


def app_url(app_id: str) -> str:
    return f"https://appstoreconnect.apple.com/apps/{app_id}"


# --------------------------------------------------------------------------- fetchers
def fetch_items(client: AscClient, submission_id: str) -> List[Dict[str, Any]]:
    """Items of one review submission, with whatever target info the API will include."""
    last_err: Optional[AscApiError] = None
    for include in ITEM_INCLUDE_CHAIN:
        try:
            params = {"limit": 200}
            if include:
                params["include"] = include
            rows, included = client.collect(f"/v1/reviewSubmissions/{submission_id}/items", params)
            break
        except AscApiError as err:
            if err.status == 400:  # include list not accepted -> try the narrower one
                last_err = err
                continue
            raise
    else:
        raise last_err or AscApiError(400, [], submission_id)

    inc = index_included(included)
    items = []
    for row in rows:
        attrs = row.get("attributes", {})
        kind, target = "unknown", None
        for rel_name, rel in (row.get("relationships") or {}).items():
            data = rel.get("data") if isinstance(rel, dict) else None
            if isinstance(data, dict) and data.get("id"):
                kind = rel_name
                res = inc.get((data.get("type"), data.get("id")), {})
                keep = {k: v for k, v in (res.get("attributes") or {}).items()
                        if k in ("versionString", "appStoreState", "appVersionState", "platform",
                                 "name", "referenceName", "productId", "state", "reviewNote")}
                target = {"type": data.get("type"), "id": data.get("id"), **keep}
                break
        items.append({"id": row.get("id"), "state": attrs.get("state"), "kind": kind, "target": target})
    return items


def summarize_review_detail(res: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Describe App Review Information WITHOUT copying credentials or contact details."""
    if not res:
        return None
    a = res.get("attributes", {})
    return {
        "demo_account_required": a.get("demoAccountRequired"),
        "has_demo_account_name": bool(a.get("demoAccountName")),
        "has_demo_account_password": bool(a.get("demoAccountPassword")),
        "has_contact_email": bool(a.get("contactEmail")),
        "has_contact_phone": bool(a.get("contactPhone")),
        "notes": a.get("notes"),
    }


def fetch_versions(client: AscClient, app_id: str) -> List[Dict[str, Any]]:
    params = {"limit": 200, "include": "build,appStoreReviewDetail"}
    try:
        rows, included = client.collect(f"/v1/apps/{app_id}/appStoreVersions", params)
    except AscApiError as err:
        if err.status != 400:
            raise
        rows, included = client.collect(f"/v1/apps/{app_id}/appStoreVersions", {"limit": 200})
    inc = index_included(included)
    out = []
    for row in rows:
        a = row.get("attributes", {})
        rels = row.get("relationships") or {}

        def target(rel: str) -> Optional[Dict[str, Any]]:
            data = (rels.get(rel) or {}).get("data")
            return inc.get((data.get("type"), data.get("id"))) if isinstance(data, dict) else None

        build = target("build")
        b = (build or {}).get("attributes", {})
        out.append({
            "id": row.get("id"),
            "platform": a.get("platform"),
            "version": a.get("versionString"),
            "state": a.get("appVersionState") or a.get("appStoreState"),
            "created": a.get("createdDate"),
            "build": {"number": b.get("version"), "uploaded": b.get("uploadedDate"),
                      "min_os": b.get("minOsVersion")} if build else None,
            "review_detail": summarize_review_detail(target("appStoreReviewDetail")),
        })
    return out


def analyze_app(client: AscClient, app: Dict[str, Any], since: Optional[dt.datetime],
                history: bool) -> Dict[str, Any]:
    app_id = app["id"]
    a = app.get("attributes", {})
    result: Dict[str, Any] = {
        "app_id": app_id, "name": a.get("name"), "bundle_id": a.get("bundleId"),
        "url": app_url(app_id), "rejections": [], "notes": [],
    }

    versions = fetch_versions(client, app_id)
    by_version_id = {v["id"]: v for v in versions}

    subs, _ = client.collect(f"/v1/apps/{app_id}/reviewSubmissions", {"limit": 200})
    covered_versions = set()
    for sub in sorted(subs, key=lambda s: s.get("attributes", {}).get("submittedDate") or "", reverse=True):
        sa = sub.get("attributes", {})
        current = submission_needs_attention(sa.get("state"))
        if not current and not (history and within(sa.get("submittedDate"), since)):
            continue
        items = fetch_items(client, sub["id"])
        rejected_items = [i for i in items if "REJECT" in (i["state"] or "").upper()]
        if not current and not rejected_items:
            continue
        for it in items:
            tid = (it.get("target") or {}).get("id")
            if tid in by_version_id and ("REJECT" in (it["state"] or "").upper() or current):
                covered_versions.add(tid)
        result["rejections"].append({
            "source": "reviewSubmission",
            "submission_id": sub["id"],
            "platform": sa.get("platform"),
            "submitted": sa.get("submittedDate"),
            "state": sa.get("state"),
            "status": "OPEN - needs developer action" if current else "past (item was rejected)",
            "items": items,
            "needs_resolution_center_text": True,
        })

    for v in versions:
        if looks_rejected_version_state(v["state"]) and v["id"] not in covered_versions:
            if not within(v["created"], since):
                continue
            result["rejections"].append({
                "source": "appStoreVersion", "version_id": v["id"], "platform": v["platform"],
                "version": v["version"], "state": v["state"], "created": v["created"],
                "status": "OPEN - needs developer action", "build": v["build"],
                "review_detail": v["review_detail"], "needs_resolution_center_text": True,
            })

    # Attach version/build/review-detail context to submission findings.
    for r in result["rejections"]:
        if r["source"] != "reviewSubmission":
            continue
        for it in r["items"]:
            v = by_version_id.get((it.get("target") or {}).get("id"))
            if v:
                it["version_context"] = {"version": v["version"], "build": v["build"],
                                         "review_detail": v["review_detail"]}
    return result


# --------------------------------------------------------------------------- reporting
def render_markdown(report: Dict[str, Any]) -> str:
    lines = [f"# App Store Connect rejection scan", "",
             f"Generated {report['generated']} - {report['apps_scanned']} apps scanned, "
             f"{report['apps_with_rejections']} with rejections or open issues.", ""]
    if not report["apps_with_rejections"]:
        lines.append("No rejections or Unresolved Issues found in the scanned window.")
    for app in report["apps"]:
        if not app["rejections"]:
            continue
        lines += [f"## {app['name']} (`{app['bundle_id']}`)", f"Open in App Store Connect: {app['url']}", ""]
        for r in app["rejections"]:
            if r["source"] == "reviewSubmission":
                lines.append(f"- **Submission {r['submission_id'][:8]}** ({r['platform']}) - state "
                             f"`{r['state']}`, submitted {r['submitted'] or 'n/a'} - {r['status']}")
                for it in r["items"]:
                    t = it.get("target") or {}
                    label = t.get("versionString") or t.get("name") or t.get("id") or "?"
                    lines.append(f"  - item `{it['state']}` - {it['kind']} {label}")
            else:
                b = r.get("build") or {}
                lines.append(f"- **Version {r['version']}** ({r['platform']}) - state `{r['state']}`, "
                             f"build {b.get('number', 'n/a')} - {r['status']}")
        lines += ["", "_Guideline number and reviewer message are not in the API: read the "
                      "Resolution Center for this app (see references/resolution-center.md)._", ""]
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--app", action="append", default=[], help="filter by name, bundle ID, SKU or app ID (repeatable)")
    p.add_argument("--since-days", type=int, default=730, help="history window for past rejections (default 730)")
    p.add_argument("--no-history", action="store_true", help="only report currently open rejections")
    p.add_argument("--out", default="asc-rejections-report", help="output directory")
    p.add_argument("--json", action="store_true", help="print full JSON to stdout instead of a summary")
    p.add_argument("--base-url", default=None, help="override API base URL (testing)")
    args = p.parse_args(argv)

    try:
        client = AscClient(load_credentials(), base_url=args.base_url)
        since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=args.since_days)
        apps, _ = client.collect("/v1/apps", {"limit": 200})
        apps = [a for a in apps if matches(a, args.app)]
        results = []
        for app in apps:
            try:
                results.append(analyze_app(client, app, since, history=not args.no_history))
            except AscApiError as err:
                attrs = app.get("attributes", {})
                results.append({"app_id": app["id"], "name": attrs.get("name"),
                                "bundle_id": attrs.get("bundleId"), "url": app_url(app["id"]),
                                "rejections": [], "notes": [f"Could not scan: {err} {err.hint()}"]})
    except AscConfigError as err:
        print(f"Config error: {err}", file=sys.stderr)
        return 2
    except AscApiError as err:
        print(f"{err}\n{err.hint()}", file=sys.stderr)
        return 3

    report = {
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "apps_scanned": len(results),
        "apps_with_rejections": sum(1 for r in results if r["rejections"]),
        "api_requests": client.request_count,
        "limitations": [
            "Resolution Center messages (guideline numbers, reviewer text) are not available "
            "through the public API.",
            "Past rejections that were later fixed and approved may leave no trace in the API.",
        ],
        "apps": results,
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "rejections.json").write_text(json.dumps(report, indent=2))
    (out / "rejections.md").write_text(render_markdown(report))

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render_markdown(report))
        print(f"\nSaved: {out / 'rejections.json'} and {out / 'rejections.md'}")
    for r in results:
        for n in r["notes"]:
            print(f"warning: {r['name']}: {n}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
