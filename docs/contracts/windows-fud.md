# Contract — Windows FUD Payload Generation

Purpose
- Generate Windows executable artifacts (32/64-bit) with embedded Metasploit payloads using C and/or PowerShell, optional encoder chains, and UPX compression.

Inputs
- payload: enum (e.g., windows/meterpreter/reverse_tcp, windows/meterpreter/reverse_http, windows/meterpreter/reverse_https)
- lhost: IPv4/hostname
- lport: 1..65535
- arch: enum (x86, x64)
- encoder_chain: ordered list of encoders with iteration counts (e.g., [ { name: "x86/shikata_ga_nai", iterations: 10 }, { name: "x86/countdown", iterations: 8 } ])
- template: enum (c_psh, apache_psh, msf_stager, c_only)
- upx: boolean (compress output with upx)
- output_name: string (base name without extension)

Outputs
- artifacts:
  - output/<output_name>.exe (primary)
  - logs/build.log (full command traces)
  - status.json (final status and metadata)

Process (Headless)
1) Prepare task folder (input/temp/output/logs).
2) Build msfvenom command pipeline using encoder_chain, payload, lhost, lport, arch.
3) If template requires PowerShell, generate powershell_attack.txt (or equivalent string) and integrate with C template.
4) Compile using mingw (i686-w64-mingw32-gcc or x86_64-w64-mingw32-gcc) with appropriate flags.
5) Optionally run upx on the produced EXE.
6) Emit status.json including sha256 checksum, size, timings.

Preconditions
- mingw (version 4.9.1 or 6.3.0 supported)
- msfvenom available and functional
- upx available if upx=true

Failure Cases
- Missing toolchain (mingw/upx/msfvenom)
- Invalid payload or encoder names
- Compiler errors
- Permission denied on output folder

Security Notes
- Artifacts must remain within the task-scoped output folder.
- No execution of produced binaries on the orchestrator host.