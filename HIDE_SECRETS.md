Hiding secrets
===============

This repository should not contain long-lived secrets. Follow the steps below to hide secrets from the repo and replace them with placeholders.

1. Backup current secrets (if you haven't already).
   - Use Supabase dashboard to create a DB snapshot and store your Firebase service account JSON securely.

2. Run the included helper (recommended):
   - From the backend folder, run PowerShell:
     .\scripts\secrets_cleanup.ps1
   - This will:
     - Move .env -> .env.local (your real secrets are preserved locally in .env.local)
     - Create a placeholder .env for developers to copy from
     - Rename app/core/firebase-service-account.json -> app/core/firebase-service-account.json.secret

3. Verify and reconfigure local development:
   - Restore your real secrets into .env.local and keep it outside version control.
   - For CI/deploy, set environment variables in the host (Render/Railway/Supabase) rather than committing secrets.

4. .gitignore already includes .env and the firebase service account JSON to avoid accidental commits.

If you want, I can run the cleanup script here (will move files in this workspace). Otherwise run it locally where you keep the secrets.
