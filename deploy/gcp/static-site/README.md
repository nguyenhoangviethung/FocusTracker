# FocusFlow AI Static Download Portal

This folder contains the public landing page for the demo release downloads.

## Upload layout

Use a Cloud Storage bucket configured for static website hosting and upload:

- `index.html`
- `404.html`
- `style.css`
- `downloads/windows/FocusFlowAI-Windows.exe`
- `downloads/macos/FocusFlowAI-macOS.dmg`
- `downloads/linux/FocusFlowAI-Linux.AppImage`
- `docs/QuickStart.pdf`
- `docs/Checksums.txt`

## Public links

The landing page links to the release files using relative paths so the same
structure works both locally and in Cloud Storage.

## Notes

- Keep release binaries public only if the demo needs zero-friction access.
- Do not upload secrets, `.env` files, or service-account keys here.
- Cloud Run remains the API and session backend; this site is only for public
  client distribution.
