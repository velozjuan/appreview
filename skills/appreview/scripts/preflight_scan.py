#!/usr/bin/env python3
"""Pre-submission check: scan an iOS app project for likely App Review problems.

Static heuristics, not a verdict. Each finding is a *candidate* with evidence
(file, line, snippet) that the assistant must confirm by reading the code before
reporting it. Works on native Swift/Obj-C projects and on React Native, Expo,
Flutter and Capacitor projects (it reads their iOS folder, config and source).

    python preflight_scan.py /path/to/project [--out preflight.json]

Read-only: it never modifies the project. Snippets are trimmed and long tokens
masked so API keys in source code don't end up in the report.
"""
from __future__ import annotations

import argparse
import json
import plistlib
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

SKIP_DIRS = {"Pods", "node_modules", ".build", "DerivedData", "build", "Carthage", ".git",
             "vendor", ".dart_tool", ".gradle", "android", ".expo", "dist", "Build", ".swiftpm",
             "xcuserdata", "fastlane", "Tests", "UITests"}
CODE_EXT = {".swift", ".m", ".mm", ".h", ".js", ".jsx", ".ts", ".tsx", ".dart", ".vue"}
MANIFESTS = {"Podfile", "Podfile.lock", "Package.resolved", "Package.swift", "package.json",
             "pubspec.yaml", "Cartfile", "project.pbxproj"}
MAX_FILE_BYTES = 1_500_000
MAX_EVIDENCE = 4

# (plist key, code pattern that needs it, what it is)
PURPOSE_KEYS = [
    ("NSCameraUsageDescription", r"AVCaptureDevice|UIImagePickerController\b.*camera|\.camera\b.*sourceType|expo-camera|react-native-vision-camera|image_picker|CameraView", "camera"),
    ("NSMicrophoneUsageDescription", r"AVAudioRecorder|AVAudioSession.*record|requestRecordPermission|expo-av|react-native-audio|record\(\)", "microphone"),
    ("NSPhotoLibraryUsageDescription", r"PHPhotoLibrary|PHAsset\b|UIImagePickerController|expo-media-library|CameraRoll|image_picker", "photo library"),
    ("NSPhotoLibraryAddUsageDescription", r"UIImageWriteToSavedPhotosAlbum|PHAssetChangeRequest|saveToLibraryAsync", "saving to photos"),
    ("NSLocationWhenInUseUsageDescription", r"CLLocationManager|requestWhenInUseAuthorization|expo-location|geolocator|navigator\.geolocation", "location"),
    ("NSLocationAlwaysAndWhenInUseUsageDescription", r"requestAlwaysAuthorization|startMonitoringSignificantLocationChanges|allowsBackgroundLocationUpdates", "background location"),
    ("NSContactsUsageDescription", r"CNContactStore|expo-contacts|react-native-contacts", "contacts"),
    ("NSCalendarsUsageDescription", r"EKEventStore|expo-calendar", "calendars"),
    ("NSBluetoothAlwaysUsageDescription", r"CBCentralManager|CBPeripheralManager|react-native-ble|flutter_blue", "Bluetooth"),
    ("NSFaceIDUsageDescription", r"LAContext|biometryType|expo-local-authentication|local_auth", "Face ID"),
    ("NSSpeechRecognitionUsageDescription", r"SFSpeechRecognizer", "speech recognition"),
    ("NSMotionUsageDescription", r"CMMotionActivityManager|CMPedometer", "motion"),
    ("NSHealthShareUsageDescription", r"HKHealthStore", "HealthKit"),
    ("NSUserTrackingUsageDescription", r"ATTrackingManager|requestTrackingAuthorization|expo-tracking-transparency", "tracking"),
]

# Required-reason APIs -> NSPrivacyAccessedAPIType
REQUIRED_REASON = [
    ("NSPrivacyAccessedAPICategoryUserDefaults", r"\bUserDefaults\b|NSUserDefaults|AsyncStorage|shared_preferences|@AppStorage"),
    ("NSPrivacyAccessedAPICategoryFileTimestamp", r"creationDate|modificationDate|\.fileModificationDate|NSFileModificationDate|getattrlist|\bstat\("),
    ("NSPrivacyAccessedAPICategorySystemBootTime", r"systemUptime|mach_absolute_time"),
    ("NSPrivacyAccessedAPICategoryDiskSpace", r"volumeAvailableCapacity|NSFileSystemFreeSize|systemFreeSize"),
    ("NSPrivacyAccessedAPICategoryActiveKeyboards", r"activeInputModes"),
]

