<img src="icon.png" alt="Veloz App Review icon" width="96">

# Veloz App Review

Find out why your iOS app was rejected, how to fix it, and whether your next build will be rejected for the same thing.

Type `/appreview` in Claude Code, or just ask Claude about an App Store rejection, and it will:

- **Explain your rejections.** It finds every app in your App Store Connect account with a rejection or Unresolved Issues, reads App Review's message, maps it to the [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/), and tells you the cause, the kind of fix (metadata only, new build, or information only), the steps, and a reply you can send to App Review.
- **Check a project before you submit.** Run `/appreview check` in an app project. It scans the code for the problems that most often get apps rejected, and checks it against your own past rejections so the same mistake doesn't ship twice.
- **Give you a report.** Results come as a page you can keep: each finding with its guideline number, where it is in your code, numbered fix steps, and a copy button for reply drafts.

It only reads. It never replies to App Review, resubmits, edits your App Store listing or changes your code, unless you ask Claude to fix something afterwards.

## Install

Pick one:

| Method | Command | Best for |
|---|---|---|
| Anthropic's directory | Add **Veloz App Review** on claude.ai (review pending) | Claude apps, Cowork and Claude Code, kept in sync |
| Claude Code plugin | `claude plugin marketplace add velozjuan/appreview`<br>`claude plugin install veloz-appreview@veloz` | Claude Code, with key settings in `/config` |
| `skills` CLI | `npx skills add https://github.com/velozjuan/appreview --skill appreview` | Claude Code, Codex, Cursor and other agents that read skills (add `-g` for all projects) |
| By hand | Copy `skills/appreview` to `~/.claude/skills/appreview` | Anyone |

However you install it, the command is `/appreview` and it shows up in `/skills`.

**Requirements:** Python 3.9 or later. The API key option also needs `pip install cryptography`.

## Use it

```
/appreview                      explain the rejections in your account
/appreview check                check the project in this folder before submitting
why was my app rejected for 4.3?
check this app against my past rejections
```

You can also paste an App Review message into the chat and ask what to do.

## Connect your App Store Connect account

Claude asks the first time. Two options:

### 1. API key

Fastest, and the best way to see what's open right now across all your apps.

1. In App Store Connect, go to **Users and Access > Integrations > App Store Connect API**.
2. Create a **Team Key** with the **App Manager** role and download the `AuthKey_XXXX.p8` file. Apple lets you download it only once.
3. Keep the file on your computer, outside any git repository:
   ```bash
   mkdir -p ~/.appstoreconnect/private_keys
   mv ~/Downloads/AuthKey_XXXX.p8 ~/.appstoreconnect/private_keys/
   chmod 600 ~/.appstoreconnect/private_keys/AuthKey_XXXX.p8
   ```
4. Tell the skill where it is:
   - **Plugin install:** Claude Code asks for the Key ID, Issuer ID and key file when you enable the plugin. Change them later with `/config`.
   - **Any other install:** set environment variables, for example in `~/.zshrc`:
     ```bash
     export ASC_KEY_ID=XXXX
     export ASC_ISSUER_ID=your-issuer-id   # leave out for an individual key
     export ASC_PRIVATE_KEY_PATH=~/.appstoreconnect/private_keys/AuthKey_XXXX.p8
     ```

Never paste the contents of the `.p8` file into a chat. If it ever leaks, revoke it on the same Integrations page.

The API key works where Claude runs commands on your own computer, as in Claude Code. Cloud sandboxes, such as code execution on claude.ai, usually block Apple's API; there, use the browser option, or the skill gives you a one-line command to run in your Terminal.

### 2. Your browser (no key)

Claude opens App Store Connect in a browser where you're signed in, goes through your apps and reads the App Review messages. You sign in yourself; Claude never asks for your Apple ID password or verification codes, and it doesn't click anything that changes your apps. This needs a browser Claude can use, such as the Claude desktop app's built-in browser or Claude in Chrome.

### Past rejections

