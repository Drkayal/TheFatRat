import os
import subprocess
import logging
from pathlib import Path
from typing import Dict, Optional

class EnvironmentManager:
    """Manage environment variables and system dependencies"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.workspace = self._get_workspace_path()
    
    @staticmethod
    def get_lhost() -> str:
        """Get LHOST from environment or use default"""
        return os.environ.get('LHOST', '127.0.0.1')
    
    @staticmethod
    def get_lport() -> str:
        """Get LPORT from environment or use default"""
        return os.environ.get('LPORT', '4444')
    
    @staticmethod
    def _get_workspace_path() -> Path:
        """Get workspace path from environment or use default"""
        workspace = os.environ.get('WORKSPACE_PATH', '/workspace')
        return Path(workspace)
    
    def validate_environment(self) -> Dict[str, bool]:
        """Validate that all required environment variables and dependencies are available"""
        validation_results = {
            'java': self._check_java(),
            'apktool': self._check_apktool(),
            'workspace_writable': self._check_workspace_writable(),
            'tools_available': self._check_tools_availability()
        }
        
        missing_items = [k for k, v in validation_results.items() if not v]
        if missing_items:
            self.logger.warning(f"Missing dependencies: {missing_items}")
        
        return validation_results
    
    def _check_java(self) -> bool:
        """Check if Java is available"""
        try:
            result = subprocess.run(
                ['java', '-version'], 
                capture_output=True, 
                text=True, 
                timeout=10
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            return False
    
    def _check_apktool(self) -> bool:
        """Check if apktool is available"""
        try:
            result = subprocess.run(
                ['apktool', '--version'], 
                capture_output=True, 
                text=True, 
                timeout=10
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            return False
    
    def _check_workspace_writable(self) -> bool:
        """Check if workspace directory is writable"""
        try:
            test_file = self.workspace / '.test_write'
            test_file.touch()
            test_file.unlink()
            return True
        except Exception:
            return False
    
    def _check_tools_availability(self) -> bool:
        """Check if required tools are available"""
        tools_to_check = [
            self.workspace / "tools" / "android-sdk" / "aapt",
            self.workspace / "tools" / "android-sdk" / "aapt2",
            self.workspace / "tools" / "android-sdk" / "zipalign",
            self.workspace / "tools" / "apktool" / "apktool.jar"
        ]
        
        available_tools = 0
        for tool in tools_to_check:
            if tool.exists():
                available_tools += 1
        
        return available_tools >= 2  # At least 2 tools should be available
    
    def get_tool_paths(self) -> Dict[str, Optional[Path]]:
        """Get paths to required tools"""
        return {
            'android_sdk': self.workspace / "tools" / "android-sdk",
            'apktool_jar': self.workspace / "tools" / "apktool" / "apktool.jar",
            'aapt': self.workspace / "tools" / "android-sdk" / "aapt",
            'aapt2': self.workspace / "tools" / "android-sdk" / "aapt2",
            'zipalign': self.workspace / "tools" / "android-sdk" / "zipalign",
            'apksigner': self.workspace / "tools" / "android-sdk" / "apksigner"
        }
    
    def get_environment_info(self) -> Dict[str, str]:
        """Get current environment information"""
        return {
            'lhost': self.get_lhost(),
            'lport': self.get_lport(),
            'workspace': str(self.workspace),
            'java_version': self._get_java_version(),
            'apktool_version': self._get_apktool_version()
        }
    
    def _get_java_version(self) -> str:
        """Get Java version"""
        try:
            result = subprocess.run(
                ['java', '-version'], 
                capture_output=True, 
                text=True, 
                timeout=10
            )
            if result.returncode == 0:
                lines = result.stderr.split('\n')
                for line in lines:
                    if 'version' in line:
                        return line.strip()
            return "Unknown"
        except Exception:
            return "Not available"
    
    def _get_apktool_version(self) -> str:
        """Get apktool version"""
        try:
            result = subprocess.run(
                ['apktool', '--version'], 
                capture_output=True, 
                text=True, 
                timeout=10
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return "Unknown"
        except Exception:
            return "Not available"