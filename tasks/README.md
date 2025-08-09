# Tasks Folder Structure

All headless executions must operate within a task-scoped directory to prevent cross-task contamination and to simplify artifact handling.

Template
- tasks/_template/
  - input/
  - temp/
  - output/
  - logs/

Runtime Layout
- tasks/YYYYMMDD/<task_id>/
  - input/: user-provided files (e.g., APK, PDF, DEB, keystores)
  - temp/: intermediate files, safe to purge after completion
  - output/: final artifacts to be returned to the user (via Telegram)
  - logs/: build/run logs and status.json

Conventions
- status.json: machine-readable status including { state, started_at, finished_at, payload, parameters, artifacts[], checksums{} }.
- All tools must write only under this folder (and ~/.msf4/local for msf artifacts before collection).
- No tool should prompt for input; all parameters must be specified upfront.