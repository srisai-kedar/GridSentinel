# GridSentinel backend deployment steps

These are the existing Render deployment steps for the backend. This change does not deploy or promote anything.

## Pre-deploy checks

From the repository root, on the reviewed branch:

```powershell
git status --short
git rev-parse HEAD
Get-FileHash backend/models/fusion_classifier.joblib -Algorithm SHA256
```

Confirm the model hash is the protected production hash recorded in `AGENTS.md`. Do not include datasets, reports, credentials, or unrelated work in the deploy commit.

## Deploy through the existing Render service

Render is configured to deploy the backend from the repository's deployment branch. After the focused change has been reviewed and approved, the repository-side command is:

```powershell
git push origin main
```

Render then builds `backend/Dockerfile` and starts the configured command:

```text
uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

Do not create a new Render service or change the public URL. If the repository uses a protected branch, merge the reviewed pull request through GitHub and let the existing Render auto-deploy complete instead of bypassing branch protection.

## Verify the deployed commit and model

```powershell
$base = "https://gridsentinel-72tf.onrender.com"
Invoke-RestMethod "$base/health"
Invoke-RestMethod "$base/version" | ConvertTo-Json
Invoke-RestMethod "$base/classifier/status" | ConvertTo-Json
```

`/version` must show the intended `git_sha`, and `/classifier/status` must show `is_loaded: true`. Confirm the model path and decision threshold are unchanged. A deployment is not verified from a successful build alone.

## Roll back

Use the existing Render service dashboard: open the service, open **Deploys**, select the last known-good deploy, and choose **Rollback**. Then rerun the same three endpoint checks above and confirm that `/version.git_sha` is the rolled-back commit. Do not replace the model file manually on the server.

For an emergency repository rollback after approval, revert the focused commit through a reviewed pull request; do not force-push or reset a shared branch.
