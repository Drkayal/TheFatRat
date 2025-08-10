import os
import re
import xml.etree.ElementTree as ET
import zipfile
import struct
import hashlib
import binascii
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass
from datetime import datetime
import subprocess
import tempfile
import json

@dataclass
class ManifestInfo:
    package_name: str
    version_code: str
    version_name: str
    min_sdk_version: int
    target_sdk_version: int
    compile_sdk_version: Optional[int]
    permissions: List[str]
    activities: List[Dict[str, Any]]
    services: List[Dict[str, Any]]
    receivers: List[Dict[str, Any]]
    providers: List[Dict[str, Any]]
    application_info: Dict[str, Any]
    uses_features: List[str]
    intents: List[Dict[str, Any]]

@dataclass
class CodeStructure:
    dex_files: List[str]
    class_count: int
    method_count: int
    string_count: int
    native_libraries: List[str]
    architectures: List[str]
    obfuscation_indicators: Dict[str, Any]
    encryption_indicators: Dict[str, Any]
    reflection_usage: List[str]
    dynamic_loading: List[str]

@dataclass
class SecurityAnalysis:
    anti_debug_techniques: List[str]
    anti_emulator_techniques: List[str]
    root_detection: List[str]
    code_obfuscation: Dict[str, Any]
    encryption_methods: List[str]
    suspicious_permissions: List[str]
    network_security: Dict[str, Any]
    certificate_info: Dict[str, Any]

