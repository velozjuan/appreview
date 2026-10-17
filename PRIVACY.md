# Privacy Policy: Veloz App Review

Last updated: October 17, 2026

Veloz App Review is an open-source plugin for Claude. It runs on your computer and inside your Claude session. Its author runs no servers and receives no data from it: no analytics, no telemetry, no accounts.

## What the plugin reads

- **App Store Connect data**, when you connect it: your app list, App Store versions, review submission states, and the App Review messages you choose to have it read. With an API key, this comes from Apple's API. In browser mode, Claude reads the App Store Connect pages in a browser where you're signed in.
- **Your app project's source files**, when you run the submission check. They're read on your computer.
- **Your App Store Connect API key file**, only to sign requests to Apple. It's read from where you keep it. The plugin never copies, uploads or stores it.

## Where data goes

- `api.appstoreconnect.apple.com` (Apple): read-only requests, signed with your own key, in API key mode.
- `appstoreconnect.apple.com` (Apple): pages you're already signed in to, in browser mode. The plugin never asks for or stores your Apple ID password or verification codes.
- `developer.apple.com` (Apple): to read the current App Review Guidelines.
- `fonts.googleapis.com` and `fonts.gstatic.com` (Google): fonts load when you open a report page.

Like any Claude session, what the plugin reads is processed by Claude under [Anthropic's privacy policy](https://www.anthropic.com/legal/privacy). The plugin sends nothing anywhere else.

## What the plugin stores

- **A rejection history** at `~/.appreview/history.json` on your computer: app name, bundle ID, version, review date, guideline, and the reviewer's words. It stays until you delete the file.
- **Reports you ask for**, as files on your computer or as private artifacts in your Claude account, which you control.

Reports and the history never include passwords, demo account credentials, contact details or API keys. Code snippets in reports have long tokens masked.

## Your choices

You can use the plugin without an API key (browser mode or pasting messages), delete `~/.appreview/history.json` at any time, revoke your API key in App Store Connect under Users and Access > Integrations, and uninstall the plugin whenever you like.

## Children

The plugin is meant for app developers and isn't directed at anyone under 18.

## Contact

Questions or concerns: open an issue at https://github.com/velozjuan/appreview/issues.
