# Pre-submission check (preflight)

Checks an app project for the problems that most often get apps rejected, before the user
submits. No App Store Connect access needed, only the project folder.

## 1. Find the project

Use the folder the user is working in, or the one they name. It needs the app's source:
an `.xcodeproj`/`.xcworkspace` or `Package.swift` for native apps, or the root of a React
Native, Expo, Flutter or Capacitor project (the folder with `package.json` or `pubspec.yaml`).
If the folder isn't reachable from where you run code, ask the user to connect it.

## 1b. Load the account's rejection history

The check is much sharper when it knows what App Review rejected before. The history lives in
`~/.appreview/history.json` (see `python scripts/history.py path`) and is filled every time a
rejections report is made (`history.py import report.json`).

- **History exists**: run `python scripts/history.py list` and tell the user in one line how
  many past rejections you'll check against.
- **No history**: offer once, briefly: "Want me to pull your past rejections from App Store
  Connect first, so I can check this project against them?" If yes, collect them with Helm's
  CLI if the user has it (`helm-cli.md`, the most complete source), otherwise from the App
  Review pages in the browser (`browser-mode.md`, step 3, history), or ask the user to paste
  the messages. The API key alone isn't enough here: it only shows rejections that are still
  open. Build a rejections report, import it into the history, then come back here. If no,
  do the plain check.
- If the history file can't be reached from where you run code (a sandbox), import the
  rejections report there for this run, or ask the user where the file is.

## 2. Run the scanner

```bash
python scripts/preflight_scan.py /path/to/project --out preflight.json
```

It reads Info.plist files (and `INFOPLIST_KEY_*` build settings, and Expo `app.json`
`infoPlist`), privacy manifests, dependency manifests (Podfile, Package.resolved,
package.json, pubspec.yaml) and source files, skipping third-party folders (Pods,
node_modules, build output). It returns candidates with guideline, severity, confidence,
evidence and a fix hint, plus a `not_checked` list.

It checks for:

| Guideline | What it looks for |
|---|---|
| 5.1.1 | Permission APIs used without a purpose string; vague purpose strings |
| 5.1.1 / ITMS-91053 | Required-reason APIs (UserDefaults, file timestamps, boot time, disk space, keyboards) without a privacy manifest entry |
| 5.1.1(v) | Account creation with no account deletion |
| 5.1.1(i) | No privacy policy link in the app |
| 4.8 | Google/Facebook login without Sign in with Apple or equivalent |
| 3.1.1 | In-app purchases without Restore; links to outside checkouts |
| 3.1.2 | Subscriptions without Terms/Privacy links |
| 5.1.2 | Advertising identifier or ad/attribution SDKs without the ATT prompt |
| 2.1 | Placeholder text; staging, localhost or tunnel URLs |
| 1.2 | Posting or messaging without report/block |
| 2.5.1 / 2.5.2 | Private API patterns; hot-patching frameworks |
| 4.2 | Very small app built around a web view |

With history, the scanner picks it up from the default path (or `--history FILE`) and adds
`history_check`: one entry per past rejection, with

- `same_app`: true when the past rejection was for this app (matched by bundle ID, from
  `bundle_ids` the scanner found in the project);
- `same_cause_findings`: current findings under the same guideline whose topic matches the
  reviewer's words (those findings also get `previously_rejected`);
- `same_area_findings`: findings under the same guideline but apparently a different cause;
- `verdict`: `repeat_risk` (same cause found), `related_area` (same guideline, different
  cause; still check the original cause) or `check_by_hand` (nothing in code matched);
- `manual_check`: what to check for guidelines that code can't show (demo account,
  screenshots, similarity between apps).

### Judge each past rejection against the project

The guideline match is coarse; the reviewer's words (`said`) are what count. For each entry:

1. Read what the reviewer said then and find the same area in this project: the screen, flow,
   SDK, purchase or string they described. Search the code for the names they used.
2. Decide one of:
   - **Same problem found** (`status: "repeat"`): the cause is still there. Point at the file
     and line, and say how it was fixed last time if the history says.
   - **Looks fixed** (`status: "fixed"`): you found the fix in this project (e.g. a Delete
     Account screen now exists). Say where, briefly.
   - **Check by hand** (`status: "manual"`): the cause isn't visible in code (demo account,
     metadata, 4.3 similarity, a runtime crash). Give the concrete check from `manual_check`,
     made specific to what the reviewer said.
3. A rejection in **another** app counts too: the same developer usually repeats the same
   patterns (shared code, templates, the same login or paywall). Weigh same-app history
   first, then account-wide patterns, and say which apps they came from.

## 3. Confirm every candidate

The scanner uses text patterns, so it has false positives and misses things. Before
reporting a finding, open the evidence files and check:

- **Is it real?** A staging URL used only in a debug build configuration, a `deleteAccount`
  that lives on the server, a Sign in with Apple button in a different module: these are
  false positives. Drop them.
- **Is the evidence the right place?** Point the user at the file and line where the fix goes.
- **Anything it missed nearby?** While reading, note related problems (a paywall that hides
  the renewal price, a login screen with no way past it for a reviewer).

Severity guide: **high** means a rejection or crash is likely as-is; **medium** means a
reviewer may reject depending on what they see; **low** means good practice.

Then check the current text of each guideline you cite
(https://developer.apple.com/app-store/review/guidelines/) when web fetch is available, and
use `guidelines-playbook.md` for the fix and wording.

## 4. Report

If you checked against history, the first group is **"Past rejections, checked again"**: one
finding per past rejection with `status` repeat / manual / fixed, the reviewer's words from
then in `said`, what you found in this project in `why`, and the evidence. Order: same
problem found first, then check by hand, then looks fixed; same-app before other apps. Put the
count of repeats in the summary sentence, since that's what the user most needs to know.

Then group the remaining findings by severity area or by target (app, widget, extension), most serious first.
For each: what was found and where, why it matters for review, how to fix it. Skip the reply
draft unless the user is already answering a rejection. Add one line listing what static
checks can't see (from `not_checked`) and suggest they run `/appreview` against App Store
Connect after submitting if they get rejected.

If nothing is found, say so plainly and still list what wasn't checked. A clean scan doesn't
guarantee approval.
