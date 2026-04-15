# Security

## Reporting a vulnerability

Please report security-sensitive issues privately to the repository maintainers (open a **private** security advisory on GitHub if enabled, or contact the project owners directly). Do not file public issues for undisclosed vulnerabilities.

## Before making this repository public

1. **Scan full git history** for secrets (e.g. [gitleaks](https://github.com/gitleaks/gitleaks) or [TruffleHog](https://github.com/trufflesecurity/trufflehog) with history enabled), not only the latest commit.
2. Ensure **`.env`**, service account JSON keys, and Cloudflare credential files are **never committed** (see [.gitignore](.gitignore)).
3. If any real **API key, token, or password** ever appeared in git history, **rotate** that credential everywhere it was used, then remove it from history (e.g. `git filter-repo`) or publish from a clean snapshot.

Operational values (subscription IDs, resource names, hostnames) should live in a local `.env` or GitHub **Secrets/Variables**, not in committed source. Use [.env.example](.env.example) as the template.

## GitHub Actions

Store `AZURE_CREDENTIALS`, `FOUNDRY_API_KEY`, and related values in **Actions secrets**. Store non-secret configuration such as `AZURE_RESOURCE_GROUP` and `AZURE_CONTAINER_APP_NAME` in **Actions variables**. See [.github/workflows/deploy-azure-foundry.yml](.github/workflows/deploy-azure-foundry.yml).
