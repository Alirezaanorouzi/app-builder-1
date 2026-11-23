# Vercel Sandbox verification checklist

Complete against the **pinned** Python `vercel` package before production.

- [ ] **Session extend:** find method name (`extend_timeout`, `extend_execution_time_limit`, or JS `extendTimeout` equivalent).
- [ ] **Snapshot retention:** create with `count=1, delete_evicted=True`; `update(snapshot_retention=…)` on existing sandbox.
- [ ] **Lifecycle hooks:** `onCreate` / `onResume` in Python SDK, if present.
- [ ] **Preview hosts:** record real hostname; update `templates/vite-react/vite.config.js` `allowedHosts`.
- [ ] **Plan limits:** Hobby ~45m session max vs Pro; align `MAX_ITERATIONS` and extend calls.
- [ ] **Isolation:** `run_command` cannot escape VM; note outbound network for `npm`.
- [ ] **Auto-resume:** `runCommand` / `writeFiles` resume stopped persistent sandboxes; reconcile (post-MVP) must not use them.

## Post-MVP

- [ ] Orphan reconcile — list/metadata only, env-prefixed names `{DEPLOY_ENV}:{uuid}`.