Apple's API only shows rejections that are still open. Once a rejection is fixed and the app is approved, it disappears from the API. To build your rejection history (used by `/appreview check`), the skill reads past App Review messages in your browser, or you paste them in. The history is saved on your computer at `~/.appreview/history.json`.

## What the submission check looks for

| Guideline | Check |
|---|---|
| 5.1.1 | Permission APIs used without an explanation string, or with a vague one |
| 5.1.1 / ITMS-91053 | Required-reason APIs without a privacy manifest entry |
| 5.1.1(v) | Account sign-up with no in-app account deletion |
| 5.1.1(i) | No privacy policy link in the app |
| 4.8 | Google or Facebook login without Sign in with Apple or an equivalent |
| 3.1.1 / 3.1.2 | In-app purchases without Restore; subscriptions without terms links; outside checkouts |
| 5.1.2 | Advertising identifier or ad SDKs without the App Tracking Transparency prompt |
| 2.1 | Placeholder text, staging or localhost servers |
| 1.2 | Posting or chat without report and block |
| 2.5.1 / 2.5.2 | Private API patterns, hot-patching frameworks |
| 4.2 | Very small apps built around a web view |

Plus your own history: each past rejection is checked again against the project and marked **same problem found**, **check by hand** or **looks fixed**.

It works with Swift and Objective-C projects and with React Native, Expo, Flutter and Capacitor apps. Claude confirms each finding by reading the code before reporting it. Code can't show your App Store listing, App Privacy answers, demo account or runtime crashes, so those come up as things to check by hand. A clean check doesn't guarantee approval.

## Troubleshooting

| Problem | Fix |
|---|---|
| `401` when checking the key | The Key ID, Issuer ID and `.p8` don't match, the key was revoked, or your computer's clock is off. For an individual key, leave the Issuer ID empty. |
| `403` | The key's role can't read review data. Use **App Manager** or **Admin**. |
| "The network here blocks api.appstoreconnect.apple.com" | You're in a sandbox. Use Claude Code on your computer, the Terminal command the skill gives you, or browser mode. |
| The scan finds no rejections but you had some | They were resolved, so Apple's API no longer shows them. Use browser mode to read them. |
| `/appreview` isn't listed | Restart Claude Code, or check `/plugin` (plugin install) or `~/.claude/skills/appreview/SKILL.md` (other installs). |

## Data and network use

| What | Where it goes | When |
|---|---|---|
| Signed, read-only requests (`GET` only) with a token made from your API key | `api.appstoreconnect.apple.com` (Apple) | API key mode |
| Your browser session, read only | `appstoreconnect.apple.com` (Apple), in your own browser | Browser mode |
| Nothing (just reads the public page) | `developer.apple.com` | To check the current guideline text |
| Your project's source files, read locally | Nowhere: the scan runs on your machine | Submission check |
| Rejection history (app name, bundle ID, version, date, guideline, reviewer's words) | `~/.appreview/history.json` on your computer | After a rejections report |
| Report page fonts | `fonts.googleapis.com` / `fonts.gstatic.com`, when the report is opened | Report |

The key file is read where you keep it, to sign requests, and is never copied, uploaded or stored by the skill. Reports and the history never contain passwords, demo account credentials, contact details or keys, and code snippets in reports have long tokens masked. Claude sees what the skill reads, as in any Claude session. Full details: [PRIVACY.md](PRIVACY.md).

## Repository layout

```
.claude-plugin/plugin.json        plugin manifest, icon and key settings
.claude-plugin/marketplace.json   lets Claude Code install from this repo
skills/appreview/SKILL.md         the skill
skills/appreview/scripts/         Python scripts: API client, scans, report
skills/appreview/references/      guideline playbook, setup and workflow notes
PRIVACY.md                        privacy policy
```

To test the scripts offline against a mock of the App Store Connect API:

```bash
python3 skills/appreview/scripts/selftest.py
```

Issues and suggestions: [github.com/velozjuan/appreview/issues](https://github.com/velozjuan/appreview/issues).

## License

MIT. Not affiliated with or endorsed by Apple. App Store, App Store Connect and iOS are trademarks of Apple Inc.
