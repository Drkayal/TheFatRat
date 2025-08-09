# Privacy and Access Policy (Lab-Only)

Scope
- This system is intended exclusively for authorized lab/testing use. It must never be exposed to the public internet nor used against targets without explicit consent.

Access Control
- Telegram bot must restrict interactions to an allowlist of chat IDs (owners only).
- Internal API (orchestrator) must bind to loopback only and be unreachable from external networks.
- Run-time secrets (bot token, keystore passwords) must be injected via environment variables or secret stores; never committed to repo.

Data Handling
- Task inputs and outputs (artifacts, logs) remain within the task-scoped folders.
- Artifacts are retained only for the configured retention window, then purged.
- No telemetry is sent to third parties; optional notifications are limited to Telegram messages to the owners.

Operational Safety
- Handlers/listeners must be executed only in isolated lab networks.
- Produced binaries/documents must not be executed on the orchestrator host.
- Containers/users run without elevated privileges; network egress is restricted where possible.

Auditing
- Record task metadata (who, when, what parameters) in a central audit log.
- Retain audit logs per retention policy to support incident review.