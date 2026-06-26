# FocusFlow AI Static Download Portal

This folder contains the public landing page for the demo release downloads.

## Upload layout

Use a Cloud Storage bucket configured for static website hosting and upload:

- `index.html`
- `404.html`
- `style.css`
- `releases/latest/FocusFlowAI-Windows.exe`
- `releases/latest/FocusFlowAI-macOS.dmg`
- `releases/latest/FocusFlowAI-Linux.tar.gz`
- `releases/latest/SHA256SUMS.txt`
- `docs/QuickStart.pdf`

## Public links

The Cloud Run `/download` page can point to the same objects with:

```text
FOCUSFLOW_RELEASE_BASE_URL=https://storage.googleapis.com/<bucket>/releases/latest
```

The static landing page can still be uploaded to the bucket for a pure Cloud
Storage download portal. The release binary layout stays the same.

## Notes

- Keep release binaries public only if the demo needs zero-friction access.
- Do not upload secrets, `.env` files, or service-account keys here.
- Cloud Run remains the API and session backend; this site is only for public
  client distribution.
