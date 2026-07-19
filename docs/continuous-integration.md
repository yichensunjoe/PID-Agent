# Continuous integration

GitHub Actions runs the repository's deterministic validation on every push to `main` and on every pull request.

## Automated checks

The workflow in `.github/workflows/ci.yml` runs two independent Ubuntu jobs:

- Python 3.11: install `.[mcp,dev]`, run `ruff check backend`, then `pytest -q`;
- Node.js 24: install frontend dependencies and run `npm run build`.

The backend runner installs the Cairo runtime required by SVG/PNG export tests. No model-provider credentials are used by CI.

## Manual acceptance checks

The following checks remain manual because they require external services, local hardware, credentials, or longer execution time:

- real-provider `pid-agent model-matrix` runs;
- the full 500/1000/2500/5000-element performance benchmark;
- interactive engineering drawing acceptance and diagnostic-package review.

These manual results should be committed under `reports/` only after confirming that API keys, authorization headers, prompts, and confidential engineering data are absent.