TRACKING_SDKS = r"Google-Mobile-Ads|GoogleMobileAds|google_mobile_ads|react-native-google-mobile-ads|FBAudienceNetwork|AppsFlyer|appsflyer|Adjust|adjust_sdk|AppLovin|applovin|UnityAds|unity-ads|IronSource|Vungle|Branch"
GENERIC_PURPOSE = re.compile(r"^\s*(?:\$\(.*\)|.{0,24}|.*\b(?:needs?|requires?|uses?) (?:access|permission)\.?|this app (?:needs|requires|uses) .{0,20}|for (?:app )?functionality\.?)\s*$", re.I)


def masked(s: str) -> str:
    s = re.sub(r"[A-Za-z0-9_\-+/=]{28,}", "…", s.strip())
    return s[:160]


class Project:
    def __init__(self, root: Path):
        self.root = root
        self.code: List[Tuple[Path, List[str]]] = []
        self.manifest_text = ""
        self.plists: Dict[Path, dict] = {}
        self.privacy_manifests: Dict[Path, dict] = {}
        self.extra_plist_keys: Dict[str, Tuple[str, str]] = {}  # key -> (value, source)
        self.kind = "native"
        self.bundle_ids: set = set()
        self._load()

    def rel(self, p: Path) -> str:
        try:
            return str(p.relative_to(self.root))
        except ValueError:
            return str(p)

    def _walk(self) -> Iterable[Path]:
        stack = [self.root]
        while stack:
            d = stack.pop()
            try:
                entries = list(d.iterdir())
            except OSError:
                continue
            for e in entries:
                if e.is_dir():
                    if e.name in SKIP_DIRS or (e.name.startswith(".") and e.name != ".") or e.suffix in (".xcassets", ".lproj"):
                        continue
                    if e.suffix == ".xcodeproj":
                        pbx = e / "project.pbxproj"
                        if pbx.is_file():
                            yield pbx
                        continue
                    stack.append(e)
                else:
                    yield e

    def _load(self) -> None:
        for f in self._walk():
            try:
                if f.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            name, ext = f.name, f.suffix
            if name in MANIFESTS:
                text = f.read_text(errors="replace")
                self.manifest_text += f"\n# {self.rel(f)}\n" + text
                if name == "project.pbxproj":
                    for m in re.finditer(r'PRODUCT_BUNDLE_IDENTIFIER\s*=\s*"?([\w.\-]+)"?;', text):
                        self.bundle_ids.add(m.group(1))
                    for m in re.finditer(r'INFOPLIST_KEY_(NS\w+UsageDescription)\s*=\s*"?([^";]*)"?;', text):
                        self.extra_plist_keys.setdefault(m.group(1), (m.group(2), self.rel(f)))
                if name == "pubspec.yaml":
                    self.kind = "flutter"
                if name == "package.json" and '"react-native"' in text:
                    self.kind = "react-native" if self.kind == "native" else self.kind
            if name in ("app.json", "app.config.json") or name.startswith("app.config."):
                text = f.read_text(errors="replace")
                self.manifest_text += f"\n# {self.rel(f)}\n" + text
                for m in re.finditer(r'"bundleIdentifier"\s*:\s*"([\w.\-]+)"', text):
                    self.bundle_ids.add(m.group(1))
                if '"expo"' in text or "expo" in name:
                    self.kind = "expo"
                for m in re.finditer(r'"?(NS\w+UsageDescription)"?\s*:\s*"([^"]*)"', text):
                    self.extra_plist_keys.setdefault(m.group(1), (m.group(2), self.rel(f)))
                for m in re.finditer(r'"?(NS\w+UsageDescription)"?\s*:', text):
                    self.extra_plist_keys.setdefault(m.group(1), ("(set in config)", self.rel(f)))
            if ext == ".plist" and name not in ("GoogleService-Info.plist",):
                try:
                    data = plistlib.loads(f.read_bytes())
                    if isinstance(data, dict) and ("CFBundleIdentifier" in data or any(k.startswith("NS") for k in data)):
                        self.plists[f] = data
                        bid = str(data.get("CFBundleIdentifier", ""))
                        if bid and "$(" not in bid:
                            self.bundle_ids.add(bid)
                except Exception:  # noqa: BLE001
                    pass
            if ext == ".xcprivacy":
                try:
                    self.privacy_manifests[f] = plistlib.loads(f.read_bytes())
                except Exception:  # noqa: BLE001
                    self.privacy_manifests[f] = {}
            if ext in CODE_EXT:
                try:
                    self.code.append((f, f.read_text(errors="replace").splitlines()))
                except OSError:
                    pass

    # -- search helpers -----------------------------------------------------
    def grep(self, pattern: str, flags=0, limit: int = MAX_EVIDENCE, strings_only: bool = False) -> List[dict]:
        rx = re.compile(pattern, flags)
        hits = []
        for f, lines in self.code:
            for i, line in enumerate(lines, 1):
                s = line.strip()
                if s.startswith(("//", "*", "/*")) or (s.startswith("#") and f.suffix not in (".m", ".mm", ".h")):
                    continue
                if strings_only:
                    lits = re.findall(r'"([^"\n]{2,})"|\'([^\'\n]{2,})\'', line)
                    target = " ".join(a or b for a, b in lits)
                    if not target or not rx.search(target):
                        continue
                elif not rx.search(line):
                    continue
                hits.append({"file": self.rel(f), "line": i, "snippet": masked(line)})
                if len(hits) >= limit:
                    return hits
        return hits

    def has(self, pattern: str, flags=0) -> bool:
        return bool(self.grep(pattern, flags, limit=1))

    def in_manifests(self, pattern: str) -> List[str]:
        return sorted(set(m.group(0) for m in re.finditer(pattern, self.manifest_text)))

    def plist_value(self, key: str) -> Optional[Tuple[str, str]]:
        for f, data in self.plists.items():
            if key in data:
                return str(data[key]), self.rel(f)
        return self.extra_plist_keys.get(key)


