# Guideline playbook

How to read this file: each section is keyed by the guideline number App Review cites, in
square brackets, so `scripts/parse_rejection.py --playbook` can pull the matching section
(it falls back from `5.1.1(i)` to `5.1.1` to `5.1`). Every section has the same shape:
what the guideline means, what usually triggers it, how to fix it, and how to reply.

Apple revises the guidelines several times a year. Before telling someone a rule says
something specific, check the current text at
https://developer.apple.com/app-store/review/guidelines/ (use web fetch if available).
Treat the sections below as an experienced starting point, not the rulebook. Where a
section says "verify", the rule has moved recently or varies by region.

Contents: 1.1 · 1.2 · 1.3 · 1.5 · 2.1 · 2.1(b) · 2.3 · 2.5.1 · 2.5.2 · 3.1.1 · 3.1.2 ·
4.0 · 4.1 · 4.2 · 4.3 · 4.5.4 · 4.7 · 4.8 · 5.1.1 · 5.1.2 · 5.1.5 · 5.2 · 5.3 · 5.6 ·
then non-guideline rejections (ITMS binary errors, metadata-only, appeals).

---

## [1.1] Objectionable content
**Means**: content that is offensive, discriminatory, defamatory, or overtly sexual or violent for the stated age rating.
**Triggers**: user-visible text or imagery, AI-generated output with no safeguards, an age rating lower than the content warrants.
**Fix**: remove or moderate the content, raise the age rating answers in App Store Connect, add output filtering for generative features.
**Reply**: name the exact screens changed and the new age rating.

## [1.2] User-generated content
**Means**: any app where users post or share content (chat, comments, feeds, profiles, AI chat shared between users) needs safeguards.
**Triggers**: missing one of the four basics: a way to filter objectionable material, a way to report content with timely responses, a way to block abusive users, and published contact information.
**Fix**: add report and block actions on every piece of user content and every profile, add a content filter or moderation queue, publish contact details in the app and the support URL, accept terms users must agree to before posting.
**Reply**: describe each safeguard with its location in the app (Settings > Report, long-press a message > Block) and say how quickly reports are handled.

## [1.3] Kids category
**Means**: Kids Category apps have the strictest privacy and ad rules.
**Triggers**: third-party analytics or advertising SDKs, links out of the app with no parental gate, collecting identifiers.
**Fix**: remove third-party analytics and ads, add a parental gate before external links and purchases, audit SDKs for data collection.
**Reply**: list the SDKs removed and where the parental gate appears.

## [1.5] Developer information
**Means**: users must be able to reach you.
**Triggers**: dead or generic Support URL, no contact route.
**Fix**: a working support URL with real contact details (email or form).
**Reply**: state the new URL. This is usually a metadata-only fix; no new build.

## [2.1] App completeness (and "Information Needed")
**Means**: the reviewer could not exercise the app. Also used when App Review needs more information and pauses the review.
**Triggers**: crashes on launch or on a specific flow, placeholder text or "coming soon" screens, broken links, backend offline or staging server, demo account missing or not working, login blocked by 2FA or region, features that need hardware the reviewer lacks, an explicit list of questions or a screen-recording request.
**Fix**: reproduce on a clean install of the exact submitted build on a physical device. Fix crashes and dead ends. Provide a working demo account with content, or a demo mode. Keep the backend live during review. Put step-by-step instructions in App Review Information notes. For "Information Needed", answer every numbered item.
**Reply**: answer each question in the same order, attach the requested screen recording captured on a physical device, state the build number tested. If you only changed metadata or review notes, say so.

## [2.1(b)] In-app purchases the reviewer cannot find or use
**Means**: the reviewer could not locate or complete a purchase.
**Triggers**: IAPs or subscriptions not attached to the submission (the first one of each type must be submitted with a new app version), products still in a state that is not ready for review, paywall unreachable without an unavailable account or region, spinner that never ends because products fail to load.
**Fix**: attach the IAPs/subscriptions to the version, complete their metadata and review screenshot, check that products load for the reviewer's storefront, make the paywall reachable from a clear path and describe that path in the review notes.
**Reply**: say which products were attached and the path to the paywall.

