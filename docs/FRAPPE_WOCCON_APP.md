# Woccon Language app for Frappe (control panel)

## Where the app lives: separate repo, not inside Frappe or WocconWaker

- **WocconWaker** (this repo): ingest, extraction, merge, API. No Frappe code.
- **Frappe app**: a **separate repo** (e.g. `woccon_language` or `woccon-frappe`) that you maintain on its own. It is installed into a Frappe bench with `bench get-app <repo_url>` and `bench install-app woccon_language`.
- **frappe-learning** (your bench): just one place you *install* the app for development or testing. You don’t develop the app inside the frappe-learning repo; you develop it in the woccon_language repo and pull it in.

So: build the plugin as a **standalone, installable app** in its own repo; keep it maintained separately from both WocconWaker and the Frappe bench.

---

## Your Frappe instance (for testing the app)

- **Path:** `/Users/personal/Documents/frappe-learning`
- **Bench:** `frappe-learning/frappe-bench`
- **Frappe:** 16.0.0-dev
- **Site:** `lms.localhost` (default)

You install the Woccon app into this bench (or any other Frappe 16 site) from its own repo.

---

## Recommendation: standalone app repo `woccon_language`

1. **Create the app in its own repo** (not inside frappe-learning or WocconWaker):
   ```bash
   # e.g. in a folder like ~/repos or alongside WocconWaker
   cd /path/to/your/repos
   bench init woccon-bench --frappe-branch version-16   # only if you don't have a bench yet
   cd woccon-bench
   bench new-app woccon_language
   ```
   Or: create a new Git repo, then run `bench new-app woccon_language` inside a temporary bench and **move** the generated `apps/woccon_language` folder into your new repo (then add setup.py, pyproject.toml, etc. so it’s installable with `bench get-app`).

2. **Publish the app repo** (GitHub/GitLab, etc.) so you can install it anywhere:
   ```bash
   bench get-app https://github.com/your-org/woccon_language
   bench --site lms.localhost install-app woccon_language
   ```
   On frappe-learning you’d do the same: `cd frappe-bench && bench get-app <your-repo-url>` so the app is cloned into `apps/woccon_language` and you can install it on `lms.localhost` for testing.

3. **Add a dedicated module** (optional but clearer for “language” vs default “Woccon Language”):
   - In `woccon_language/modules.txt` add a line, e.g. `Woccon Language` (or split later into Lexicon, Grammar, etc.).
   - DocTypes will live under that module so they appear under one group in the Desk.

4. **Add DocTypes** (via bench or JSON). Suggested set:

   | DocType | Purpose | Key fields |
   |--------|---------|------------|
   | **Source Document** | Library: uploaded/linked file | title, file_url (or attach), drive_link, source_type (Upload / Drive Link), status, azure_storage_id (optional) |
   | **Pending Lexicon Entry** | From extraction, awaiting review | woccon, english, pos, pronunciation, source_document (Link), source_url, status (Pending / Approved / Rejected / Modified), notes |
   | **Pending Rule** | Grammar/pronunciation/cultural note from extraction | category (Grammar / Pronunciation / Cultural), content (Text), source_document, source_url, status |
   | **Lexicon Entry** | Canonical lexicon (committed) | woccon, english, pos, pronunciation, source_url, source_document (optional) |
   | **Language Rule** (or split by category) | Canonical rules (committed) | category, name/label, content, source_url |

   You can start with **Source Document** and **Pending Lexicon Entry** only, then add Pending Rule and canonical DocTypes when you add “Commit” workflow.

5. **Desk “tabs” (navigation)**  
   - In Frappe 16, list views and forms are under **Desk → Module → DocType**.  
   - To get “tabs” (Lexicon, Grammar, Pronunciation, etc.):
     - **Option A:** One module “Woccon Language” with multiple DocTypes; use **Workspace** (Desk) to create a “Woccon Control Panel” workspace with shortcuts to each DocType list (e.g. Lexicon, Grammar, Library).  
     - **Option B:** Multiple modules (e.g. “Woccon Lexicon”, “Woccon Grammar”, “Woccon Library”) so the sidebar shows those as separate groups.

6. **Source link on each line**  
   - On **Pending Lexicon Entry** and **Pending Rule**, add a **Data** or **Small Text** field `source_url` (and optionally **Link** to **Source Document**). In the list view, show `source_url` and make it a clickable link (formatter or custom list column).

7. **Upload and extraction**  
   - **Option A (simplest):** A **Custom** or **Server Script** (or a **Woccon Settings** DocType with “Upload” button) that:
     - Accepts file upload or Drive link.
     - Calls your WocconWaker API (e.g. `POST /upload` or `POST /admin/ingest-drive` with body), or saves file to Drive + Azure and then triggers extraction (e.g. background job or queue).
   - **Option B:** Build a **Web Form** or **Page** that posts to WocconWaker; WocconWaker stores file (Drive + Azure), runs Sonnet extraction, then pushes extracted JSON to Frappe via a **whitelisted API** (e.g. `POST /api/method/woccon_language.api.import_pending_entries`) that creates **Pending Lexicon Entry** and **Pending Rule** records.

   The plan (PLAN.md) assumes: upload/link → WocconWaker stores file and runs extraction → structured data is “for review” in Frappe. So either Frappe calls WocconWaker to ingest, or WocconWaker (after extraction) calls Frappe to create pending records. Either way, the add-on only needs to **display and edit** pending + canonical data; the heavy lifting stays in WocconWaker.

8. **Approve / Reject / Commit**  
   - **Pending Lexicon Entry** and **Pending Rule**: add a **Select** field `status` (Pending, Approved, Rejected, Modified). Use **Actions** or **Custom Button** “Approve” / “Reject” that updates status.  
   - **Commit:** A **Server Script** or **DocType method** that:  
     - Finds all Pending* with status = Approved (and optionally Modified).  
     - Creates or updates **Lexicon Entry** / **Language Rule** from them.  
     - Optionally exports to JSON (e.g. `dictionary_unified.json`) or calls WocconWaker reload API.  
   - You can later add “Commit” as a **Workflow** (Workflow DocType) or a simple “Commit” button on a Workspace.

---

## Where the app code lives

- **Canonical home:** Its **own repo** (e.g. `woccon_language`). You develop and maintain the app there.
- **In a bench:** The app is only *installed* via `bench get-app <repo_url>`, which clones it into `apps/woccon_language`. frappe-learning is just one bench where you install it for testing; you don’t commit Frappe app code inside the frappe-learning repo.
- **Extension only:** Don’t modify `frappe` or `lms`; all Woccon UI and DocTypes live in the `woccon_language` app. Ingest/extract stays in WocconWaker.

---

## Summary

- **Build:** Standalone app repo `woccon_language`, installable on any Frappe 16 bench with `bench get-app` + `bench install-app woccon_language`.
- **Structure:** One (or more) modules, DocTypes for Source Document, Pending Lexicon Entry, Pending Rule, and (when you add commit) Lexicon Entry and Language Rule; source_url (and optional Source Document link) on each pending/canonical line.
- **Tabs:** Use Desk Workspace + DocType list views, or multiple modules (Lexicon, Grammar, Library).
- **Upload/extract:** Handled by WocconWaker; Frappe either triggers it (API call) or receives results (API from WocconWaker to create Pending* records).
- **Commit:** Script or button that copies Approved pending records into canonical DocTypes and optionally notifies WocconWaker to reload.

If you want, the next step can be scaffolding `woccon_language` (e.g. `bench new-app` plus first DocTypes and a minimal Workspace) under `frappe-learning/frappe-bench/apps/` so you have a runnable starting point.