class AndroidManifestParser:
    """Advanced Android Manifest XML parser with binary support"""
    
    # Android resource constants
    ANDROID_NS = "http://schemas.android.com/apk/res/android"
    
    # Permission categories
    DANGEROUS_PERMISSIONS = {
        'android.permission.READ_CALENDAR',
        'android.permission.WRITE_CALENDAR',
        'android.permission.CAMERA',
        'android.permission.READ_CONTACTS',
        'android.permission.WRITE_CONTACTS',
        'android.permission.GET_ACCOUNTS',
        'android.permission.ACCESS_FINE_LOCATION',
        'android.permission.ACCESS_COARSE_LOCATION',
        'android.permission.RECORD_AUDIO',
        'android.permission.READ_PHONE_STATE',
        'android.permission.READ_PHONE_NUMBERS',
        'android.permission.CALL_PHONE',
        'android.permission.ANSWER_PHONE_CALLS',
        'android.permission.READ_CALL_LOG',
        'android.permission.WRITE_CALL_LOG',
        'android.permission.ADD_VOICEMAIL',
        'android.permission.USE_SIP',
        'android.permission.PROCESS_OUTGOING_CALLS',
        'android.permission.BODY_SENSORS',
        'android.permission.SEND_SMS',
        'android.permission.RECEIVE_SMS',
        'android.permission.READ_SMS',
        'android.permission.RECEIVE_WAP_PUSH',
        'android.permission.RECEIVE_MMS',
        'android.permission.READ_EXTERNAL_STORAGE',
        'android.permission.WRITE_EXTERNAL_STORAGE',
    }
    
    MALICIOUS_PERMISSIONS = {
        'android.permission.SYSTEM_ALERT_WINDOW',
        'android.permission.DEVICE_ADMIN',
        'android.permission.BIND_DEVICE_ADMIN',
        'android.permission.ACCESSIBILITY_SERVICE',
        'android.permission.BIND_ACCESSIBILITY_SERVICE',
        'android.permission.WRITE_SECURE_SETTINGS',
        'android.permission.INSTALL_PACKAGES',
        'android.permission.DELETE_PACKAGES',
        'android.permission.MODIFY_PHONE_STATE',
        'android.permission.MOUNT_UNMOUNT_FILESYSTEMS',
        'android.permission.WRITE_SETTINGS',
    }
    
    @staticmethod
    def parse_binary_manifest(manifest_data: bytes) -> Dict[str, Any]:
        """Parse binary AndroidManifest.xml using advanced techniques"""
        result = {
            "parsed": False,
            "package_name": None,
            "version_code": None,
            "version_name": None,
            "min_sdk": None,
            "target_sdk": None,
            "permissions": [],
            "activities": [],
            "services": [],
            "receivers": [],
            "providers": [],
            "application": {},
            "uses_features": [],
            "intents": []
        }
        
        try:
            # Try using aapt dump first
            temp_file = tempfile.NamedTemporaryFile(suffix='.xml', delete=False)
            temp_file.write(manifest_data)
            temp_file.close()
            
            # Use aapt to dump manifest
            aapt_path = "/workspace/tools/android-sdk/build-tools/latest/aapt"
            if os.path.exists(aapt_path):
                try:
                    output = subprocess.check_output([
                        aapt_path, "dump", "xmltree", temp_file.name
                    ], text=True, timeout=30)
                    
                    result.update(AndroidManifestParser._parse_aapt_output(output))
                    result["parsed"] = True
                except subprocess.SubprocessError:
                    pass
            
            # Fallback to manual binary parsing
            if not result["parsed"]:
                result.update(AndroidManifestParser._parse_binary_xml(manifest_data))
            
            os.unlink(temp_file.name)
            
        except Exception as e:
            result["error"] = str(e)
        
        return result
    
    @staticmethod
    def _parse_aapt_output(output: str) -> Dict[str, Any]:
        """Parse aapt dump output"""
        result = {}
        
        # Extract package information
        package_match = re.search(r'package="([^"]+)"', output)
        if package_match:
            result["package_name"] = package_match.group(1)
        
        version_code_match = re.search(r'versionCode="([^"]+)"', output)
        if version_code_match:
            result["version_code"] = version_code_match.group(1)
        
        version_name_match = re.search(r'versionName="([^"]+)"', output)
        if version_name_match:
            result["version_name"] = version_name_match.group(1)
        
        # Extract SDK versions
        min_sdk_match = re.search(r'minSdkVersion="([^"]+)"', output)
        if min_sdk_match:
            result["min_sdk"] = int(min_sdk_match.group(1))
        
        target_sdk_match = re.search(r'targetSdkVersion="([^"]+)"', output)
        if target_sdk_match:
            result["target_sdk"] = int(target_sdk_match.group(1))
        
        # Extract permissions
        permissions = re.findall(r'uses-permission.*name="([^"]+)"', output)
        result["permissions"] = list(set(permissions))
        
        # Extract activities
        activities = []
        activity_blocks = re.findall(r'E: activity[^E]*?(?=E:|$)', output, re.DOTALL)
        for block in activity_blocks:
            name_match = re.search(r'name="([^"]+)"', block)
            if name_match:
                activity = {"name": name_match.group(1)}
                
                # Check for exported
                exported_match = re.search(r'exported="([^"]+)"', block)
                if exported_match:
                    activity["exported"] = exported_match.group(1) == "true"
                
                # Check for main activity
                if "android.intent.action.MAIN" in block:
                    activity["main"] = True
                
                activities.append(activity)
        
        result["activities"] = activities
        
        # Extract services
        services = []
        service_blocks = re.findall(r'E: service[^E]*?(?=E:|$)', output, re.DOTALL)
        for block in service_blocks:
            name_match = re.search(r'name="([^"]+)"', block)
            if name_match:
                service = {"name": name_match.group(1)}
                
                exported_match = re.search(r'exported="([^"]+)"', block)
                if exported_match:
                    service["exported"] = exported_match.group(1) == "true"
                
                services.append(service)
        
        result["services"] = services
        
        # Extract receivers
        receivers = []
        receiver_blocks = re.findall(r'E: receiver[^E]*?(?=E:|$)', output, re.DOTALL)
        for block in receiver_blocks:
            name_match = re.search(r'name="([^"]+)"', block)
            if name_match:
                receiver = {"name": name_match.group(1)}
                
                exported_match = re.search(r'exported="([^"]+)"', block)
                if exported_match:
                    receiver["exported"] = exported_match.group(1) == "true"
                
                # Check for boot receiver
                if "android.intent.action.BOOT_COMPLETED" in block:
                    receiver["boot_receiver"] = True
                
                receivers.append(receiver)
        
        result["receivers"] = receivers
        
        return result
    
    @staticmethod
    def _parse_binary_xml(data: bytes) -> Dict[str, Any]:
        """Manual binary XML parsing for AndroidManifest.xml"""
        result = {}
        
        try:
            # Basic binary XML header parsing
            if len(data) < 8:
                return result
            
            # Check magic number
            magic = struct.unpack('<I', data[0:4])[0]
            if magic != 0x00080003:  # Binary XML magic
                return result
            
            file_size = struct.unpack('<I', data[4:8])[0]
            
            # This is a simplified parser - in real implementation,
            # you would need to parse the string pool and resource tables
            result["binary_parsed"] = True
            
        except Exception:
            pass
        
        return result