## [2.3] Accurate metadata
**Means**: everything on the product page must match the app. Sub-rules include 2.3.1 (no hidden or undocumented features), 2.3.3 (screenshots show the app in use, not only splash or login), 2.3.7 (keywords and names: no competitor names, no trademarks, no irrelevant terms), 2.3.8 (metadata suitable for all audiences), 2.3.10 (do not mention other platforms), 2.3.12 (What's New describes real changes).
**Triggers**: screenshots that do not match the UI, claims the app does not deliver, price or "free" wording in the name, keyword stuffing, another platform's name in text.
**Fix**: edit the metadata in App Store Connect. No new build is needed.
**Reply**: list the fields you changed (screenshots set, subtitle, keywords, description).

## [2.5.1] Public APIs
**Means**: only documented APIs, used as intended.
**Triggers**: a third-party SDK or library calling private APIs, required-reason APIs used without a declaration in the privacy manifest.
**Fix**: update or remove the offending SDK, rebuild. Check the rejection for the exact API or symbol named.
**Reply**: name the SDK version changed and the new build number.

## [2.5.2] Self-contained code
**Means**: the app may not download or run code that changes its features after review.
**Triggers**: hot-patching frameworks, remote scripts that alter behavior, apps that fetch executable logic.
**Fix**: remove the hot-patching mechanism or the SDK that ships it; if you only load data or content, explain that data does not change app behavior.
**Reply**: either confirm removal, or explain precisely what is downloaded and why it is data, not code.

## [3.1.1] In-app purchase
**Means**: digital content and features unlocked inside the app use Apple's In-App Purchase, except where the guidelines allow another route.
**Triggers**: buttons, text or links steering users to buy digital goods elsewhere, purchasing credits or currencies outside IAP, unlocking features with a code sold elsewhere. Verify: rules for external purchase links differ by storefront and have changed after recent court rulings and regional regulation.
**Fix**: move digital purchases to IAP, or remove the external call to action for storefronts where it is not allowed. Check the current text of 3.1.1, 3.1.1(a) and 3.1.3.
**Reply**: say which storefronts and flows changed.

## [3.1.2] Subscriptions
**Means**: subscription apps must be clear and fair.
**Triggers**: paywall that hides price, billing period or renewal terms, a free trial without clear conversion terms, missing links to Terms of Use and Privacy Policy, no Restore Purchases, subscription that offers too little ongoing value.
**Fix**: show price, period, trial length and what happens after on the paywall itself in readable text, include Terms and Privacy links in the app and in metadata, add Restore Purchases.
**Reply**: attach a screenshot of the revised paywall and state its path.

## [4.0] Design
**Means**: general quality bar for interface and experience.
**Triggers**: confusing navigation, broken layouts on some devices, poor iPad support.
**Fix**: test on current devices and sizes, follow the Human Interface Guidelines.
**Reply**: describe the concrete UI changes.

## [4.1] Copycats
**Means**: do not copy another developer's app or use their brand.
**Fix**: remove copied assets, name and look; show original work.
**Reply**: explain what is original.

## [4.2] Minimum functionality
**Means**: an app must offer more than a website in a wrapper.
**Triggers**: repackaged website, marketing-only app, thin content apps.
**Fix**: add native features that justify an app (offline use, push, device features, native navigation), or reconsider shipping as an app.
**Reply**: list the native capabilities and where the reviewer sees them.

## [4.3] Spam (4.3(a) similar to other apps, 4.3(b) saturated category)
**Means**: the app is too similar in binary, metadata or concept to apps from you or others, or the category is flooded with the same idea.
**Triggers**: several apps from one codebase that differ by theme or content, template or no-code output, near-duplicate descriptions and screenshots, saturated utility categories. The message is usually broad and does not say which asset or code triggered it. Do not assume a specific SDK was the cause.
**Fix**: consolidate near-duplicates into one app with in-app variants, make each remaining app clearly distinct in function, metadata and screenshots, remove reused boilerplate, and explain concretely what makes this one different.
**Reply**: a short factual comparison against your other apps and the closest competitors, with screenshots of differentiating features. If you believe it is a mistake, request a call or use the App Review Board appeal after a reply.

## [4.5.4] Push notifications
**Means**: push cannot be required to use the app and cannot be used for marketing without opt-in.
**Fix**: make push optional, add an in-app opt-in for promotions, do not use push for ads.
**Reply**: state where the opt-in lives.

## [4.7] Mini apps, HTML5 and embedded content
**Means**: apps that host other software (mini apps, games, emulators, plug-ins) have extra requirements.
**Fix**: follow 4.7 sub-rules about review of hosted content, age ratings, and privacy; verify the current text because this area is evolving.
**Reply**: explain how hosted content is curated and rated.

## [4.8] Login services
**Means**: apps that use a third-party or social login to set up or authenticate the primary account must also offer an equivalent login option that limits data collection to name and email, allows hiding the email, and does not track without consent. Sign in with Apple meets this. Verify the current wording, as it was revised in 2024.
**Triggers**: Google, Facebook or similar login with no equivalent option.
**Fix**: add Sign in with Apple (or another service that meets all the criteria), place it with equal prominence.
**Reply**: say where the new option appears.

## [5.1.1] Data collection and storage
**Means**: privacy policy, consent, purpose and account deletion. Key sub-rules: (i) a privacy policy link in App Store Connect and inside the app, (ii) consent for data collection, (iii) data minimization, (iv) apps must work without optional permissions, (v) apps that allow account creation must offer account deletion inside the app.
**Triggers**: missing or dead privacy policy link, privacy policy that does not cover what the app does, App Privacy labels that do not match actual collection, permission purpose strings that are vague or missing, no in-app account deletion, forcing a permission before allowing basic use.
**Fix**: add a working policy URL in metadata and an in-app link (Settings > Privacy Policy), make the policy specific, correct the App Privacy answers by auditing every SDK, write purpose strings that explain the benefit to the user, add Delete Account in the app (not only an email address or a web form), do not gate the app on optional permissions.
**Reply**: list the exact paths (Settings > Account > Delete Account) and the corrected URL.

## [5.1.2] Data use and sharing
**Means**: how data is used, shared and tracked. Includes App Tracking Transparency and, per the 2025 update, clear disclosure and explicit permission before sharing personal data with third-party AI. Verify the current text.
**Triggers**: tracking without the ATT prompt, sharing data with ad or analytics partners not declared, sending user content to a third-party AI service without disclosure and consent.
**Fix**: add the ATT prompt where tracking exists, declare the data in App Privacy, add a clear in-app disclosure and consent step before data goes to a third-party AI or analytics provider.
**Reply**: describe the consent screen and what data is covered.

## [5.1.5] Location services
**Means**: location must be needed and consent must be clear.
**Fix**: request only when and as much as needed, write a precise purpose string, make the feature optional.
**Reply**: say which feature uses location and why.

## [5.2] Intellectual property
**Means**: do not use others' trademarks, copyrighted content, or brand without rights.
**Triggers**: logos, names, characters, music, or text from others; app name that implies affiliation.
**Fix**: remove or replace, or add documentation of rights.
**Reply**: attach proof of license when you have it, otherwise state the removal.

## [5.3] Gaming, gambling and lotteries
**Means**: real-money gaming needs licensing and geo-restrictions; sweepstakes have extra rules.
**Fix**: provide licenses, restrict regions, or remove real-money features.
**Reply**: attach licenses and the geo-fencing explanation.

## [5.6] Developer code of conduct
**Means**: account-level conduct: (5.6.1) manipulating reviews or ratings, (5.6.2) developer identity, (5.6.3) discovery fraud, (5.6.4) quality of apps and repeated problems.
**Triggers**: incentivized reviews, spammy metadata patterns across apps, many rejected submissions of the same issue.
**Fix**: this is not fixed by editing one build. Stop the behavior, document the corrective actions, and reply to App Review or use the appeal route. Escalate early because it can affect the whole account.
**Reply**: factual and complete. State what changed in your process.

---

## Rejections that are not guideline numbers

**Binary processing errors (ITMS-9xxxx emails)**: these arrive by email right after upload, before review. Common examples: missing purpose string for a protected API (ITMS-90683), missing privacy manifest declaration for a required-reason API (ITMS-91053), SDK version below Apple's current minimum (ITMS-90725; in 2026 uploads need Xcode 26 or later with the matching SDK). Fix in the project and upload a new build with a higher build number. There is nothing to reply to in Resolution Center.

**Metadata-only rejection**: the version shows Metadata Rejected. Edit the metadata and reply; no new build is needed, but you still have to resubmit.

**Unresolved Issues does not mean waiting**: while a submission sits in Unresolved Issues nothing is queued for review. Reply in the Resolution Center, then resubmit from the App Store Connect web UI so the item goes back to Ready for Review. Developers have reported that the API returns 409 for submissions in this state, so do not plan to script the resubmission.

**Appeals**: reply in the Resolution Center first. If you still believe the guideline was misapplied, submit an appeal to the App Review Board through Apple's developer support. Be specific and factual, one issue per appeal.