def finding(fid, guideline, title, severity, confidence, message, evidence=None, fix=None):
    return {"id": fid, "guideline": guideline, "title": title, "severity": severity,
            "confidence": confidence, "message": message, "evidence": evidence or [], "fix_hint": fix}


def run_checks(p: Project) -> List[dict]:
    out: List[dict] = []

    # 1. Purpose strings: missing for APIs in use, or too vague
    for key, code_rx, what in PURPOSE_KEYS:
        uses = p.grep(code_rx)
        if not uses and not p.in_manifests(code_rx):
            continue
        val = p.plist_value(key)
        if val is None:
            out.append(finding(f"purpose-missing-{key}", "5.1.1", "Data Collection and Storage", "high", "likely",
                               f"The code uses {what} but no {key} was found. iOS crashes when the permission is requested "
                               "without it, and App Review rejects vague or missing purpose strings.",
                               uses, f"Add {key} to Info.plist with a sentence explaining how {what} benefits the user."))
        elif GENERIC_PURPOSE.match(val[0]) and val[0] != "(set in config)":
            out.append(finding(f"purpose-vague-{key}", "5.1.1", "Data Collection and Storage", "medium", "possible",
                               f"The {what} purpose string looks too vague: \"{masked(val[0])}\". Reviewers want what the data is used for and why it helps the user.",
                               [{"file": val[1], "line": None, "snippet": f"{key} = {masked(val[0])}"}],
                               "Rewrite it as a specific sentence, e.g. \"Scan receipts with the camera to add expenses automatically.\""))

    # 2. Privacy manifest and required-reason APIs
    declared = set()
    for data in p.privacy_manifests.values():
        for entry in (data.get("NSPrivacyAccessedAPITypes") or []):
            if isinstance(entry, dict):
                declared.add(entry.get("NSPrivacyAccessedAPIType"))
    missing = []
    for cat, rx in REQUIRED_REASON:
        hits = p.grep(rx, limit=2)
        if hits and cat not in declared:
            missing.append((cat, hits))
    if missing:
        ev = [h for _, hits in missing for h in hits][:MAX_EVIDENCE]
        cats = ", ".join(c.replace("NSPrivacyAccessedAPICategory", "") for c, _ in missing)
        out.append(finding("privacy-manifest", "5.1.1", "Privacy manifest (ITMS-91053)", "high" if not p.privacy_manifests else "medium",
                           "likely" if not p.privacy_manifests else "possible",
                           ("No PrivacyInfo.xcprivacy found" if not p.privacy_manifests else "PrivacyInfo.xcprivacy does not declare every API category used")
                           + f". Required-reason API categories in use: {cats}. Uploads get ITMS-91053 warnings or rejections.",
                           ev, "Add or update PrivacyInfo.xcprivacy with NSPrivacyAccessedAPITypes and an approved reason for each category. "
                               "Third-party SDKs need their own manifests; update them to current versions."))

    # 3. Account creation without deletion
    signup = p.grep(r"createUser\(|createUserWithEmail|\.signUp\(|signUpWith|registerUser|auth\(\)\.createUser|supabase\.auth\.signUp|Auth\.auth\(\)\.createUser|\"(?:Sign Up|Create Account|Crear cuenta|Registrarse)\"", re.I)
    delete = p.grep(r"deleteAccount|delete_account|deleteUser|user\.delete\(|currentUser\??\.delete|admin\.deleteUser|\"(?:Delete Account|Delete my account|Eliminar cuenta|Borrar cuenta)\"", re.I, limit=1)
    if signup and not delete:
        out.append(finding("account-deletion", "5.1.1(v)", "Account deletion", "high", "likely",
                           "The app lets people create an account, but no account deletion was found. Apps with account creation must let users start deleting their account inside the app.",
                           signup, "Add Delete Account in Settings or Profile that deletes the account and its data (or starts the deletion), not only an email link."))

    # 4. Third-party login without Sign in with Apple
    social = p.grep(r"GIDSignIn|GoogleSignIn|signInWithGoogle|FBSDKLoginKit|LoginManager\(\)\.logIn|signInWithFacebook|@react-native-google-signin|google_sign_in|flutter_facebook_auth|expo-auth-session", 0)
    social += [{"file": "dependencies", "line": None, "snippet": s} for s in p.in_manifests(r"GoogleSignIn|FBSDKLoginKit|@react-native-google-signin/google-signin|google_sign_in|flutter_facebook_auth")]
    apple = p.has(r"ASAuthorizationAppleIDProvider|SignInWithAppleButton|appleAuthentication|expo-apple-authentication|sign_in_with_apple|@invertase/react-native-apple-authentication")
    if social and not apple:
        out.append(finding("login-4.8", "4.8", "Login Services", "high", "likely",
                           "Third-party or social login is used for the account, with no Sign in with Apple or other equivalent privacy-focused login option found.",
                           social[:MAX_EVIDENCE], "Add Sign in with Apple (or another login that limits data to name and email and allows hiding the email), with equal prominence."))

    # 5. Purchases: restore + paywall terms
    iap = p.grep(r"Product\.products\(|SKProductsRequest|SKPaymentQueue|Purchases\.shared|Purchases\.configure|react-native-iap|react-native-purchases|in_app_purchase|purchases_flutter|\.purchase\(", 0)
    if iap:
        if not p.has(r"restorePurchases|restoreCompletedTransactions|AppStore\.sync|restoreTransactions|getAvailablePurchases|\"Restore", re.I):
            out.append(finding("iap-restore", "3.1.1", "In-App Purchase: restore", "medium", "likely",
                               "In-app purchases are used but no Restore Purchases action was found.",
                               iap[:2], "Add a visible Restore Purchases button on the paywall or in Settings."))
        subs = p.has(r"subscription|autoRenew|Product\.SubscriptionInfo|\.subscription\b", re.I)
        terms = p.grep(r"terms|eula|privacy", re.I, limit=2, strings_only=True)
        if subs and not terms:
            out.append(finding("subs-terms", "3.1.2", "Subscriptions: required information", "medium", "possible",
                               "Subscriptions appear to be sold, but no Terms of Use or Privacy Policy links were found in the app's strings.",
                               iap[:2], "Show price, period, trial terms, and links to Terms of Use (EULA) and Privacy Policy on the paywall."))

    # 6. External payment links for digital goods
    ext = p.grep(r"checkout\.stripe\.com|buy\.stripe\.com|paypal\.com/checkout|gumroad\.com|lemonsqueezy|paddle\.com|\"(?:Buy on (?:our )?website|Subscribe on the web|Comprar en la web)", re.I)
    if ext:
        out.append(finding("external-payments", "3.1.1", "Payments outside In-App Purchase", "medium", "possible",
                           "Links to outside checkouts were found. Selling digital content or features this way can break 3.1.1, though rules now differ by storefront.",
                           ext, "Check what is sold. Physical goods and services are fine; for digital content use IAP, or follow the current 3.1.1(a)/3.1.3 rules for the storefronts you serve."))

    # 7. Tracking: IDFA or ad SDKs without ATT
    idfa = p.grep(r"advertisingIdentifier|ASIdentifierManager", 0)
    ad_sdks = p.in_manifests(TRACKING_SDKS)
    att = p.has(r"ATTrackingManager|requestTrackingAuthorization|expo-tracking-transparency|app_tracking_transparency|react-native-tracking-transparency")
    if (idfa or ad_sdks) and not att:
        out.append(finding("att", "5.1.2", "Data Use and Sharing: tracking", "high" if idfa else "medium", "likely" if idfa else "possible",
                           "The advertising identifier or ad/attribution SDKs are present, but no App Tracking Transparency prompt was found.",
                           idfa + [{"file": "dependencies", "line": None, "snippet": s} for s in ad_sdks][:MAX_EVIDENCE],
                           "Request tracking permission with ATTrackingManager before tracking, add NSUserTrackingUsageDescription, and declare tracking in App Privacy."))

    # 8. Placeholder content
    ph = p.grep(r"lorem ipsum|coming soon|próximamente|under construction|\bplaceholder text\b|\bTBD\b|test123", re.I, strings_only=True)
    if ph:
        out.append(finding("placeholders", "2.1", "App Completeness: placeholder content", "medium", "possible",
                           "User-facing strings contain placeholder or unfinished text.", ph,
                           "Remove placeholder text and \"coming soon\" screens, or hide unfinished features before submitting."))

    # 9. Dev/staging endpoints
    dev = p.grep(r"https?://(?:localhost|127\.0\.0\.1|10\.0\.2\.2|192\.168\.|[\w.-]*ngrok|[\w.-]*\.local\b|staging\.|dev\.|[\w-]+-staging\.)", re.I, strings_only=True)
    if dev:
        out.append(finding("dev-endpoints", "2.1", "App Completeness: development servers", "high", "possible",
                           "Development or staging URLs found in strings. If the release build uses them, the reviewer gets errors or empty screens.",
                           dev, "Make sure release builds point at production, e.g. with build configurations, and that the backend is live during review."))

    # 10. User-generated content without report/block
    ugc = p.grep(r"sendMessage|postComment|createPost|addComment|collection\([\"'](?:messages|posts|comments|chats)[\"']|\"(?:Post|Comment|Send message)\"", re.I)
    if ugc and not p.has(r"report|block(?:User|edUsers)|\"Block|\"Report|reportContent|flagContent", re.I):
        out.append(finding("ugc", "1.2", "User-Generated Content", "medium", "possible",
                           "Users seem to post or send content to others, but no report or block feature was found.",
                           ugc, "Add Report on content and Block on users, a filter or moderation, and published contact info."))

    # 11. Private APIs / hot patching
    priv = p.grep(r"LSApplicationWorkspace|UITabBarSwappableImageView|_UIStatusBar|\bvalueForKey:@\"_|setValue:.*forKey:@\"_|UIGetScreenImage|GSEvent", 0)
    if priv:
        out.append(finding("private-api", "2.5.1", "Software Requirements: non-public APIs", "high", "possible",
                           "Code that looks like private API use was found.", priv, "Replace with public APIs or remove; check the SDK that ships it."))
    hot = p.grep(r"JSPatch|Rollout\.io|wax\.|evaluateScript\(.*(?:http|download)", re.I)
    hot += [{"file": "dependencies", "line": None, "snippet": s} for s in p.in_manifests(r"JSPatch|Rollout|DynamicCocoa|Wax")]
    if hot:
        out.append(finding("hot-patch", "2.5.2", "Software Requirements: downloaded code", "high", "possible",
                           "Hot-patching or remote code loading may be present.", hot[:MAX_EVIDENCE],
                           "Remove the hot-patching framework. Downloading content is fine; downloading code that changes features is not."))

    # 12. Privacy policy link in app
    if not p.grep(r"privacy", re.I, limit=1, strings_only=True):
        out.append(finding("privacy-link", "5.1.1(i)", "Privacy policy link in the app", "medium", "possible",
                           "No privacy policy link or text was found in the app's strings. It must be in App Store Connect and easy to reach inside the app.",
                           [], "Add Privacy Policy in Settings or About that opens your policy URL."))

    # 13. Web wrapper
    web = p.grep(r"WKWebView|react-native-webview|webview_flutter|<WebView", 0)
    native_files = sum(1 for f, _ in p.code if f.suffix in (".swift", ".m", ".tsx", ".jsx", ".dart"))
    if web and native_files <= 6:
        out.append(finding("web-wrapper", "4.2", "Minimum Functionality", "medium", "possible",
                           f"The app is small ({native_files} source files) and uses a web view, so it may look like a website in a wrapper.",
                           web[:2], "Make sure the app offers native features beyond the website (offline use, notifications, device features, native navigation)."))

    return out