class PermissionAnalyzer:
    """Advanced permission analysis with risk assessment"""
    
    @staticmethod
    def analyze_permissions(permissions: List[str]) -> Dict[str, Any]:
        """Comprehensive permission analysis"""
        analysis = {
            "total_permissions": len(permissions),
            "dangerous_permissions": [],
            "malicious_permissions": [],
            "risk_score": 0,
            "risk_level": "LOW",
            "permission_categories": {},
            "unusual_combinations": [],
            "privilege_escalation_risk": False
        }
        
        # Categorize permissions
        categories = {
            "network": [],
            "storage": [],
            "location": [],
            "camera": [],
            "microphone": [],
            "contacts": [],
            "sms": [],
            "phone": [],
            "device_admin": [],
            "accessibility": [],
            "system": []
        }
        
        for perm in permissions:
            # Check dangerous permissions
            if perm in AndroidManifestParser.DANGEROUS_PERMISSIONS:
                analysis["dangerous_permissions"].append(perm)
                analysis["risk_score"] += 3
            
            # Check malicious permissions
            if perm in AndroidManifestParser.MALICIOUS_PERMISSIONS:
                analysis["malicious_permissions"].append(perm)
                analysis["risk_score"] += 5
            
            # Categorize permissions
            if "INTERNET" in perm or "NETWORK" in perm:
                categories["network"].append(perm)
            elif "STORAGE" in perm or "EXTERNAL" in perm:
                categories["storage"].append(perm)
            elif "LOCATION" in perm:
                categories["location"].append(perm)
            elif "CAMERA" in perm:
                categories["camera"].append(perm)
            elif "RECORD_AUDIO" in perm or "MICROPHONE" in perm:
                categories["microphone"].append(perm)
            elif "CONTACTS" in perm:
                categories["contacts"].append(perm)
            elif "SMS" in perm or "MMS" in perm:
                categories["sms"].append(perm)
            elif "PHONE" in perm or "CALL" in perm:
                categories["phone"].append(perm)
            elif "DEVICE_ADMIN" in perm or "ADMIN" in perm:
                categories["device_admin"].append(perm)
            elif "ACCESSIBILITY" in perm:
                categories["accessibility"].append(perm)
            elif "SYSTEM" in perm or "WRITE_SECURE_SETTINGS" in perm:
                categories["system"].append(perm)
        
        analysis["permission_categories"] = {k: v for k, v in categories.items() if v}
        
        # Check for unusual permission combinations
        if categories["device_admin"] and categories["network"]:
            analysis["unusual_combinations"].append("Device Admin + Network Access")
            analysis["risk_score"] += 10
        
        if categories["accessibility"] and categories["system"]:
            analysis["unusual_combinations"].append("Accessibility + System Permissions")
            analysis["risk_score"] += 8
        
        if len(categories["sms"]) > 0 and categories["network"]:
            analysis["unusual_combinations"].append("SMS Access + Network")
            analysis["risk_score"] += 6
        
        # Check privilege escalation risk
        if any(perm in AndroidManifestParser.MALICIOUS_PERMISSIONS for perm in permissions):
            analysis["privilege_escalation_risk"] = True
        
        # Determine risk level
        if analysis["risk_score"] >= 20:
            analysis["risk_level"] = "CRITICAL"
        elif analysis["risk_score"] >= 15:
            analysis["risk_level"] = "HIGH"
        elif analysis["risk_score"] >= 10:
            analysis["risk_level"] = "MEDIUM"
        elif analysis["risk_score"] >= 5:
            analysis["risk_level"] = "LOW"
        else:
            analysis["risk_level"] = "MINIMAL"
        
        return analysis

