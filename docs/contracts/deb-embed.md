# Contract — Debian Package Backdooring (trodebi)

Purpose
- Embed payloads into Debian packages to produce trojanized .deb artifacts.

Inputs
- deb_path: path to original .deb
- payload: enum (linux/x86/meterpreter/reverse_tcp, linux/x64/*, generic/* as supported)
- lhost: IPv4/hostname
- lport: 1..65535
- output_name: string (base name without extension)

Outputs
- artifacts:
  - output/<output_name>.deb
  - logs/build.log
  - status.json

Process (Headless)
1) Validate deb_path and unpack .deb to temp.
2) Inject payload into maintainer scripts or binary as per method.
3) Repack .deb and verify control integrity.
4) Emit status with checksums and sizes.

Preconditions
- dpkg-deb available
- msfvenom for payload generation

Failure Cases
- Invalid .deb structure
- Control file integrity issues
- Injection failure

Security Notes
- Only for lab/testing use on isolated environments.