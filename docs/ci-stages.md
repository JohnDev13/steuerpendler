# Verification stages and current authorization blocker

## What is actually checked
Local `npm test`, `npm run build` and production-build Playwright smoke tests are executable. These are local checks, **not GitHub CI**.

## GitHub permission blocker
On 17 October 2026 GitHub rejected the workflow upload because the connected OAuth credential lacks `workflow` scope. No workflow was pushed or activated, and no CI success is claimed. The canonical local project retains the workflow sources; they can be added through a reviewed PR after the owner grants the required permission.

The owner authorized a public repository and a GitHub Pages **test preview** in chat. Branch-based Pages publishing is the least-privilege fallback: build/test locally, publish static output on `gh-pages`, never push directly to main. This is not production-launch authorization.

Tax/map/travel feature acceptance, ESTV/SBB official references, owner golden, content approval, exact licensing/launch review and production release remain independent gates. Synthetic or preflight tests never establish nationwide data acceptance. A test deployment never closes these gates.