class CodeStructureScanner:
    """Advanced code structure analysis and DEX scanning"""
    
    @staticmethod
    def scan_dex_files(apk_path: Path) -> Dict[str, Any]:
        """Comprehensive DEX file analysis"""
        analysis = {
            "dex_files": [],
            "total_classes": 0,
            "total_methods": 0,
            "total_strings": 0,
            "obfuscation_score": 0,
            "encryption_indicators": [],
            "reflection_usage": [],
            "dynamic_loading": [],
            "native_methods": [],
            "suspicious_patterns": []
        }
        
        try:
            with zipfile.ZipFile(apk_path, 'r') as apk:
                # Find all DEX files
                dex_files = [f for f in apk.namelist() if f.endswith('.dex')]
                analysis["dex_files"] = dex_files
                
                for dex_file in dex_files:
                    dex_data = apk.read(dex_file)
                    dex_analysis = CodeStructureScanner._analyze_dex_content(dex_data)
                    
                    analysis["total_classes"] += dex_analysis.get("class_count", 0)
                    analysis["total_methods"] += dex_analysis.get("method_count", 0)
                    analysis["total_strings"] += dex_analysis.get("string_count", 0)
                    
                    # Merge analysis results
                    analysis["encryption_indicators"].extend(dex_analysis.get("encryption_indicators", []))
                    analysis["reflection_usage"].extend(dex_analysis.get("reflection_usage", []))
                    analysis["dynamic_loading"].extend(dex_analysis.get("dynamic_loading", []))
                    analysis["native_methods"].extend(dex_analysis.get("native_methods", []))
                    analysis["suspicious_patterns"].extend(dex_analysis.get("suspicious_patterns", []))
                
                # Calculate obfuscation score
                analysis["obfuscation_score"] = CodeStructureScanner._calculate_obfuscation_score(analysis)
                
        except Exception as e:
            analysis["error"] = str(e)
        
        return analysis
    
    @staticmethod
    def _analyze_dex_content(dex_data: bytes) -> Dict[str, Any]:
        """Analyze DEX file content"""
        analysis = {
            "class_count": 0,
            "method_count": 0,
            "string_count": 0,
            "encryption_indicators": [],
            "reflection_usage": [],
            "dynamic_loading": [],
            "native_methods": [],
            "suspicious_patterns": []
        }
        
        try:
            # DEX file header parsing
            if len(dex_data) < 112:  # Minimum DEX header size
                return analysis
            
            # Check DEX magic
            magic = dex_data[0:8]
            if not magic.startswith(b'dex\n'):
                return analysis
            
            # Parse header
            header = struct.unpack('<8I8I16I', dex_data[8:112])
            
            # Extract counts from header
            string_ids_size = header[0]
            type_ids_size = header[1]
            proto_ids_size = header[2]
            field_ids_size = header[3]
            method_ids_size = header[4]
            class_defs_size = header[5]
            
            analysis["string_count"] = string_ids_size
            analysis["method_count"] = method_ids_size
            analysis["class_count"] = class_defs_size
            
            # Analyze strings for suspicious patterns
            analysis.update(CodeStructureScanner._analyze_dex_strings(dex_data, header))
            
        except Exception as e:
            analysis["parse_error"] = str(e)
        
        return analysis
    
    @staticmethod
    def _analyze_dex_strings(dex_data: bytes, header: tuple) -> Dict[str, Any]:
        """Analyze strings in DEX file for suspicious patterns"""
        result = {
            "encryption_indicators": [],
            "reflection_usage": [],
            "dynamic_loading": [],
            "native_methods": [],
            "suspicious_patterns": []
        }
        
        try:
            # Extract string pool (simplified)
            string_ids_off = header[8]  # string_ids_off
            string_ids_size = header[0]  # string_ids_size
            
            # Suspicious patterns to look for
            encryption_patterns = [
                b'AES', b'DES', b'RSA', b'encrypt', b'decrypt', b'cipher',
                b'javax.crypto', b'Cipher.getInstance', b'SecretKey'
            ]
            
            reflection_patterns = [
                b'Class.forName', b'getDeclaredMethod', b'getMethod',
                b'invoke', b'newInstance', b'getDeclaredField'
            ]
            
            dynamic_loading_patterns = [
                b'DexClassLoader', b'PathClassLoader', b'loadClass',
                b'defineClass', b'findClass'
            ]
            
            native_patterns = [
                b'System.loadLibrary', b'System.load', b'native'
            ]
            
            suspicious_patterns = [
                b'su', b'root', b'/system/bin', b'/system/xbin',
                b'android.permission.', b'getDeviceId', b'getSubscriberId',
                b'TelephonyManager', b'getSimSerialNumber'
            ]
            
            # Search for patterns in raw data (simplified approach)
            for pattern in encryption_patterns:
                if pattern in dex_data:
                    result["encryption_indicators"].append(pattern.decode('utf-8', errors='ignore'))
            
            for pattern in reflection_patterns:
                if pattern in dex_data:
                    result["reflection_usage"].append(pattern.decode('utf-8', errors='ignore'))
            
            for pattern in dynamic_loading_patterns:
                if pattern in dex_data:
                    result["dynamic_loading"].append(pattern.decode('utf-8', errors='ignore'))
            
            for pattern in native_patterns:
                if pattern in dex_data:
                    result["native_methods"].append(pattern.decode('utf-8', errors='ignore'))
            
            for pattern in suspicious_patterns:
                if pattern in dex_data:
                    result["suspicious_patterns"].append(pattern.decode('utf-8', errors='ignore'))
                    
        except Exception as e:
            result["string_analysis_error"] = str(e)
        
        return result
    
    @staticmethod
    def _calculate_obfuscation_score(analysis: Dict[str, Any]) -> int:
        """Calculate obfuscation score based on various indicators"""
        score = 0
        
        # High class to method ratio might indicate obfuscation
        if analysis["total_classes"] > 0:
            methods_per_class = analysis["total_methods"] / analysis["total_classes"]
            if methods_per_class < 2:  # Very few methods per class
                score += 20
            elif methods_per_class < 5:
                score += 10
        
        # High number of classes might indicate obfuscation
        if analysis["total_classes"] > 1000:
            score += 15
        elif analysis["total_classes"] > 500:
            score += 10
        
        # Reflection usage indicates potential obfuscation
        if analysis["reflection_usage"]:
            score += len(analysis["reflection_usage"]) * 5
        
        # Dynamic loading is suspicious
        if analysis["dynamic_loading"]:
            score += len(analysis["dynamic_loading"]) * 10
        
        # Native methods can be used for obfuscation
        if analysis["native_methods"]:
            score += len(analysis["native_methods"]) * 3
        
        return min(score, 100)  # Cap at 100

