# Repository Guidelines

## Git Check-in & Sync Policy
Whenever asked to check in, commit, or save code changes in this repository:
1. **Stage & Commit:** Verify staged files (`git status -s`) to ensure no secrets, `.env`, `.venv`, or build artifacts are included, then commit with a clear message.
2. **Sync (`pull --rebase`):** If `origin/main` already exists on the remote (`git ls-remote --heads origin main`), run `git pull --rebase origin main` before pushing so history stays linear and up to date.
3. **Push & Verify:** Immediately push to the remote (`git push -u origin main`) and verify `git status -sb` shows `## main...origin/main` with no ahead/unpushed commits before finishing the turn.
4. **Fail Fast in Non-Interactive Shells:** Always set `$env:GIT_TERMINAL_PROMPT = "0"` and `$env:GCM_INTERACTIVE = "never"` when running `git pull` / `git push` from automated commands so missing GitHub credentials fail immediately with a clear error instead of hanging in the background.
