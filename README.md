![veloz](veloz-logo.png)

# Veloz App Review

Find out why your iOS app was rejected, how to fix it, and whether your next build will be rejected for the same thing.

Type `/appreview` in Claude Code, or just ask Claude about an App Store rejection, and it will:

- **Explain your rejections.** It finds every app in your App Store Connect account with a rejection or Unresolved Issues, reads App Review's message, maps it to the [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/), and tells you the cause, the kind of fix (metadata only, new build, or information only), the steps, and a reply you can send to App Review.
- **Check a project before you submit.** Run `/appreview check` in an app project. It scans the code for the problems that most often get apps rejected, and checks it against your own past rejections so the same mistake doesn't ship twice.
- **Give you a report.** Results come as a page you can keep: each finding with its guideline number, where it is in your code, numbered fix steps, and a copy button for reply drafts.

It only reads. It never replies to App Review, resubmits, edits your App Store listing or changes your code, unless you ask Claude to fix something afterwards.

## Install

Pick one. However you install it, the command is `/appreview` and it shows up in `/skills`.

### Claude Code plugin

Recommended for Claude Code. Your API key settings live in `/config`.

```bash
claude plugin marketplace add velozjuan/appreview
claude plugin install veloz-appreview@veloz
```

### skills CLI

Works with Claude Code, Codex, Cursor and other agents that read skills. Add `-g` to install it for all your projects.

```bash
npx skills add https://github.com/velozjuan/appreview --skill appreview
```

### Anthropic's directory

Review pending. Once it's listed, add **Veloz App Review** on claude.ai and it syncs to the Claude apps, Cowork and Claude Code.

### By hand

Copy the `skills/appreview` folder to `~/.claude/skills/appreview`.

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

Claude asks the first time. Three options:

### 1. Helm CLI (most complete, if you use Helm)

If you use [Helm for App Store Connect](https://helm-app.com) with Helm Pro, install its `helm-asc` command-line tool from Helm's **Settings** on your Mac. `/appreview` finds it on its own and uses it to read the App Review messages for all your apps, including past rejections that were later fixed, which Apple's API can't return.

- It uses the account you already connected in Helm. No extra key setup.
- The skill only runs helm-asc commands that read. It never submits, replies or changes anything through Helm.
- It runs on your Mac, so use it from Claude Code on your Mac. In other setups, Claude gives you the commands to paste into Terminal.

Helm is a separate product by another developer and isn't required.

### 2. API key

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

### 3. Your browser (no key)

Claude opens App Store Connect in a browser where you're signed in, goes through your apps and reads the App Review messages. You sign in yourself; Claude never asks for your Apple ID password or verification codes, and it doesn't click anything that changes your apps. This needs a browser Claude can use, such as the Claude desktop app's built-in browser or Claude in Chrome.

### Past rejections

Apple's API only shows rejections that are still open. Once a rejection is fixed and the app is approved, it disappears from the API. To build your rejection history (used by `/appreview check`), the skill reads past App Review messages with Helm's CLI if you have it, otherwise in your browser, or you paste them in. The history is saved on your computer at `~/.appreview/history.json`.

## What the submission check looks for

| Area | Guideline | What it flags |
|---|---|---|
| Privacy | 5.1.1 | Permission prompts without an explanation, or with a vague one |
| Privacy | 5.1.1 (ITMS-91053) | Missing privacy manifest |
| Privacy | 5.1.1(v) | Sign-up with no in-app account deletion |
| Privacy | 5.1.1(i) | No privacy policy link in the app |
| Login | 4.8 | Google or Facebook login without Sign in with Apple |
| Payments | 3.1.1 | In-app purchases without Restore; checkouts outside the App Store |
| Payments | 3.1.2 | Subscriptions without terms links |
| Tracking | 5.1.2 | Advertising identifier or ad SDKs without the tracking prompt |
| Completeness | 2.1 | Placeholder text; staging or localhost servers |
| User content | 1.2 | Posting or chat without report and block |
| Code | 2.5.1, 2.5.2 | Private API patterns; hot-patching frameworks |
| Minimum functionality | 4.2 | Very small apps built around a web view |

Plus your own history: each past rejection is checked again against the project and marked **same problem found**, **check by hand** or **looks fixed**.

It works with Swift and Objective-C projects and with React Native, Expo, Flutter and Capacitor apps. Claude confirms each finding by reading the code before reporting it. Code can't show your App Store listing, App Privacy answers, demo account or runtime crashes, so those come up as things to check by hand. A clean check doesn't guarantee approval.

## Troubleshooting

**Error 401 when checking the key.** The Key ID, Issuer ID and `.p8` file don't match, the key was revoked, or your computer's clock is off. For an individual key, leave the Issuer ID empty.

**Error 403.** The key's role can't read review data. Use a key with the **App Manager** or **Admin** role.

**"The network here blocks api.appstoreconnect.apple.com."** You're in a sandbox. Use Claude Code on your computer, the Terminal command the skill gives you, or browser mode.

**The scan finds no rejections, but you had some.** They were resolved, so Apple's API no longer shows them. Use Helm's CLI or browser mode to read them.

**helm-asc isn't found.** It comes with Helm Pro and is installed from Helm's Settings on your Mac. It only works on that Mac, not in cloud sandboxes.

**`/appreview` isn't listed.** Restart Claude Code. Then check `/plugin` for a plugin install, or that `~/.claude/skills/appreview/SKILL.md` exists for other installs.

## Data and network use

- **API key mode:** signed, read-only requests (`GET` only), with a token made from your key, go to Apple at `api.appstoreconnect.apple.com`.
- **Helm CLI mode:** Claude runs read-only `helm-asc` commands on your Mac. Helm makes the requests to Apple with the account you connected in Helm. See [Helm's privacy policy](https://helm-app.com/privacy/) for how Helm handles data.
- **Browser mode:** Claude reads `appstoreconnect.apple.com` in your own signed-in browser.
- **Guideline text:** Claude reads the public page at `developer.apple.com`. Nothing is sent.
- **Submission check:** your project's source files are read on your computer and sent nowhere else.
- **Rejection history:** app name, bundle ID, version, date, guideline and the reviewer's words are saved to `~/.appreview/history.json` on your computer.
- **Report page:** fonts load from `fonts.googleapis.com` and `fonts.gstatic.com` when you open a report.

The key file is read where you keep it, to sign requests, and is never copied, uploaded or stored by the skill. Reports and the history never contain passwords, demo account credentials, contact details or keys, and code snippets in reports have long tokens masked. Claude sees what the skill reads, as in any Claude session. Full details: [PRIVACY.md](PRIVACY.md).

## Repository layout

```
.claude-plugin/plugin.json        plugin manifest, icon and key settings
.claude-plugin/marketplace.json   lets Claude Code install from this repo
skills/appreview/SKILL.md         the skill
skills/appreview/scripts/         Python scripts: API client, scans, report
skills/appreview/references/      guideline playbook, setup and workflow notes
PRIVACY.md                        privacy policy
icon.png, veloz-logo.png          listing icon and brand logo
```

To test the scripts offline against a mock of the App Store Connect API:

```bash
python3 skills/appreview/scripts/selftest.py
```

Issues and suggestions: [github.com/velozjuan/appreview/issues](https://github.com/velozjuan/appreview/issues).

## License

MIT. Not affiliated with or endorsed by Apple. App Store, App Store Connect and iOS are trademarks of Apple Inc.
