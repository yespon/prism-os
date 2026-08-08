# Security Policy

PrismOS is alpha software. It includes tenant, RBAC, audit, and sandbox
controls, but it is not a security certification or a complete enterprise
policy engine. Treat deployments and generated artifacts as sensitive until
your team reviews the whole execution path.

## Reporting a vulnerability

Report suspected vulnerabilities privately through GitHub Security Advisories:

<https://github.com/yespon/prism-os/security/advisories/new>

If the private advisory flow is unavailable, contact the project maintainers
through the private channel associated with the repository. Do not open a
public issue for an undisclosed vulnerability.

Include, where possible:

- affected version, commit, or deployment mode;
- concise description and impact assessment;
- reproducible steps or a minimal proof of concept;
- logs, traces, or screenshots with secrets and personal data removed; and
- a suggested mitigation, if available.

Do not access data that is not yours, degrade service availability, or publish
exploit details before maintainers have had a reasonable opportunity to respond.
We will acknowledge reports as soon as practical, assess severity, coordinate a
fix or mitigation, and credit responsible disclosure when permitted.

## Supported versions

| Version | Support expectation |
| --- | --- |
| `main` | Development baseline; best-effort security fixes |
| `v0.1.0-alpha.1` | Alpha pre-release; best-effort fixes and upgrade guidance |
| Older snapshots | Not supported; upgrade to current release or main |

The support table will be tightened after alpha. A pre-release is not a promise
of backward compatibility or a production SLA.

## Security baseline and limitations

The current implementation includes:

- tenant-aware resource scopes and protected management routes;
- platform and tenant RBAC roles;
- database-backed model and integration configuration;
- audit views for supported administrative operations;
- local, Docker, and Kubernetes sandbox adapters; and
- user/tenant management with status controls.

It does not yet provide a complete centrally enforced policy engine, end-to-end
Task/Run or Workflow lifecycle, evaluation framework, connector federation, or
independent Agent runtime. These are roadmap items.

In particular:

- The default local filesystem sandbox executes on the host and is not a
  production isolation boundary.
- Docker-socket modes can grant substantial host control. Use dedicated hosts,
  least privilege, reviewed images, and restrictive network policy.
- Kubernetes provisioner mode requires operator-managed RBAC, namespace policy,
  quotas, image provenance, network policy, and kubeconfig protection.
- MCP servers and model providers are external code/data boundaries. Review
  commands, URLs, tokens, scopes, and tenant assignments before enabling them.
- Never place API keys, passwords, or personal data in `config.yaml`, `.env`,
  logs, issue reports, or source control.

AI operations is only a validation scenario. Security review must cover the
PrismOS core and every enabled plugin or connector independently; it must not
assume an operations workflow closes the governance loop.
