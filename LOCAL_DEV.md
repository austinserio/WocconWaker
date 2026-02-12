# Local development with Messenger

Run the app on your machine and receive Messenger webhooks at a stable URL using the **UIC Cloudflare** tunnel: `https://local-woccon.urbanindigenouscollective.org`.

## What you need

- **UIC Cloudflare** – Named tunnel so the webhook URL is always `https://local-woccon.urbanindigenouscollective.org/webhook` (no changing Facebook when you restart).
- **An app that allows webhook edits** – If your WocconWaker *development* app won’t let you change the webhook (Facebook sometimes locks this by app type/mode), use either:
  - Your **production WocconWaker app**: when developing locally, set its webhook to the tunnel URL; when done, set it back to the Azure URL, or
  - Your **Shocktalk dev app** (if it allows webhook changes): add the Woccon Page to that app for testing, or use that app’s page and token in `.env`.
- **`.env`** – `VERIFY_TOKEN`, `PAGE_ACCESS_TOKEN`, and optional LLM/Foundry vars.

---

## 1. UIC Cloudflare tunnel (local-woccon.urbanindigenouscollective.org)

Use the UIC Cloudflare account and a named tunnel so the hostname is fixed.

### One-time setup (UIC Cloudflare)

1. **Log in with UIC Cloudflare**
   ```bash
   cloudflared tunnel login
   ```
   Use the UIC Cloudflare account when the browser opens.

2. **Create the tunnel**
   ```bash
   cloudflared tunnel create local-woccon
   ```
   Note the tunnel ID (e.g. `abc123-def456-...`) from the output.

3. **Add DNS (Cloudflare dashboard or CLI)**  
   In the zone `urbanindigenouscollective.org`, add a CNAME:
   - **Name**: `local-woccon` (or `local-woccon.urbanindigenouscollective.org` depending on UI)
   - **Target**: `<TUNNEL_ID>.cfargotunnel.com`  
   (e.g. `abc123-def456-ghi789.cfargotunnel.com`)

   Or with Cloudflare API/CLI:
   ```bash
   cloudflared tunnel route dns local-woccon local-woccon.urbanindigenouscollective.org
   ```
   (run from the same machine/account that owns the zone)

4. **Create config file**  
   Save as `~/.cloudflared/config.yml` (or project-local `config.yml` and use `cloudflared tunnel --config config.yml run local-woccon`):

   ```yaml
   tunnel: <TUNNEL_ID>
   credentials-file: ~/.cloudflared/<TUNNEL_ID>.json

   ingress:
     - hostname: local-woccon.urbanindigenouscollective.org
       service: http://localhost:8000
     - service: http_status:404
   ```

   Replace `<TUNNEL_ID>` with the actual ID from step 2. Path to `credentials-file` is usually `~/.cloudflared/<TUNNEL_ID>.json` after `tunnel create`.

### Run the tunnel (when developing)

```bash
cloudflared tunnel run local-woccon
```

Leave this running. Your app will be reachable at **https://local-woccon.urbanindigenouscollective.org**. Webhook URL for Facebook: **https://local-woccon.urbanindigenouscollective.org/webhook**.

---

## 2. Create `.env` in the project root

```bash
# Required for Messenger (use token for the Page you're testing with)
VERIFY_TOKEN=test-key-beta
PAGE_ACCESS_TOKEN=your_page_access_token

# Server
WOCCON_MODE=server
PORT=8000

# Use Azure Foundry for chat (same as production) — no Ollama needed
LOCAL_LLM=false
FOUNDRY_ENDPOINT=https://woccon-foundry.services.ai.azure.com
FOUNDRY_API_KEY=your_foundry_api_key
FOUNDRY_DEPLOYMENT=Meta-Llama-3.1-8B-Instruct
FOUNDRY_API_VERSION=2024-05-01-preview

# Optional
ENABLE_TYPING_INDICATORS=true
```

Copy the Foundry vars from your Azure Container App. Use the same VERIFY_TOKEN in Facebook and the right Page Access Token for the Page you're testing with.

---

## 3. Start the app