# What to check by hand for past rejections that code can't show. Keyed by guideline prefix.
MANUAL_CHECKS = [
    ("2.1(b)", "Attach every new in-app purchase and subscription to the submission, and describe the path to the paywall in the review notes."),
    ("2.1", "Fill in a working demo account (with its password) and step-by-step review notes, keep the backend live, and test the release build on a clean device."),
    ("2.3", "Compare screenshots, description, keywords and What's New with the current build; remove anything the app doesn't do."),
    ("4.3", "Make sure this app is clearly different from your other apps in function, name, icon, screenshots and description; avoid reusing the same template."),
    ("4.2", "Make sure the reviewer sees native features beyond a website in the first minute of use."),
    ("4.0", "Check layouts on the smallest and largest iPhones and on iPad if supported."),
    ("3.1", "Open the paywall: price, period, trial terms, Restore, and Terms/Privacy links must all be visible; digital goods only through In-App Purchase."),
    ("5.1.1", "Check that the App Privacy answers in App Store Connect match what the app and every SDK collect."),
    ("5.1.2", "Check data sharing disclosures and consent, including data sent to analytics or AI services."),
    ("1.2", "Try reporting a post and blocking a user in the build you'll submit."),
    ("5.6", "Account-level: review how you ask for ratings and how apps and metadata are produced across the account."),
    ("", "Read the past reviewer message and check the same area of this app by hand."),
]


