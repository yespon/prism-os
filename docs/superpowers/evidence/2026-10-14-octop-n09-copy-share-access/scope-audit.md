# Copy/share configuration access audit

Existing branch: `codex/octop-integration`, base `38073b1`. No new authority tables, no N08 execution/version subsystem, no push/deploy.

| Entry | Current authority / behavior | Verification boundary |
| --- | --- | --- |
| Agent discovery | Current Tenant + membership role; foreign private labels remain discoverable, configuration and revision redacted | Actual HTTP + SQLite / PostgreSQL |
| Agent get/create/update/delete/name check | Current DB role, original owner/shared scope; reference transaction before membership lock on writes | Existing CRUD and reference transaction regressions |
| Copy | Concrete source ID + content revision, current source owner/tenant, explicit target scope and original resource resolver | Source change, foreign owner/tenant, stale ID, withdrawal, duplicate target, personal-to-shared refusal and explicit tenant replacement |
| Copy provenance | Original Agent metadata records source ID/revision/tenant; never copies grants or creates N08 facts | Stored row and effective original prompt |
| Source confirmation/runtime | Original admin/owner/tenant_admin aliases; current membership required to renew and use diagnosis source grant | Original diagnosis authorization regression |
| Owned profile | Current membership before/after read; original held-file no-follow read/mutation | HTTP positive write/read, symlink denial, no host write after denial, member withdrawal |
| UI draft / response | Existing tenant/member draft identity, concrete source revision and target resources; redacted labels cannot be copied/executed as owned configurations | Component and API tests; final production build |
| Unknown copy response | No automatic retry; target must be inspected before a new confirmation | HTTP 5xx and network loss require inspection; submitted target name pinned; stale identity 404 cannot start a source read. Both red regressions and accepted tests retained |

Actual model, external tool, countable ticket endpoint, real remote SSH/Kubernetes/Apple execution, remote CI are not covered by these local checks. M1 has not exited. The original N01–N15, O01–O42/F01–F12 and all original PrismOS gates remain.

The execution host changed to Windows/WSL on resumption; the Git worktree and uncommitted evidence survived, old `/tmp` logs did not. Only retained raw evidence is eligible for historical reuse. The current run archives logs directly here. Full backend is newly run because application inputs changed. Full frontend pre-final-delta results must be combined with explicit delta coverage or replaced after relevant fixes; an in-flight build is not proof for later changed inputs.
