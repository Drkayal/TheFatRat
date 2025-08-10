import subprocess
import logging
from typing import List, Tuple, Optional, Dict
from pathlib import Path

class InjectionError(Exception):
    """Custom exception for injection errors"""
    pass

class ValidationError(Exception):
    """Custom exception for validation errors"""
    pass

class FileOperationError(Exception):
    """Custom exception for file operation errors"""
    pass

class ErrorHandler:
    """Handle errors and provide meaningful error messages"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    @staticmethod
    def run_command(cmd: List[str], timeout: int = 300, cwd: Optional[Path] = None) -> Tuple[bool, str]:
        """Run command with comprehensive error handling"""
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
                encoding='utf-8',
                errors='replace',
                cwd=cwd
            )
            
            output = (proc.stdout + "\n" + proc.stderr).strip()
            
            if proc.returncode != 0:
                return False, f"Command failed (exit code {proc.returncode}): {output}"
            
            return True, output
            
        except subprocess.TimeoutExpired:
            return False, f"Command timed out after {timeout} seconds: {' '.join(cmd)}"
        except FileNotFoundError:
            return False, f"Command not found: {cmd[0]}"
        except PermissionError:
            return False, f"Permission denied: {' '.join(cmd)}"
        except Exception as e:
            return False, f"Unexpected error: {str(e)}"
    
    def validate_file_path(self, file_path: Path, must_exist: bool = True) -> bool:
        """Validate file path"""
        try:
            if must_exist and not file_path.exists():
                raise FileOperationError(f"File not found: {file_path}")
            
            if file_path.exists() and not file_path.is_file():
                raise FileOperationError(f"Path is not a file: {file_path}")
            
            return True
        except Exception as e:
            self.logger.error(f"File validation error: {e}")
            return False
    
    def validate_directory_path(self, dir_path: Path, must_exist: bool = True, must_be_writable: bool = True) -> bool:
        """Validate directory path"""
        try:
            if must_exist and not dir_path.exists():
                raise FileOperationError(f"Directory not found: {dir_path}")
            
            if dir_path.exists() and not dir_path.is_dir():
                raise FileOperationError(f"Path is not a directory: {dir_path}")
            
            if must_be_writable and dir_path.exists():
                test_file = dir_path / '.test_write'
                test_file.touch()
                test_file.unlink()
            
            return True
        except Exception as e:
            self.logger.error(f"Directory validation error: {e}")
            return False
    
    def handle_subprocess_error(self, error: subprocess.CalledProcessError) -> str:
        """Handle subprocess errors and return meaningful message"""
        error_msg = f"Subprocess error (exit code {error.returncode})"
        
        if error.stdout:
            error_msg += f"\nStdout: {error.stdout}"
        
        if error.stderr:
            error_msg += f"\nStderr: {error.stderr}"
        
        return error_msg
    
    def log_error_with_context(self, error: Exception, context: str, additional_info: Optional[Dict] = None):
        """Log error with context and additional information"""
        error_msg = f"Error in {context}: {str(error)}"
        
        if additional_info:
            error_msg += f"\nAdditional info: {additional_info}"
        
        self.logger.error(error_msg)
        
        # Log the full traceback for debugging
        import traceback
        self.logger.debug(f"Full traceback:\n{traceback.format_exc()}")
    
    def create_error_summary(self, errors: List[Tuple[str, Exception]]) -> str:
        """Create a summary of multiple errors"""
        if not errors:
            return "No errors occurred"
        
        summary = f"Encountered {len(errors)} errors:\n"
        
        for i, (context, error) in enumerate(errors, 1):
            summary += f"{i}. {context}: {str(error)}\n"
        
        return summary