# Words a reviewer typically uses for the problem each check finds.
TOPIC_WORDS = {
    "account-deletion": ["delet"],
    "login-4.8": ["sign in", "sign-in", "login", "log in", "google", "facebook", "equivalent"],
    "purpose": ["purpose string", "usage description", "permission", "access to the", "requests access"],
    "privacy-manifest": ["privacy manifest", "required reason", "xcprivacy", "itms-91053"],
    "privacy-link": ["privacy policy"],
    "iap-restore": ["restore"],
    "subs-terms": ["terms of use", "eula", "terms", "renewal", "subscription"],
    "external-payments": ["external", "outside of", "payment mechanism", "buy", "purchase"],
    "att": ["track", "advertising identifier", "idfa", "app tracking transparency"],
    "placeholders": ["placeholder", "coming soon", "incomplete", "lorem", "beta"],
    "dev-endpoints": ["server", "error", "unable to load", "network", "did not load", "blank"],
    "ugc": ["report", "block", "user-generated", "objectionable"],
    "private-api": ["non-public", "private api"],
    "hot-patch": ["download", "executable code", "hot", "change your app's behavior"],
    "web-wrapper": ["website", "web view", "repackaged", "minimum functionality"],
}


def _topic(fid: str) -> str:
    return "purpose" if fid.startswith("purpose-") else fid