class AntiAnalysisDetector:
    """Advanced anti-analysis technique detection"""
    
    @staticmethod
    def detect_protection_mechanisms(apk_path: Path) -> Dict[str, Any]:
        """Detect various anti-analysis and protection mechanisms"""
        detection_result = {
            "anti_debug": [],
            "anti_emulator": [],
            "root_detection": [],
            "integrity_checks": [],
            "obfuscation_techniques": [],
            "packing_indicators": [],
            "overall_protection_score": 0
        }
        
        try:
            with zipfile.ZipFile(apk_path, 'r') as apk:
                # Analyze DEX files for anti-analysis techniques
                dex_files = [f for f in apk.namelist() if f.endswith('.dex')]
                
                for dex_file in dex_files:
                    dex_data = apk.read(dex_file)
                    dex_analysis = AntiAnalysisDetector._analyze_dex_protection(dex_data)
                    
                    # Merge results
                    for key in detection_result:
                        if key != "overall_protection_score" and key in dex_analysis:
                            detection_result[key].extend(dex_analysis[key])
                
                # Analyze native libraries
                native_analysis = AntiAnalysisDetector._analyze_native_protection(apk)
                for key in detection_result:
                    if key != "overall_protection_score" and key in native_analysis:
                        detection_result[key].extend(native_analysis[key])
                
                # Calculate overall protection score
                detection_result["overall_protection_score"] = AntiAnalysisDetector._calculate_protection_score(detection_result)
                
        except Exception as e:
            detection_result["analysis_error"] = str(e)
        
        return detection_result
    
    @staticmethod
    def _analyze_dex_protection(dex_data: bytes) -> Dict[str, Any]:
        """Analyze DEX file for protection mechanisms"""
        result = {
            "anti_debug": [],
            "anti_emulator": [],
            "root_detection": [],
            "integrity_checks": [],
            "obfuscation_techniques": []
        }
        
        # Anti-debug patterns
        anti_debug_patterns = [
            b'isDebuggerConnected', b'Debug.isDebuggerConnected',
            b'android.os.Debug', b'PTRACE', b'ptrace',
            b'/proc/self/status', b'TracerPid'
        ]
        
        # Anti-emulator patterns
        anti_emulator_patterns = [
            b'goldfish', b'sdk_gphone', b'generic', b'emulator',
            b'vbox', b'virtualbox', b'qemu', b'bluestacks',
            b'build.prop', b'ro.kernel.qemu', b'ro.hardware'
        ]
        
        # Root detection patterns
        root_detection_patterns = [
            b'/system/app/Superuser.apk', b'/system/xbin/su',
            b'/system/bin/su', b'/sbin/su', b'busybox',
            b'Superuser', b'SuperSU', b'Magisk'
        ]
        
        # Integrity check patterns
        integrity_patterns = [
            b'PackageManager', b'getInstallerPackageName',
            b'checkSignatures', b'GET_SIGNATURES',
            b'MessageDigest', b'SHA', b'MD5'
        ]
        
        # Obfuscation patterns
        obfuscation_patterns = [
            b'DexClassLoader', b'reflection', b'Class.forName',
            b'invoke', b'newInstance'
        ]
        
        # Search for patterns
        for pattern in anti_debug_patterns:
            if pattern in dex_data:
                result["anti_debug"].append(pattern.decode('utf-8', errors='ignore'))
        
        for pattern in anti_emulator_patterns:
            if pattern in dex_data:
                result["anti_emulator"].append(pattern.decode('utf-8', errors='ignore'))
        
        for pattern in root_detection_patterns:
            if pattern in dex_data:
                result["root_detection"].append(pattern.decode('utf-8', errors='ignore'))
        
        for pattern in integrity_patterns:
            if pattern in dex_data:
                result["integrity_checks"].append(pattern.decode('utf-8', errors='ignore'))
        
        for pattern in obfuscation_patterns:
            if pattern in dex_data:
                result["obfuscation_techniques"].append(pattern.decode('utf-8', errors='ignore'))
        
        return result
    
    @staticmethod
    def _analyze_native_protection(apk: zipfile.ZipFile) -> Dict[str, Any]:
        """Analyze native libraries for protection mechanisms"""
        result = {
            "anti_debug": [],
            "anti_emulator": [],
            "root_detection": [],
            "packing_indicators": []
        }
        
        try:
            # Find native libraries
            native_libs = [f for f in apk.namelist() if f.startswith('lib/') and f.endswith('.so')]
            
            for lib_path in native_libs:
                lib_data = apk.read(lib_path)
                
                # Check for anti-debug in native code
                if b'ptrace' in lib_data or b'PTRACE' in lib_data:
                    result["anti_debug"].append(f"Native ptrace in {lib_path}")
                
                # Check for packing indicators
                if b'UPX' in lib_data:
                    result["packing_indicators"].append(f"UPX packing in {lib_path}")
                
                # Check ELF header for anomalies
                if len(lib_data) >= 16:
                    elf_header = lib_data[:16]
                    if elf_header[:4] != b'\x7fELF':
                        result["packing_indicators"].append(f"Invalid ELF header in {lib_path}")
                
        except Exception as e:
            result["native_analysis_error"] = str(e)
        
        return result
    
    @staticmethod
    def _calculate_protection_score(detection_result: Dict[str, Any]) -> int:
        """Calculate overall protection score"""
        score = 0
        
        # Weight different protection mechanisms
        score += len(detection_result["anti_debug"]) * 15
        score += len(detection_result["anti_emulator"]) * 10
        score += len(detection_result["root_detection"]) * 20
        score += len(detection_result["integrity_checks"]) * 10
        score += len(detection_result["obfuscation_techniques"]) * 5
        score += len(detection_result["packing_indicators"]) * 25
        
        return min(score, 100)  # Cap at 100

