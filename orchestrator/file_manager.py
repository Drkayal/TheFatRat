import shutil
import logging
from pathlib import Path
from typing import Optional, List
from contextlib import contextmanager
import tempfile
import gc

class FileManager:
    """Handle file operations safely"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    @staticmethod
    def safe_read_text(file_path: Path, encoding: str = 'utf-8') -> str:
        """Safely read text file with fallback encodings"""
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        encodings = [encoding, 'utf-8', 'latin-1', 'cp1252']
        
        for enc in encodings:
            try:
                return file_path.read_text(encoding=enc)
            except UnicodeDecodeError:
                continue
        
        raise UnicodeDecodeError(f"Could not decode file with any encoding: {file_path}")
    
    @staticmethod
    def safe_write_text(file_path: Path, content: str, encoding: str = 'utf-8') -> None:
        """Safely write text file with backup"""
        # Ensure directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write with backup
        backup_path = file_path.with_suffix(file_path.suffix + '.bak')
        if file_path.exists():
            shutil.copy2(file_path, backup_path)
        
        try:
            file_path.write_text(content, encoding=encoding)
        except Exception:
            # Restore backup if write fails
            if backup_path.exists():
                shutil.copy2(backup_path, file_path)
            raise
    
    @staticmethod
    def copy_large_file(src: Path, dst: Path, chunk_size: int = 8192) -> bool:
        """Copy large file in chunks to avoid memory issues"""
        try:
            with open(src, 'rb') as fsrc:
                with open(dst, 'wb') as fdst:
                    while True:
                        chunk = fsrc.read(chunk_size)
                        if not chunk:
                            break
                        fdst.write(chunk)
            return True
        except Exception:
            return False
    
    @staticmethod
    def get_file_size_mb(file_path: Path) -> float:
        """Get file size in MB"""
        return file_path.stat().st_size / (1024 * 1024)
    
    @staticmethod
    @contextmanager
    def temporary_workspace():
        """Context manager for temporary workspace with cleanup"""
        temp_dir = None
        try:
            temp_dir = tempfile.mkdtemp()
            yield Path(temp_dir)
        finally:
            if temp_dir:
                try:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                except Exception:
                    pass
                gc.collect()  # Force garbage collection
    
    def cleanup_large_objects(self):
        """Clean up large objects to free memory"""
        gc.collect()
        
        # Clear any cached data
        if hasattr(self, '_cache'):
            self._cache.clear()
    
    def find_files_by_pattern(self, directory: Path, pattern: str) -> List[Path]:
        """Find files matching pattern in directory"""
        try:
            return list(directory.rglob(pattern))
        except Exception as e:
            self.logger.error(f"Error finding files with pattern {pattern}: {e}")
            return []
    
    def ensure_directory_exists(self, directory: Path) -> bool:
        """Ensure directory exists, create if necessary"""
        try:
            directory.mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            self.logger.error(f"Error creating directory {directory}: {e}")
            return False
    
    def safe_remove_file(self, file_path: Path) -> bool:
        """Safely remove file with error handling"""
        try:
            if file_path.exists():
                file_path.unlink()
            return True
        except Exception as e:
            self.logger.error(f"Error removing file {file_path}: {e}")
            return False
    
    def safe_remove_directory(self, directory: Path) -> bool:
        """Safely remove directory with error handling"""
        try:
            if directory.exists():
                shutil.rmtree(directory, ignore_errors=True)
            return True
        except Exception as e:
            self.logger.error(f"Error removing directory {directory}: {e}")
            return False