def _split(g: str):
    m = re.match(r"^([\d.]+)((?:\([a-z0-9]+\))*)$", g or "")
    return (m.group(1).split("."), m.group(2)) if m else ((g or "").split("."), "")


def related(history_g: str, finding_g: str) -> bool:
    (a, asub), (b, bsub) = _split(history_g), _split(finding_g)
    n = min(len(a), len(b))
    if n < 2 or a[:n] != b[:n]:
        return False
    # A specific sub-rule like 5.1.1(v) only matches findings for that same sub-rule.
    return not asub or asub == bsub


def manual_check(g: str) -> str:
    for prefix, text in MANUAL_CHECKS:
        if g.startswith(prefix):
            return text
    return MANUAL_CHECKS[-1][1]


def compare_history(history: List[dict], findings: List[dict], bundle_ids: set, project: str) -> List[dict]:
    out = []
    for h in history:
        g = h.get("guideline", "")
        said = (h.get("said", "") + " " + h.get("why", "") + " " + h.get("title", "")).lower()
        same_app = bool(h.get("bundle_id") and h["bundle_id"] in bundle_ids) or \
            (not h.get("bundle_id") and (h.get("app") or "").lower().replace(" ", "") == project.lower().replace(" ", ""))
        rel = [f for f in findings if related(g, f["guideline"])]
        # Same cause = the reviewer's words mention what this finding is about.
        same = [f for f in rel if any(w in said for w in TOPIC_WORDS.get(_topic(f["id"]), []))]
        for f in same:
            f.setdefault("previously_rejected", []).append(
                {k: h.get(k) for k in ("app", "version", "date", "guideline") if h.get(k)})
        verdict = "repeat_risk" if same else ("related_area" if rel else "check_by_hand")
        out.append({
            **{k: h.get(k) for k in ("app", "bundle_id", "version", "date", "guideline", "title", "said", "why") if h.get(k)},
            "same_app": same_app,
            "same_cause_findings": [f["id"] for f in same],
            "same_area_findings": [f["id"] for f in rel if f not in same],
            "verdict": verdict,
            "manual_check": manual_check(g),
        })
    rank = {"repeat_risk": 0, "check_by_hand": 1, "related_area": 2}
    out.sort(key=lambda x: (not x["same_app"], rank[x["verdict"]], x.get("date") or ""))
    return out


