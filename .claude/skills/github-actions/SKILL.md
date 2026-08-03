# GitHub Actions Review

Focus on when reviewing `.github/workflows/`:

- Every `uses:` action reference is pinned to a full 40-character commit
  SHA with a trailing `# vX.Y.Z` comment — no tag or branch references.
- `permissions:` is declared at the workflow level as `contents: read`
  only, with no elevated or write permissions.
- Triggers are limited to exactly what's needed (push to main, PR to
  main, `workflow_dispatch`) — no unnecessary trigger surface.
- The Python version matrix matches what the project claims to support.
- No publishing, artifact upload, or external network calls beyond
  standard package installation.
