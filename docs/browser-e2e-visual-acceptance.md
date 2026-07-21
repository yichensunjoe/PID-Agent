# Browser E2E and visual acceptance

P&ID-Agent uses Playwright to validate real browser behavior against the real FastAPI document service and a production Vite build. The suite is deterministic: every test creates an isolated SQLite database, creates its own engineering document through REST, and never calls a real model provider.

## Install

Install the normal project and frontend dependencies first:

```bash
python -m pip install -e ".[mcp,dev]"
cd frontend
npm ci
npx playwright install --with-deps chromium
```

On a workstation where Chromium runtime dependencies are already installed, `npx playwright install chromium` is sufficient. CI always uses `--with-deps`.

## Run headless or headed

From `frontend/`:

```bash
# Build the deterministic E2E bundle and run every browser check.
npm run test:e2e

# Open Chromium and show the interactions.
npm run test:e2e:headed

# Run one file or one named scenario.
npm run build:e2e
npx playwright test e2e/engineering.spec.ts
npx playwright test --grep "Agent ghost preview"
```

The Playwright web servers start:

- FastAPI on `127.0.0.1:8000`, with a unique database and diagnostics file under `frontend/test-results/`;
- the production Vite preview on `127.0.0.1:4173`.

The E2E build exposes a test-only bridge for reading structured workspace state and injecting a deterministic Agent preview. Normal development and production builds do not expose that bridge.

## Failure evidence and traces

A failing scenario retains a screenshot, trace, video, and browser/API context under `frontend/test-results/playwright/`. The HTML report is written to `frontend/test-results/playwright-report/`.

Open a trace with:

```bash
cd frontend
npx playwright show-trace test-results/playwright/<scenario>/trace.zip
```

In GitHub Actions, the `Browser acceptance · Chromium` job uploads these directories only when the job fails. Artifacts are retained for seven days. The job uses deterministic fixture data and no Provider API key.

## Visual baselines

Visual snapshots use a fixed 1440 × 960 viewport, `zh-CN`, the `Asia/Shanghai` timezone, reduced motion, a fixed test clock, deterministic fixture names, and an E2E stylesheet that disables animation and pins the UI font stack. Baselines live in:

```text
frontend/e2e/visual.spec.ts-snapshots/
```

Update them only after reviewing the rendered result:

```bash
cd frontend
npm run test:e2e:update
```

A product regression is a change that was not intended by the implementation: clipped controls, lost engineering elements, changed connector colors, missing lock/anchor/ghost affordances, incorrect panel state, or unstable text/layout. A legitimate visual change is an explicitly reviewed product modification whose affected screenshots match the approved design. Do not update snapshots merely to make CI green; inspect the actual, expected, and diff images first.

Baselines must never contain API keys, authorization headers, local user paths, random IDs, private engineering data, videos, traces, or generated reports. Only the reviewed PNG baselines are committed.

## Automatic acceptance coverage

The pull-request job automatically verifies:

- document creation and persistence after reload;
- browser placement of two devices and a connector drawn from real source/target ports;
- endpoint binding and orthogonality after moving connected equipment;
- junction/branch topology and `main_route_id` preservation;
- route segment editing, obstacle avoidance, locked route anchors, and bend insertion;
- alignment, distribution, grouping, group movement, element locks, and mixed-value bulk editing;
- one canvas command and one selection command through the command palette;
- inline insertion of a two-port device into a main line;
- light/dark appearance without engineering SVG color or revision changes;
- named views, minimap navigation, automatic large-diagram zones, and fit-selection;
- deterministic Agent ghost preview without a revision change, followed by apply and undo;
- ten visual regression states;
- opening, zooming, panning, selecting, minimap navigation, and fit-selection on a 500-element drawing with deliberately broad CI limits.

Assertions inspect the persisted document, element counts, revisions, endpoint IDs and port IDs, route metadata, lock/group metadata, styles, labels, and orthogonal points. They do not pass solely because a button is present.

## Manual acceptance still required

The normal pull-request workflow does not replace:

- real-provider model-matrix checks with user-supplied credentials;
- subjective review of complex, production-scale engineering drawings;
- the separate 1000/2500/5000-element benchmark suite;
- platform-specific headed checks outside Chromium/Linux;
- review of a visual baseline change before the new PNG is accepted.