class APKAnalysisEngine:
    """Main APK analysis engine coordinating all analysis components"""
    
    def __init__(self, workspace_dir: Path):
        self.workspace = workspace_dir
        self.manifest_parser = AndroidManifestParser()
        self.permission_analyzer = PermissionAnalyzer()
        self.code_scanner = CodeStructureScanner()
        self.anti_analysis_detector = AntiAnalysisDetector()
    
    def comprehensive_analysis(self, apk_path: Path) -> Dict[str, Any]:
        """Perform comprehensive APK analysis"""
        analysis_result = {
            "analysis_timestamp": datetime.now().isoformat(),
            "apk_path": str(apk_path),
            "manifest_analysis": {},
            "permission_analysis": {},
            "code_structure": {},
            "security_analysis": {},
            "risk_assessment": {},
            "injection_recommendations": {}
        }
        
        try:
            # Extract and analyze manifest
            with zipfile.ZipFile(apk_path, 'r') as apk:
                if 'AndroidManifest.xml' in apk.namelist():
                    manifest_data = apk.read('AndroidManifest.xml')
                    manifest_info = self.manifest_parser.parse_binary_manifest(manifest_data)
                    analysis_result["manifest_analysis"] = manifest_info
                    
                    # Analyze permissions
                    if manifest_info.get("permissions"):
                        perm_analysis = self.permission_analyzer.analyze_permissions(manifest_info["permissions"])
                        analysis_result["permission_analysis"] = perm_analysis
            
            # Analyze code structure
            code_analysis = self.code_scanner.scan_dex_files(apk_path)
            analysis_result["code_structure"] = code_analysis
            
            # Detect anti-analysis mechanisms
            security_analysis = self.anti_analysis_detector.detect_protection_mechanisms(apk_path)
            analysis_result["security_analysis"] = security_analysis
            
            # Generate risk assessment
            analysis_result["risk_assessment"] = self._generate_risk_assessment(analysis_result)
            
            # Generate injection recommendations
            analysis_result["injection_recommendations"] = self._generate_injection_recommendations(analysis_result)
            
        except Exception as e:
            analysis_result["analysis_error"] = str(e)
        
        return analysis_result
    
    def _generate_risk_assessment(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Generate comprehensive risk assessment"""
        risk_assessment = {
            "overall_risk_score": 0,
            "risk_level": "UNKNOWN",
            "risk_factors": [],
            "security_concerns": [],
            "injection_difficulty": "UNKNOWN"
        }
        
        try:
            score = 0
            
            # Permission-based risk
            perm_analysis = analysis.get("permission_analysis", {})
            score += perm_analysis.get("risk_score", 0)
            
            if perm_analysis.get("malicious_permissions"):
                risk_assessment["risk_factors"].append("Malicious permissions detected")
            
            # Code structure risk
            code_analysis = analysis.get("code_structure", {})
            obfuscation_score = code_analysis.get("obfuscation_score", 0)
            score += obfuscation_score // 5  # Convert to risk points
            
            if obfuscation_score > 50:
                risk_assessment["risk_factors"].append("High code obfuscation")
            
            # Security mechanism risk
            security_analysis = analysis.get("security_analysis", {})
            protection_score = security_analysis.get("overall_protection_score", 0)
            score += protection_score // 4  # Convert to risk points
            
            if protection_score > 30:
                risk_assessment["risk_factors"].append("Advanced protection mechanisms")
                risk_assessment["injection_difficulty"] = "HIGH"
            elif protection_score > 10:
                risk_assessment["injection_difficulty"] = "MEDIUM"
            else:
                risk_assessment["injection_difficulty"] = "LOW"
            
            # Overall risk level
            risk_assessment["overall_risk_score"] = min(score, 100)
            
            if score >= 70:
                risk_assessment["risk_level"] = "CRITICAL"
            elif score >= 50:
                risk_assessment["risk_level"] = "HIGH"
            elif score >= 30:
                risk_assessment["risk_level"] = "MEDIUM"
            elif score >= 10:
                risk_assessment["risk_level"] = "LOW"
            else:
                risk_assessment["risk_level"] = "MINIMAL"
                
        except Exception as e:
            risk_assessment["assessment_error"] = str(e)
        
        return risk_assessment
    
    def _generate_injection_recommendations(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Generate injection strategy recommendations"""
        recommendations = {
            "recommended_injection_points": [],
            "evasion_techniques_needed": [],
            "payload_modifications": [],
            "stealth_requirements": []
        }
        
        try:
            manifest_analysis = analysis.get("manifest_analysis", {})
            security_analysis = analysis.get("security_analysis", {})
            code_analysis = analysis.get("code_structure", {})
            
            # Recommend injection points based on activities/services
            activities = manifest_analysis.get("activities", [])
            services = manifest_analysis.get("services", [])
            
            # Find main activity for injection
            main_activities = [a for a in activities if a.get("main")]
            if main_activities:
                recommendations["recommended_injection_points"].append({
                    "type": "main_activity",
                    "target": main_activities[0]["name"],
                    "priority": "high"
                })
            
            # Recommend service injection if services exist
            if services:
                recommendations["recommended_injection_points"].append({
                    "type": "background_service",
                    "target": services[0]["name"],
                    "priority": "medium"
                })
            
            # Determine needed evasion techniques
            if security_analysis.get("anti_debug"):
                recommendations["evasion_techniques_needed"].append("anti_debug_bypass")
            
            if security_analysis.get("anti_emulator"):
                recommendations["evasion_techniques_needed"].append("emulator_evasion")
            
            if security_analysis.get("root_detection"):
                recommendations["evasion_techniques_needed"].append("root_hiding")
            
            if code_analysis.get("obfuscation_score", 0) > 50:
                recommendations["evasion_techniques_needed"].append("code_deobfuscation")
            
            # Recommend payload modifications
            if "INTERNET" not in manifest_analysis.get("permissions", []):
                recommendations["payload_modifications"].append("add_internet_permission")
            
            if not any("BOOT_COMPLETED" in str(r) for r in manifest_analysis.get("receivers", [])):
                recommendations["payload_modifications"].append("add_boot_receiver")
            
            # Stealth requirements
            protection_score = security_analysis.get("overall_protection_score", 0)
            if protection_score > 50:
                recommendations["stealth_requirements"] = ["high", "advanced_obfuscation", "runtime_protection"]
            elif protection_score > 20:
                recommendations["stealth_requirements"] = ["medium", "code_obfuscation"]
            else:
                recommendations["stealth_requirements"] = ["low", "basic_hiding"]
                
        except Exception as e:
            recommendations["recommendation_error"] = str(e)
        
        return recommendations

# Export main classes
__all__ = [
    'APKAnalysisEngine', 'AndroidManifestParser', 'PermissionAnalyzer', 
    'CodeStructureScanner', 'AntiAnalysisDetector', 'ManifestInfo', 
    'CodeStructure', 'SecurityAnalysis'
]