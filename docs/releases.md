# Releases & Docker Publishing

Remy now ships SemVer-tagged releases and a Docker image for the CLI via GitHub Actions.

## How to cut a release

1. Make sure `main` is green (lint, typecheck, pytest) and pushed.
2. Choose the next SemVer tag in the form `vMAJOR.MINOR.PATCH`.
3. Tag and push:
   ```bash
   git tag v0.2.0
   git push origin v0.2.0
   ```
4. The `Remy Release` workflow (see `.github/workflows/release.yml`) runs automatically and will:
   - Verify the tag matches SemVer.
   - Create a GitHub Release with generated notes.
   - Build the CLI Docker image from `docker/Dockerfile.cli`.
   - Push multi-arch images to GitHub Packages (GHCR).

## Docker image details

- Registry: `ghcr.io/<owner>/remy-cli`
- Tags published per release:
  - `vX.Y.Z` (exact tag, e.g., `v0.2.0`)
  - `X.Y.Z` (SemVer without the leading `v`)
  - `latest`
- Entrypoint: `remy` (default command `--help`)

Example usage:

```bash
docker pull ghcr.io/michaelasper/remy-cli:latest
docker run --rm ghcr.io/michaelasper/remy-cli:latest plan path/to/context.json --pretty
```
