# Local development with Messenger

Run the app on your machine and receive Messenger webhooks at a stable URL using a **Cloudflare named tunnel** (or another HTTPS tunnel) pointing at your local app.

## What you need

- **Cloudflare** (or similar) – A named tunnel so the webhook URL is stable (e.g. `https://woccon-dev.example.com/webhook`).
- **A Meta app that allows webhook edits** – If your development app will not let you change the webhook, use an app that does, or temporarily point production at the tunnel and switch back when done (document your production callback URL in `.env` as `AZURE_CONTAINER_APP_WEBHOOK_URL` so you do not lose it).
- **`.env`** – Copy from `.env.example` and set `VERIFY_TOKEN`, `PAGE_ACCESS_TOKEN`, and LLM/Foundry vars. See [CLAUDE.md](CLAUDE.md).

Set optional convenience vars (used in docs and helper scripts):

- `CLOUDFLARE_TUNNEL_HOSTNAME` – e.g. `woccon-dev.example.com` (no `https://`).
- `PUBLIC_WEBHOOK_BASE_URL` – e.g. `https://woccon-dev.example.com` (for copy-paste webhook URL).
- `AZURE_CONTAINER_APP_WEBHOOK_URL` – production Messenger callback, e.g. `https://<your-app>.<region>.azurecontainerapps.io/webhook`.

---

## 1. Cloudflare tunnel (example)

Use a Cloudflare account that controls the DNS zone for your dev hostname.

### One-time setup

1. **Log in**
   ```bash
   cloudflared tunnel login
   ```

2. **Create the tunnel**
   ```bash
   cloudflared tunnel create woccon-dev
   ```
   Note the tunnel ID from the output.

3. **Add DNS** in your zone (e.g. `example.com`): CNAME from `woccon-dev` (or your chosen host) to `<TUNNEL_ID>.cfargotunnel.com`.

   Or:
   ```bash
   cloudflared tunnel route dns woccon-dev woccon-dev.example.com
   ```

4. **Config** – Copy [cloudflared-example.yml](cloudflared-example.yml) to `cloudflared.yml` (gitignored). Set `tunnel`, `credentials-file`, and `hostname` to match your tunnel and hostname.

### Run the tunnel

```bash
cloudflared tunnel --config cloudflared.yml run woccon-dev
```

Use `CLOUDFLARE_TUNNEL_HOSTNAME=woccon-dev.example.com` in `.env` so scripts and docs stay consistent.

---

## 2. Create `.env` in the project root

```bash
cp .env.example .env
```

Edit `.env`: set Messenger tokens, `WOCCON_MODE=server`, `PORT`, and either local Ollama (`LOCAL_LLM=true`) or Foundry (`FOUNDRY_*`). See [.env.example](.env.example) and [CLAUDE.md](CLAUDE.md).

---

## 3. Start the app

**Full local stack (recommended)** — Messenger tunnel + backend + control panel dev UI in one terminal:

```bash
./run-local-full.sh
```

- Panel UI: `http://localhost:5173/panel/login`
- Backend: `http://127.0.0.1:8000`
- Messenger webhook: `https://<CLOUDFLARE_TUNNEL_HOSTNAME>/webhook` (printed on startup)
- Ctrl+C stops tunnel, backend, and Vite together
- Stop stale processes: `./run-local-full.sh --stop`

**Messenger only** (tunnel + backend, no Vite dev server):

```bash
./run-local-messenger.sh
```

App listens on `http://0.0.0.0:8000`. With a built panel (`cd panel && npm run build`), the admin UI is also at `http://localhost:8000/panel/`.

**Manual start:**

```bash
pip install -r requirements.txt
python app.py
```

Then run the tunnel in another terminal so your public hostname forwards to port 8000.

---

## 4. Point Facebook at the tunnel

1. [developers.facebook.com](https://developers.facebook.com) → your app → **Messenger** → **Webhooks** → **Edit**.
2. **Callback URL**: `https://<CLOUDFLARE_TUNNEL_HOSTNAME>/webhook` (or `PUBLIC_WEBHOOK_BASE_URL` + `/webhook`).
3. **Verify token**: same as `VERIFY_TOKEN` in `.env`.
4. Subscribe to the same fields as production.

If you temporarily moved **production** webhooks to your tunnel, set **Callback URL** back to `AZURE_CONTAINER_APP_WEBHOOK_URL` when finished.

---

## 5. Test

Send a message to the Page tied to the app/token in `.env`. You should see logs and a reply from your local instance.

---

## Webhook URL not resolving?

1. Confirm `cloudflared tunnel login` used the account that owns your DNS zone.
2. CNAME target must be `<TUNNEL_ID>.cfargotunnel.com`.
3. Project `cloudflared.yml` must match tunnel ID and credentials path.
4. Health check: `https://<your-hostname>/health` should return JSON when the app and tunnel are running.

Optional: set `CLOUDFLARE_TUNNEL_ID` and `CLOUDFLARE_TUNNEL_HOSTNAME` in `.env` and run `./setup-tunnel-dns.sh` once (after `cloudflared tunnel login`) to add DNS via CLI.

---

## Database environments

| Environment | `DATABASE_URL` | Notes |
|-------------|----------------|--------|
| **Local dev** | `sqlite:///./data/woccon.db` | Default; safe for experiments |
| **Production** (Azure Container App) | Postgres via secret `database-url` | Set with `./scripts/setup-azure-postgres.sh` + `./scripts/sync-azure-container-env.sh` |

Keep **`POSTGRES_DATABASE_URL`** in `.env` for migration, Azure sync, and pulling prod data—leave **`DATABASE_URL`** on SQLite for day-to-day local work.

```bash
# One-time: provision Postgres and migrate **current** local SQLite → prod
./scripts/setup-azure-postgres.sh
# Add POSTGRES_DATABASE_URL to .env (printed by setup script)
./scripts/migrate_sqlite_to_postgres.py          # uses ./data/woccon.db (backs up first)
./scripts/migrate_library_from_sqlite.py         # re-sync Library only from current local DB
./scripts/sync-azure-container-env.sh

# Refresh local SQLite from production (stop local app first)
./scripts/pull_panel_db_from_postgres.sh

**Source of truth:** always `./data/woccon.db` on your machine. Do not point migration scripts at old files under `data/backups/` unless you intentionally mean to restore history.

**Regions:** Postgres is in **Central US** (East US 2 is not available for Flexible Server on this subscription). The Container App is in **East US 2**, which adds latency. Prefer moving the app to Central US when you can; do not move Postgres to East US 2 until Azure allows it.
```

Do not run `reset_panel_db.py --wipe` while `DATABASE_URL` or `POSTGRES_DATABASE_URL` points at production Postgres.

---

## Reference

| Item | Typical value |
|------|----------------|
| Start everything | `./run-local-full.sh` |
| Panel UI (dev) | `http://localhost:5173/panel/login` |
| Local app | `http://0.0.0.0:8000` |
| Public base | Set `PUBLIC_WEBHOOK_BASE_URL` in `.env` |
| Webhook URL | `{PUBLIC_WEBHOOK_BASE_URL}/webhook` |
| Stop stale dev processes | `./run-local-full.sh --stop` |
| Refresh local DB from prod | `./scripts/pull_panel_db_from_postgres.sh` |
