# Setting up an App Store Connect API key

Use this when the user chose the API key option and has no working key. Walk them through
it one step at a time, in plain words, and wait for each step to be done before the next.
If they get stuck or change their mind, offer browser mode (`browser-mode.md`) instead.

## 1. Create the key

**Team key** (recommended; needs the Account Holder or an Admin to create):
1. App Store Connect > **Users and Access** > **Integrations** > **App Store Connect API**.
2. **Team Keys** > the **+** button. Name it (e.g. "Rejection analyzer").
3. Access: **App Manager** is enough to read apps, versions and review submissions.
   (Developer can work for some read calls but often gets 403 on review data.)
4. **Download** the `AuthKey_<KEY_ID>.p8` file. Apple only lets you download it once.
5. Note the **Key ID** (in the table) and the **Issuer ID** (top of the page).

**Individual key** (any user can create one for themselves, with their own role):
User profile > **Individual API Key** > **Generate API Key**. Download the `.p8` and note
the Key ID. There is no issuer ID for individual keys; leave `ASC_ISSUER_ID` unset.

## 2. Store it safely

Keep the `.p8` file on the user's machine, outside any git repository, readable only by
them:

```bash
mkdir -p ~/.appstoreconnect/private_keys
mv ~/Downloads/AuthKey_ABC123XYZ9.p8 ~/.appstoreconnect/private_keys/
chmod 600 ~/.appstoreconnect/private_keys/AuthKey_ABC123XYZ9.p8
```

The key gives API access to the whole team's apps at its role level. Never paste it into a
chat, commit it, or email it. If it leaks, revoke it in the same Integrations page.

## 3. Point the scripts at it

**Installed as a plugin in Claude Code?** Claude Code asks for the Key ID, Issuer ID and key
file when the plugin is enabled. To change them later, run `/config` and find the Veloz App
Review settings. Nothing else to set.

**Otherwise**, set environment variables:

```bash
export ASC_KEY_ID=ABC123XYZ9
export ASC_ISSUER_ID=69a6de7e-xxxx-xxxx-xxxx-xxxxxxxxxxxx   # team keys only
export ASC_PRIVATE_KEY_PATH=~/.appstoreconnect/private_keys/AuthKey_ABC123XYZ9.p8
python scripts/asc_auth.py   # prints "OK: authenticated" and a few app names
```

`ASC_PRIVATE_KEY` (the PEM text itself) also works, for CI secrets.

If the assistant runs in a sandbox that is not the user's computer, the key has to be
reachable there. Prefer running the scripts on the user's own machine (through a shell
on their computer, if the session has one). Only copy the key into a sandbox when the
user explicitly agrees, and delete it when finished.

## Errors

| Status | Usual cause |
|---|---|
| 401 | wrong Key ID / Issuer ID pairing, issuer ID set for an individual key, revoked key, clock skew |
| 403 | key role too low (use App Manager or Admin), or key restricted from that app |
| 409 | submission in Unresolved Issues; reading still works, changes do not |
| 429 | rate limited; wait and retry |
