# Contract — Android APK Backdooring

Purpose
- Inject a Metasploit payload into an existing Android APK, optionally performing string obfuscation, permission merge/shuffle, signing, and zipalign.

Inputs
- apk_path: path to original APK (input)
- payload: enum (e.g., android/meterpreter/reverse_tcp)
- lhost: IPv4/hostname
- lport: 1..65535
- method: enum (backdoor_apk_0_2_4a, fatrat_legacy, msfvenom_embed)
- perm_strategy: enum (keep_original, merge_shuffle)
- obfuscation: boolean (use android-string-obfuscator)
- signing:
  - key_store_path (optional)
  - key_alias (optional)
  - key_store_password (optional)
  - key_password (optional)
- output_name: string (base name without extension)

Outputs
- artifacts:
  - output/<output_name>.apk (rebuilt, signed, zipaligned)
  - logs/build.log (full command traces)
  - status.json (final status and metadata)

Process (Headless)
1) Validate apk_path and payload.
2) Prepare temp workspace and decode APK (apktool d).
3) Inject payload via selected method.
4) Apply obfuscation if enabled.
5) Rebuild (apktool b) to temp artifact.
6) Sign with provided keystore or debug key.
7) Zipalign final APK to output.
8) Emit status.json with checksums and sizes.

Preconditions
- apktool, baksmali/smali, zipalign, keytool/jarsigner, msfvenom available
- Android SDK components present (for zipalign/apksigner if applicable)

Failure Cases
- Invalid APK
- Missing tools (apktool/zipalign/jarsigner)
- Signing failure
- Injection failure (method-specific)

Security Notes
- Do not ship keystores inside the repo; consume from task input only.
- Artifacts remain scoped to the task folder.