```bash
pip install -r requirements.txt
python app.py
```

Or:

```bash
./run-local-messenger.sh
```

App listens on `http://0.0.0.0:8000`. Start the tunnel (step 1) in another terminal so `local-woccon.urbanindigenouscollective.org` forwards to it.

---

## 4. Point Facebook at the tunnel

1. Go to [developers.facebook.com](https://developers.facebook.com) → the app you’re using (production WocconWaker or Shocktalk dev, whichever allows webhook edits).
2. **Messenger** → **Configuration** → **Webhooks** → **Edit**.
3. **Callback URL**: `https://local-woccon.urbanindigenouscollective.org/webhook`
4. **Verify token**: same as in `.env` (e.g. `test-key-beta`).
5. **Verify and Save**. Subscribe to the same fields as production (e.g. `messages`, `messaging_postbacks`, …).

If your **WocconWaker dev app** won’t let you change the webhook:

- Use the **production WocconWaker app** for local dev: set its webhook to the tunnel URL while you develop, then set it back to `https://wocconwaker-app.icyglacier-d3593e65.eastus2.azurecontainerapps.io/webhook` when you’re done, or
- Use the **Shocktalk dev app** (where you can change the webhook): use that app’s page and token in `.env` and point its webhook at `https://local-woccon.urbanindigenouscollective.org/webhook`.

---

## 5. Test

Send a message to the Page tied to the app/token you’re using. You should see logs in the app terminal and get a reply from your local instance.

---

## 6. Switch back to production (if using production app for local dev)

When you’re done developing and you had pointed the **production** WocconWaker app at the tunnel:

1. **Webhooks** → **Edit**.
2. **Callback URL**: `https://wocconwaker-app.icyglacier-d3593e65.eastus2.azurecontainerapps.io/webhook`
3. **Verify and Save**.

---

## Webhook URL not resolving?

`https://local-woccon.urbanindigenouscollective.org` only works after this **one-time setup** (UIC Cloudflare):

1. **Log in** (browser opens):
   ```bash
   cloudflared tunnel login
   ```
   Use the UIC Cloudflare account that owns `urbanindigenouscollective.org`.

2. **Create the tunnel** and note the tunnel ID (e.g. `a1b2c3d4-e5f6-...`):
   ```bash
   cloudflared tunnel create local-woccon
   ```

3. **Add DNS** in Cloudflare (Dashboard → urbanindigenouscollective.org → DNS):
   - Type: **CNAME**
   - Name: **local-woccon**
   - Target: **`<TUNNEL_ID>.cfargotunnel.com`** (e.g. `a1b2c3d4-e5f6-....cfargotunnel.com`)
   - Save.

   Or add it via cloudflared (must be logged in as the **UIC** account that owns urbanindigenouscollective.org):
   ```bash
   cloudflared tunnel login   # sign in with UIC if you have multiple accounts
   ./setup-tunnel-dns.sh     # adds CNAME local-woccon.urbanindigenouscollective.org
   ```
   If you're logged into a different account (e.g. Shocktalk), the record would be created in that zone instead. Use the UIC account so the record is in urbanindigenouscollective.org.

4. **Create `cloudflared.yml`** in the project (copy from `cloudflared-example.yml`):
   - Set `tunnel:` to your tunnel ID.
   - Set `credentials-file:` to the path of the JSON file created in step 2 (usually `~/.cloudflared/<TUNNEL_ID>.json`).

5. Restart `./run-local-messenger.sh`. The script will use `cloudflared.yml` and the hostname should resolve in a minute or two.

To confirm: open `https://local-woccon.urbanindigenouscollective.org/health` in a browser (or curl). If you get JSON, the tunnel and app are good; then use `https://local-woccon.urbanindigenouscollective.org/webhook` in Facebook.

---

## Reference

| Item | Value |
|------|--------|
| Local app | `http://0.0.0.0:8000` |
| Public URL | `https://local-woccon.urbanindigenouscollective.org` |
| Webhook URL | `https://local-woccon.urbanindigenouscollective.org/webhook` |
| Tunnel | UIC Cloudflare named tunnel `local-woccon` |
