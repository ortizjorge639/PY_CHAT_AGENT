# Deployment Learnings — Customer Engagement (Week of 2026-04-28)

This document captures the key discoveries and fixes from the customer
deployment troubleshooting session. Use it as a checklist for future
deployments of this bot to new customer environments.

---

## 1. Hybrid Connection Setup (Azure Relay → On-Prem SQL Server)

The customer's SQL Server lives on-premises. Azure App Service reaches it
through an **Azure Relay Hybrid Connection**.

**Steps that must all be true simultaneously:**

1. An **Azure Relay** resource exists with a Hybrid Connection endpoint
   configured. The endpoint hostname and port must match the `SQL_SERVER`
   and `SQL_PORT` values the app uses (see #6 below).

2. The **Hybrid Connection Manager (HCM)** application is installed on an
   on-prem machine that can reach SQL Server. It does **not** have to run
   on the same machine as SQL Server, but co-locating them is preferred
   (simplest networking, lowest latency).

3. The **connection string from the Azure Relay resource** is copied into
   the HCM application's configuration.

4. Both sides show **"Connected"**:
   - HCM application on the on-prem machine → status: Connected
   - Azure Portal → Azure Relay → Hybrid Connection → status: Connected

If either side shows "Not Connected," traffic will not flow regardless of
how the app is configured.

---

## 2. SQL Credentials — App Service & Local `.env`

The customer uses **SQL authentication** (username + password), not Windows
Integrated auth.

**What was wrong:**
- Local `.env` had outdated/missing SQL credentials
- `SQL_TRUSTED_CONNECTION` was set to `yes` (Windows auth doesn't exist on App Service — fails silently)

**What we fixed:**
- Set `SQL_TRUSTED_CONNECTION=no`
- Obtained correct `SQL_USERNAME` / `SQL_PASSWORD` from sysadmin
- Configured credentials in **both** Azure App Service env vars **and** local `.env`

| Setting | Value | Why |
|---------|-------|-----|
| `SQL_TRUSTED_CONNECTION` | `no` | SQL auth. If accidentally `yes`, connection fails silently on App Service. |
| `SQL_USERNAME` | *(sysadmin-provisioned)* | Must match the login granted access to the target database/table. |
| `SQL_PASSWORD` | *(corresponding password)* | Same login. |

---

## 3. Deployment Fix — Startup Command in the Pipeline YAML

**What was wrong:**
- Pipeline deployed via `runFromPackage` but had no startup command
- App Service tried `python main.py` directly → `ModuleNotFoundError` for every dependency
- Root cause: `runFromPackage` mounts the ZIP read-only; Oryx never runs; the bundled venv doesn't auto-activate

**What we fixed:**
- Added explicit startup command in `azure-pipelines-customer.yml`:

```yaml
startUpCommand: '. antenv/bin/activate && python main.py'
```

Key points:
- Use `.` (dot) not `source` — App Service runs `sh`, not `bash`
- The venv must be **bundled inside the ZIP** during the build stage
  (the pipeline creates it and installs deps before archiving)

---

## 4. HCM Endpoint Hostname Must Match `SQL_SERVER`

**What was wrong:**
- `SQL_SERVER` env var used a hostname/IP that didn't match the Azure Relay
  Hybrid Connection endpoint definition → connection silently failed

**What we fixed:**
- Set `SQL_SERVER` to the **exact hostname** registered in the Hybrid Connection endpoint

Example: if the Hybrid Connection endpoint is `sqlserver01:1433`, then:
- `SQL_SERVER=sqlserver01` ✅
- `SQL_SERVER=sqlserver01.corp.local` ❌ (FQDN won't match)
- `SQL_SERVER=10.0.0.50` ❌ (IP won't match)

A mismatch means Azure Relay has no route for the hostname the app is
requesting, and the connection silently fails.

---

## 5. Teams Excel Download Links — `BASE_URL` Required

**What was wrong:**
- Excel download links in Teams returned 404 or failed to resolve
- The app generated relative paths (`/api/files/filename.xlsx`)
- In the Teams webview, relative URLs resolve against Teams' own domain, not the app's domain

**What we fixed (code changes across 3 files):**

1. **`config/settings_customer.py`** — Added `base_url: str = ""` field to the `Settings` class
2. **`agent/plugins/data_plugin_customer.py`** — Added `base_url` parameter to
   `create_data_tools()` and updated `_generate_excel()` to prepend it:
   ```python
   file_url = f"{base_url}/api/files/{filename}" if base_url else f"/api/files/{filename}"
   ```
3. **`agent/kernel_customer.py`** — Passed `base_url=settings.base_url` when calling
   `create_data_tools()` so the setting flows from env vars → kernel → plugin

**Environment variable:**

| Where | Setting | Example value |
|-------|---------|---------------|
| App Service env vars | `BASE_URL` | `https://fobsolescence-chat.extron.com` |
| Local `.env` | `BASE_URL` | *(can be blank for local dev — falls back to relative)* |

---

## Quick Reference — App Service Environment Variables

| Variable | Required | Notes |
|----------|----------|-------|
| `AZURE_OPENAI_ENDPOINT` | Yes | |
| `AZURE_OPENAI_API_KEY` | Yes | |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Yes | e.g. `gpt-4o` |
| `DATASOURCE` | Yes | `sql` for the customer |
| `SQL_SERVER` | Yes | Must match Hybrid Connection endpoint hostname |
| `SQL_PORT` | Yes | Usually `1433` |
| `SQL_DATABASE` | Yes | |
| `SQL_TABLE` | Yes | Schema-qualified, e.g. `operations.Obsolescence_Results` |
| `SQL_TRUSTED_CONNECTION` | Yes | `no` (SQL auth) |
| `SQL_USERNAME` | Yes | Sysadmin-provisioned login |
| `SQL_PASSWORD` | Yes | Corresponding password |
| `MICROSOFT_APP_ID` | Yes | Entra app registration |
| `MICROSOFT_APP_PASSWORD` | Yes | Client secret |
| `MICROSOFT_APP_TENANT_ID` | Yes | |
| `BASE_URL` | Yes | Public-facing URL for Teams file downloads |
| `GENERATED_DIR` | Yes | `/tmp/generated` (runFromPackage is read-only) |
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | Yes | `0` (deps bundled in ZIP) |
