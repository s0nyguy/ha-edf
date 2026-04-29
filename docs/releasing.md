# Release Process

Use this process when publishing a HACS-installable release.

## Prerequisites

- `main` is green in GitHub Actions.
- `custom_components/edf_kraken/manifest.json` has the version you want to release.
- The version uses semantic versioning, for example `0.1.0`.

## Create A Release

1. Make sure local `main` is up to date:

   ```powershell
   git switch main
   git pull --ff-only origin main
   ```

2. Read the version from `manifest.json`.

3. Create and push a matching tag:

   ```powershell
   git tag v0.1.0
   git push origin v0.1.0
   ```

4. GitHub Actions will run the release workflow.

The release workflow validates that the tag version matches `manifest.json`, builds `edf_kraken.zip`, and creates a GitHub release with generated notes.

## HACS Notes

- HACS can install from the default branch, but tagged GitHub releases provide stable installable versions.
- If HACS reports that a commit SHA version cannot be used, create a tagged release that matches the manifest version.
- Keep `hacs.json` in the repository root.
- Keep all integration runtime files under `custom_components/edf_kraken`.
