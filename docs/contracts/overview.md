### TheFatRat Headless Services — Functional Overview

This document enumerates the functional capabilities that will be exposed as headless services and driven from a Telegram control panel. Each capability maps to one or more concrete tasks with clear inputs and outputs (see per-capability contracts).

Capabilities
- Windows FUD Payload Generation
  - Purpose: Generate Windows executables with embedded payloads using C and/or PowerShell with encoder chains and optional UPX compression.
- PDF Embedded EXE Generation
  - Purpose: Produce a PDF file embedding a custom EXE payload using Metasploit fileformat modules.
- Android APK Backdooring
  - Purpose: Inject Metasploit payloads into existing APKs, optionally obfuscating strings, merging permissions, signing and zipaligning.
- Office/OpenOffice Document Payloads
  - Purpose: Generate malicious macro-based documents for Microsoft Word (Windows/macOS) and OpenOffice/LibreOffice (Windows/Linux/macOS) using Metasploit.
- Debian Package (.deb) Backdooring (trodebi)
  - Purpose: Embed payloads into Debian packages to produce trojanized .deb artifacts.
- Listener Generation and Session Handling
  - Purpose: Produce rc files for exploit/multi/handler and optionally launch handlers headless via msfconsole -x.
- Post-Exploitation Script Packs
  - Purpose: Execute pre-made post-exploitation resource scripts (rc) for sysinfo, migration, credential dump, gathering, etc.
- Autorun Bundle Preparation
  - Purpose: Provide ready-to-use Autorun files (USB/CD) as packaged artifacts.

Headless Orchestration Principles
- No Xterm usage. All flows are non-interactive using command flags and pre-written configuration files.
- All tasks write to task-scoped folders (input/temp/output/logs) and never to global paths outside of ~/.msf4/local and the workspace, unless explicitly configured.
- Every task emits: machine-readable status JSON, human-readable log, and zero or more output artifacts.

Please see the detailed contracts for each capability in sibling documents.