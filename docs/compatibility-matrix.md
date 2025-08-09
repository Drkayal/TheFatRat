# Compatibility and Versions Matrix

Core Tooling (Target Versions)
- msfconsole/msfvenom: >= 4.14 (as referenced by original scripts); pin to a tested release in container
- mingw-w64 toolchain: 4.9.1 or 6.3.0
- upx: latest stable compatible with produced EXEs
- apktool: version matching backdoor_apk requirements
- baksmali/smali: per original tools bundle
- Android SDK tools: zipalign/apksigner provided in repo/tools
- keytool/jarsigner: from default-jdk/default-jre
- dpkg-deb: system-provided
- ruby/gem (nokogiri): per chk_tools
- python2/python3/pip3: per chk_tools

Operating Systems (tested)
- Linux (Kali/Parrot/BlackArch/Ubuntu variants) — headless

Environment Check Reference
- See docs/environment-check.txt for actual host scan output produced by chk_tools.

Notes
- For reliability, all runners should execute inside dedicated containers that bake the exact versions above.
- Where repository bundles a tool (e.g., tools/android-sdk/zipalign), default to bundled version to reduce drift.