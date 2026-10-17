#!/usr/bin/env python3
"""Offline self-test: runs the scripts against a local mock of the App Store Connect API.

No network, no real key. Generates a throwaway P-256 key, starts a mock server that
checks the JWT signature on every request, and asserts the scan and parser output.

    python scripts/selftest.py
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

HERE = Path(__file__).resolve().parent
KEY = ec.generate_private_key(ec.SECP256R1())
PUB = KEY.public_key()
SEEN = {"paths": [], "methods": set(), "auth_ok": 0}


def b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def verify_jwt(token: str) -> dict:
    h, p, s = token.split(".")
    sig = b64d(s)
    der = encode_dss_signature(int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big"))
    PUB.verify(der, f"{h}.{p}".encode(), ec.ECDSA(hashes.SHA256()))
    header, payload = json.loads(b64d(h)), json.loads(b64d(p))
    assert header == {"alg": "ES256", "kid": "TESTKEY123", "typ": "JWT"}, header
    assert payload["aud"] == "appstoreconnect-v1"
    assert payload["iss"] == "issuer-uuid"
    assert 0 < payload["exp"] - payload["iat"] <= 1200
    return payload


def ver(id_, vs, state, created, build=None, detail=None):
    rel = {}
    if build:
        rel["build"] = {"data": {"type": "builds", "id": build}}
    if detail:
        rel["appStoreReviewDetail"] = {"data": {"type": "appStoreReviewDetails", "id": detail}}
    return {"type": "appStoreVersions", "id": id_, "relationships": rel,
            "attributes": {"platform": "IOS", "versionString": vs, "appStoreState": state,
                           "appVersionState": state, "createdDate": created}}


BASE = None  # set at runtime
APPS = [
    {"type": "apps", "id": "111", "attributes": {"name": "Alpha Notes", "bundleId": "com.ex.alpha", "sku": "A"}},
    {"type": "apps", "id": "222", "attributes": {"name": "Beta Timer", "bundleId": "com.ex.beta", "sku": "B"}},
    {"type": "apps", "id": "333", "attributes": {"name": "Clean App", "bundleId": "com.ex.clean", "sku": "C"}},
]
VERSIONS = {
    "111": [ver("v-a2", "2.0", "REJECTED", "2026-09-30T10:00:00-07:00", "b-a2", "d-a2"),
            ver("v-a1", "1.9", "READY_FOR_DISTRIBUTION", "2026-05-01T10:00:00-07:00")],
    "222": [ver("v-b1", "1.0", "METADATA_REJECTED", "2026-10-01T10:00:00-07:00"),
            ver("v-b0", "0.9", "DEVELOPER_REJECTED", "2026-08-01T10:00:00-07:00")],
    "333": [ver("v-c1", "3.1", "READY_FOR_DISTRIBUTION", "2026-07-01T10:00:00-07:00")],
}
INCLUDED_VERSIONS = [
    {"type": "builds", "id": "b-a2", "attributes": {"version": "45", "uploadedDate": "2026-09-29T00:00:00Z", "minOsVersion": "17.0"}},
    {"type": "appStoreReviewDetails", "id": "d-a2", "attributes": {
        "demoAccountRequired": True, "demoAccountName": "reviewer@ex.com", "demoAccountPassword": "",
        "contactEmail": "dev@ex.com", "contactPhone": "+1 555", "notes": "Log in with the demo account."}},
]
SUBS = {
    "111": [
        {"type": "reviewSubmissions", "id": "sub-a-open", "attributes": {"platform": "IOS", "submittedDate": "2026-10-01T00:00:00Z", "state": "UNRESOLVED_ISSUES"}},
        {"type": "reviewSubmissions", "id": "sub-a-old", "attributes": {"platform": "IOS", "submittedDate": "2026-04-20T00:00:00Z", "state": "COMPLETE"}},
        {"type": "reviewSubmissions", "id": "sub-a-ancient", "attributes": {"platform": "IOS", "submittedDate": "2019-01-01T00:00:00Z", "state": "COMPLETE"}},
    ],
    "222": [],
    "333": [{"type": "reviewSubmissions", "id": "sub-c", "attributes": {"platform": "IOS", "submittedDate": "2026-07-01T00:00:00Z", "state": "COMPLETE"}}],
}
ITEMS = {
    "sub-a-open": ([
        {"type": "reviewSubmissionItems", "id": "it1", "attributes": {"state": "REJECTED"},
         "relationships": {"appStoreVersion": {"data": {"type": "appStoreVersions", "id": "v-a2"}}}},
        {"type": "reviewSubmissionItems", "id": "it2", "attributes": {"state": "REJECTED"},
         "relationships": {"subscriptionVersion": {"data": {"type": "subscriptionVersions", "id": "sv1"}}}},
    ], [{"type": "appStoreVersions", "id": "v-a2", "attributes": {"versionString": "2.0", "appStoreState": "REJECTED", "platform": "IOS"}}]),
    "sub-a-old": ([
        {"type": "reviewSubmissionItems", "id": "it3", "attributes": {"state": "REJECTED"},
         "relationships": {"appStoreVersion": {"data": {"type": "appStoreVersions", "id": "v-a1"}}}},
    ], []),
    "sub-a-ancient": ([{"type": "reviewSubmissionItems", "id": "it4", "attributes": {"state": "REJECTED"}, "relationships": {}}], []),
    "sub-c": ([{"type": "reviewSubmissionItems", "id": "it5", "attributes": {"state": "APPROVED"},
                "relationships": {"appStoreVersion": {"data": {"type": "appStoreVersions", "id": "v-c1"}}}}], []),
}


class Mock(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        SEEN["methods"].add("GET")
        auth = self.headers.get("Authorization", "")
        try:
            verify_jwt(auth.removeprefix("Bearer "))
            SEEN["auth_ok"] += 1
        except Exception as exc:  # noqa: BLE001
            return self.send(401, {"errors": [{"title": "NOT_AUTHORIZED", "detail": str(exc)}]})
        u = urlsplit(self.path)
        q = parse_qs(u.query)
        SEEN["paths"].append(self.path)
        parts = u.path.strip("/").split("/")
        if u.path == "/v1/apps":
            # two pages, to exercise pagination
            if q.get("cursor") == ["p2"]:
                return self.send(200, {"data": APPS[2:], "links": {}})
            return self.send(200, {"data": APPS[:2], "links": {"next": f"{BASE}/v1/apps?cursor=p2&limit=200"}})
        if len(parts) == 4 and parts[:2] == ["v1", "apps"] and parts[3] == "appStoreVersions":
            return self.send(200, {"data": VERSIONS[parts[2]], "included": INCLUDED_VERSIONS, "links": {}})
        if len(parts) == 4 and parts[:2] == ["v1", "apps"] and parts[3] == "reviewSubmissions":
            return self.send(200, {"data": SUBS[parts[2]], "links": {}})
        if len(parts) == 4 and parts[:2] == ["v1", "reviewSubmissions"] and parts[3] == "items":
            inc = q.get("include", [""])[0]
            if "," in inc:  # simulate Apple rejecting a long include list -> fallback path
                return self.send(400, {"errors": [{"title": "PARAMETER_ERROR.INVALID", "detail": "include"}]})
            data, included = ITEMS[parts[2]]
            return self.send(200, {"data": data, "included": included if inc else [], "links": {}})
        return self.send(404, {"errors": [{"title": "NOT_FOUND"}]})

    def do_POST(self):  # the client must never do this
        SEEN["methods"].add("POST")
        self.send(405, {})

    do_PATCH = do_DELETE = do_POST


SAMPLE_MESSAGE = """Hello,

