# Report format

Both modes end with one JSON file that `scripts/render_report.py` turns into an HTML page,
which you then publish as an artifact. You write this JSON yourself after analysis; the scan
outputs are inputs to it, not the report.

```json
{
  "kind": "rejections",                 // or "preflight"
  "title": "Velozdev Apps App Review",  // a name, 2-4 words: "<account or app> App Review" or "<App> Submission Check"
  "generated": "2026-10-17",
  "source": "API key",                  // "API key" | "browser" | "project scan"
  "summary": "Two apps have open rejections; both need a new build.",   // one or two sentences, optional
  "stats": [[3, "apps checked"], [2, "open now"]],                      // optional; defaults are derived
  "patterns": [                          // optional, rejections only
    {"guideline": "2.1", "apps": ["Alpha Notes", "Beta Timer"],
     "cause": "demo account missing its password", "fix": "keep one reviewer account in a shared checklist"}
  ],
  "groups": [                            // one per app (rejections) or one per area/target (preflight)
    {
      "name": "Alpha Notes",
      "bundle_id": "com.example.alphanotes",   // rejections: needed so the history can match projects later
      "version": "2.0",                        // rejections: the version reviewed
      "subtitle": "Version 2.0 (build 45) · iOS",
      "link": "https://appstoreconnect.apple.com/apps/1234567890",   // optional, https only
      "clean_note": "No problems found.",                             // shown when findings is empty
      "findings": [
        {
          "guideline": "5.1.1(v)",
          "title": "Account deletion",
          "status": "open",              // rejections: "open" | "past"; preflight: "likely" | "possible";
                                         // preflight history group: "repeat" | "manual" | "fixed"
          "date": "2026-10-02",          // rejections: review date, kept in the history
          "previously_rejected": [{"app": "Beta Timer", "version": "1.0"}],   // preflight: copied from the scan
          "severity": "high",            // preflight: "high" | "medium" | "low"; optional for rejections
          "fix_type": "New build",       // "Metadata only" | "New build" | "Information only" | "Account-level"
          "said": "The app supports account creation but does not include ...",   // reviewer's words; omit in preflight
          "why": "Sign-up exists in AuthView.swift but there is no delete flow.",
          "evidence": [{"file": "App/AuthView.swift", "line": 42, "snippet": "Auth.auth().createUser(...)"}],
          "fix": ["Add Settings > Account > Delete Account", "Call user.delete() and remove their data", "Upload build 46"],
          "reply": "Hello, we added account deletion in Settings > Account > Delete Account in build 46. ..."
        }
      ]
    }
  ],
  "next_steps": ["Fix Alpha Notes 5.1.1(v) and upload build 46", "Edit Beta Timer screenshots and reply"],
  "notes": ["Resolution Center messages read in the browser on 2026-10-17.", "Static checks cannot see metadata or runtime crashes."]
}
```

Rules:
- Order groups by urgency (open before past; high before low), and findings the same way
  within a group.
- Keep text plain. Don't put HTML in fields; the renderer escapes everything.
- Never put secrets in the report: no passwords, demo credentials, API keys, contact
  details, or key IDs. Evidence snippets from preflight are already masked; keep them that way.
- In preflight, include only findings you confirmed by reading the code. Put "possible"
  ones you couldn't confirm in the report only if they're worth the user's attention, with
  `status: "possible"`. Add the scanner's `not_checked` items to `notes` in one line.
- In rejections reports, `said` quotes or closely paraphrases the reviewer. Keep it short.
  Fill `bundle_id`, `version` and `date` whenever you know them, since `history.py import`
  stores them and the submission check matches projects by bundle ID.
- In a preflight checked against history, the first group is "Past rejections, checked
  again" (see `preflight.md`), and `stats` should lead with the repeat count, e.g.
  `[[2, "past rejections repeat"], [1, "to check by hand"], [4, "other high risk"]]`.
- Write the report in the user's language. Write reply drafts in English unless the user asks
  for another language, since that's what App Review reads most reliably.