NOT_CHECKED = [
    "App Store listing: screenshots, description, keywords, name (2.3)",
    "App Privacy answers in App Store Connect matching what the app and its SDKs collect (5.1.1, 5.1.2)",
    "Demo account and review notes for the reviewer (2.1)",
    "Crashes and broken flows at runtime, and backend availability (2.1)",
    "Age rating answers and content (1.1, 1.3)",
    "Whether the app is too similar to your other apps or others (4.3)",
    "Business model and pricing rules that depend on what is sold (3.1)",
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project", help="path to the app project folder")
    ap.add_argument("--out", help="write JSON here as well as printing it")
    ap.add_argument("--history", help="rejection history JSON from history.py (default: ~/.appreview/history.json if it exists)")
    args = ap.parse_args(argv)
    root = Path(args.project).expanduser().resolve()
    if not root.is_dir():
        print(f"Not a folder: {root}", file=sys.stderr)
        return 2
    p = Project(root)
    if not p.code and not p.plists:
        print("No iOS source files or Info.plist found here. Point at the app project root.", file=sys.stderr)
        return 2
    sev_rank = {"high": 0, "medium": 1, "low": 2}
    findings = sorted(run_checks(p), key=lambda f: (sev_rank.get(f["severity"], 3), f["guideline"]))
    hist_path = Path(args.history).expanduser() if args.history else Path("~/.appreview/history.json").expanduser()
    history = []
    if hist_path.is_file():
        try:
            history = json.loads(hist_path.read_text()).get("rejections", [])
        except ValueError:
            print(f"warning: could not read history at {hist_path}", file=sys.stderr)
    elif args.history:
        print(f"warning: no history file at {hist_path}", file=sys.stderr)
    history_check = compare_history(history, findings, p.bundle_ids, root.name) if history else []
    report = {
        "project": root.name,
        "bundle_ids": sorted(p.bundle_ids),
        "history_used": str(hist_path) if history else None,
        "history_check": history_check,
        "project_kind": p.kind,
        "files_scanned": len(p.code),
        "info_plists": [p.rel(f) for f in p.plists],
        "privacy_manifests": [p.rel(f) for f in p.privacy_manifests],
        "findings": findings,
        "not_checked": NOT_CHECKED,
        "note": "Candidates from static heuristics. Confirm each by reading the code before reporting it.",
    }
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