Thank you for your resubmission. Upon further review, we identified additional issues.

Submission ID: 7f1c2a9e-1111-2222-3333-444455556666
Review date: October 02, 2026
Version reviewed: 2.0

Guideline 2.1 - Performance - App Completeness

We were unable to sign in with the demo account credentials you provided. The password field was empty.

Next Steps
Please provide a valid demo account and password in the App Review Information section.

Guideline 5.1.1(v) - Legal - Privacy - Data Collection and Storage

The app supports account creation but does not include an option to initiate account deletion.

Next Steps
Add an account deletion option in the app. Then upload a new binary.

Review device details:
- Device type: iPhone 17
- OS version: iOS 26.1
"""


def main() -> int:
    global BASE
    server = HTTPServer(("127.0.0.1", 0), Mock)
    BASE = f"http://127.0.0.1:{server.server_port}"
    threading.Thread(target=server.serve_forever, daemon=True).start()

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        keyfile = tmp / "AuthKey_TESTKEY123.p8"
        keyfile.write_bytes(KEY.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                              serialization.NoEncryption()))
        env = {**os.environ, "ASC_KEY_ID": "TESTKEY123", "ASC_ISSUER_ID": "issuer-uuid",
               "ASC_PRIVATE_KEY_PATH": str(keyfile), "ASC_BASE_URL": BASE}

        # 1. credential check
        r = subprocess.run([sys.executable, str(HERE / "asc_auth.py")], env=env, capture_output=True, text=True)
        assert r.returncode == 0 and "OK: authenticated" in r.stdout, r.stdout + r.stderr

        # 2. full scan
        out = tmp / "report"
        r = subprocess.run([sys.executable, str(HERE / "asc_rejections.py"), "--out", str(out)],
                           env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        rep = json.loads((out / "rejections.json").read_text())
        apps = {a["name"]: a for a in rep["apps"]}
        assert rep["apps_scanned"] == 3, "pagination failed"
        assert rep["apps_with_rejections"] == 2

        alpha = apps["Alpha Notes"]["rejections"]
        ids = [x.get("submission_id") or x.get("version_id") for x in alpha]
        assert ids == ["sub-a-open", "sub-a-old"], ids  # ancient one is outside the window
        open_sub = alpha[0]
        assert open_sub["status"].startswith("OPEN")
        kinds = sorted(i["kind"] for i in open_sub["items"])
        assert kinds == ["appStoreVersion", "subscriptionVersion"], kinds
        ctx = next(i for i in open_sub["items"] if i["kind"] == "appStoreVersion")["version_context"]
        assert ctx["build"]["number"] == "45"
        rd = ctx["review_detail"]
        assert rd["demo_account_required"] is True and rd["has_demo_account_password"] is False
        dumped = json.dumps(rep)
        assert "reviewer@ex.com" not in dumped and "dev@ex.com" not in dumped and "+1 555" not in dumped, "PII leaked"
        # v-a2 is covered by the submission, so no duplicate version finding
        assert not any(x.get("version_id") == "v-a2" for x in alpha)

        beta = apps["Beta Timer"]["rejections"]
        assert [x["state"] for x in beta] == ["METADATA_REJECTED"], beta  # DEVELOPER_REJECTED excluded
        assert apps["Clean App"]["rejections"] == []
        assert "Alpha Notes" in (out / "rejections.md").read_text()

        # 3. --no-history + --app filter
        r = subprocess.run([sys.executable, str(HERE / "asc_rejections.py"), "--out", str(tmp / "r2"),
                            "--app", "alpha", "--no-history"], env=env, capture_output=True, text=True)
        rep2 = json.loads((tmp / "r2" / "rejections.json").read_text())
        assert rep2["apps_scanned"] == 1
        assert [x["submission_id"] for x in rep2["apps"][0]["rejections"]] == ["sub-a-open"]

        # 4. bad credentials -> clean 401 message, exit 3
        bad = {**env, "ASC_ISSUER_ID": "wrong"}
        r = subprocess.run([sys.executable, str(HERE / "asc_auth.py")], env=bad, capture_output=True, text=True)
        assert r.returncode == 3 and "401" in r.stderr, r.stderr
        # missing key id -> exit 2
        r = subprocess.run([sys.executable, str(HERE / "asc_auth.py")], env={**env, "ASC_KEY_ID": ""},
                           capture_output=True, text=True)
        assert r.returncode == 2

        # 5. parser
        msg = tmp / "rc.txt"
        msg.write_text(SAMPLE_MESSAGE)
        r = subprocess.run([sys.executable, str(HERE / "parse_rejection.py"), str(msg), "--playbook"],
                           capture_output=True, text=True)
        parsed = json.loads(r.stdout)
        g = parsed["guidelines"]
        assert [x["guideline"] for x in g] == ["2.1", "5.1.1(v)"], g
        assert "demo account" in g[0]["explanation"]
        assert "Review device" not in g[1]["explanation"]
        assert g[0]["playbook_match"] == "2.1" and g[1]["playbook_match"] == "5.1.1"
        assert parsed["submission_id"].startswith("7f1c2a9e") and parsed["version_reviewed"] == "2.0"
        assert parsed["hints"]["mentions_demo_account"] and parsed["hints"]["mentions_new_binary"]

        # 6. preflight scanner on a small fake project
        proj = tmp / "Proj"
        (proj / "App").mkdir(parents=True)
        (proj / "Pods" / "X").mkdir(parents=True)
        (proj / "App" / "Info.plist").write_text(
            '<?xml version="1.0" encoding="UTF-8"?><plist version="1.0"><dict>'
            '<key>CFBundleIdentifier</key><string>com.ex.p</string></dict></plist>')
        (proj / "App" / "A.swift").write_text(
            'import AVFoundation\nlet d = AVCaptureDevice.default(for: .video)\n'
            'func r(){ Auth.auth().createUser(withEmail: e, password: p) { _, _ in } }\n'
            '// coming soon (comment, ignored)\n'
            'let k = "https://localhost:3000/ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"\n')
        (proj / "Pods" / "X" / "Y.swift").write_text("LSApplicationWorkspace\n")
        r = subprocess.run([sys.executable, str(HERE / "preflight_scan.py"), str(proj)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        pf = json.loads(r.stdout)
        ids = {f["id"] for f in pf["findings"]}
        for want in ("purpose-missing-NSCameraUsageDescription", "account-deletion", "dev-endpoints", "privacy-link"):
            assert want in ids, (want, ids)
        assert "private-api" not in ids and "placeholders" not in ids, ids  # Pods + comments skipped
        assert "ABCDEFGHIJKLMNOPQRSTUVWXYZ" not in r.stdout, "long token not masked"

        # 6b. history import (deduped) and comparison against the project
        (proj / "App.xcodeproj").mkdir()
        (proj / "App.xcodeproj" / "project.pbxproj").write_text("PRODUCT_BUNDLE_IDENTIFIER = com.ex.p;\n")
        past = {"kind": "rejections", "generated": "2026-06-01", "groups": [
            {"name": "P", "bundle_id": "com.ex.p", "version": "1.0", "findings": [
                {"guideline": "5.1.1(v)", "title": "Account deletion", "said": "no option to initiate account deletion"},
                {"guideline": "2.1", "title": "App Completeness", "said": "the demo account password was empty"}]},
            {"name": "Other", "bundle_id": "com.ex.o", "findings": [
                {"guideline": "4.3", "title": "Spam", "said": "similar to other apps"}]}]}
        pj, hf = tmp / "past.json", tmp / "hist.json"
        pj.write_text(json.dumps(past))
        for _ in range(2):
            subprocess.run([sys.executable, str(HERE / "history.py"), "import", str(pj), "--file", str(hf)], check=True, capture_output=True)
        assert len(json.loads(hf.read_text())["rejections"]) == 3, "history not deduped"
        r = subprocess.run([sys.executable, str(HERE / "preflight_scan.py"), str(proj), "--history", str(hf)], capture_output=True, text=True)
        hc = {h["guideline"]: h for h in json.loads(r.stdout)["history_check"]}
        assert hc["5.1.1(v)"]["verdict"] == "repeat_risk" and hc["5.1.1(v)"]["same_app"], hc["5.1.1(v)"]
        assert hc["5.1.1(v)"]["same_cause_findings"] == ["account-deletion"]
        assert hc["2.1"]["verdict"] == "related_area", hc["2.1"]       # dev URL is 2.1 but not the demo-account cause
        assert hc["4.3"]["verdict"] == "check_by_hand" and not hc["4.3"]["same_app"]

        # 7. renderer escapes third-party text
        rep = {"kind": "rejections", "title": "T", "groups": [{"name": "<img src=x onerror=alert(1)>",
               "link": "javascript:alert(1)", "findings": [{"guideline": "2.1", "title": "x", "status": "open",
               "said": "</style><script>alert(1)</script>", "reply": "a & b"}]}]}
        rj = tmp / "rep.json"
        rj.write_text(json.dumps(rep))
        subprocess.run([sys.executable, str(HERE / "render_report.py"), str(rj), "--out", str(tmp / "r.html")], check=True,
                       capture_output=True)
        page = (tmp / "r.html").read_text()
        assert "<img src=x" not in page and "<script>alert" not in page and "javascript:" not in page
        assert page.startswith("<title>T</title>")
        sys.path.insert(0, str(HERE))
        from render_report import guideline_html
        assert guideline_html("5.6.1 / 5.6.3") == "<span>5.6.1 /</span> <span>5.6.3</span>", guideline_html("5.6.1 / 5.6.3")
        assert guideline_html("2.1, 5.1.1(v)") == "<span>2.1,</span> <span>5.1.1(v)</span>"

    assert SEEN["methods"] == {"GET"}, f"non-GET request made: {SEEN['methods']}"
    server.shutdown()
    print(f"selftest OK - {SEEN['auth_ok']} signed requests verified, GET only")
    return 0


if __name__ == "__main__":
    sys.exit(main())
