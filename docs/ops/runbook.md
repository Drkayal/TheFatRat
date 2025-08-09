# Operations Runbook

## Services
- Orchestrator API
  - Host: 127.0.0.1:8000
  - Endpoints:
    - GET /health: healthcheck (expects {status: ok})
    - GET /version: version
    - POST /tasks: create task (payload|listener|android|winexe|pdf|office|deb|autorun|postex)
    - GET /tasks/{id}: task status
    - GET /tasks/{id}/artifacts: list artifacts
    - POST /tasks/{id}/cancel: cancel task

- Telegram Bot
  - Arabic UI with inline keyboards
  - Commands: /start, /menu, /cancel <id>, /ping
  - Owner restriction via TELEGRAM_OWNER_ID

## Environment Variables
- Orchestrator
  - ORCH_USE_DOCKER: true|false (default true)
  - ORCH_DOCKER_IMAGE: container with tools (default orchestrator-tools:latest)
  - ORCH_CPUS: e.g. 1
  - ORCH_MEMORY: e.g. 1g

- Telegram Bot
  - TELEGRAM_BOT_TOKEN: bot token
  - TELEGRAM_OWNER_ID: owner telegram id (0 to disable restriction)
  - ORCH_URL: e.g. http://127.0.0.1:8000

## File System Layout
- tasks/YYYYMMDD/<task_id>/{input,temp,output,logs}
- logs/audit.jsonl: append-only audit log (JSON lines)

## Retention Policy
- Tasks
  - Default: retain 7 days of tasks; older will be archived or purged
  - Archive: zip task folder to archives/YYYYMM/<task_id>.zip (optional)

- Logs
  - audit.jsonl is rotated weekly or at 100 MB, whichever comes first

- Implement with a daily cron invoking /workspace/orchestrator/scripts/cleanup.sh

## Cleanup Script (suggested)
- Remove tasks older than RETAIN_DAYS (default 7)
- Rotate logs/audit.jsonl
- Optional: zip tasks before removal

## Security Posture
- Lab-only use; do not expose API publicly
- Docker isolation per task (mount-restricted, none network by default)
- Owner-locked Telegram access
- Secrets supplied via environment only
- No persistence outside task scopes and ~/.msf4/local (isolated HOME)

## Telegram Usage (Arabic)
- /start → اختر النوع (بايلود، مستمع، Android، PDF، Office، deb، Autorun، ما بعد الاستغلال)
- يتبع كل خيار شرح قصير وصيغة الإدخال
- البوت ينشئ المهمة، يبث الحالة بالعربية، ويرسل الملف الناتج

## Troubleshooting
- API not responding: check /health and server.log
- msfconsole artifacts missing: verify task HOME mount (temp/home) and _copy_msf_local
- Docker: ensure ORCH_DOCKER_IMAGE has all toolchains and docker daemon is running
- Bot not responding: verify token with getMe, deleteWebhook, check bot.log and network egress