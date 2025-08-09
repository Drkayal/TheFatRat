import sqlite3
import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from contextlib import contextmanager
import threading

DATABASE_PATH = Path("/workspace/logs/fatrat.db")
DATABASE_PATH.parent.mkdir(exist_ok=True)

# Database schema
SCHEMA = """
CREATE TABLE IF NOT EXISTS uploaded_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id TEXT UNIQUE NOT NULL,
    user_id INTEGER NOT NULL,
    original_name TEXT NOT NULL,
    secure_path TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    mime_type TEXT,
    checksum TEXT NOT NULL,
    upload_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    validation_result TEXT,
    metadata_json TEXT,
    status TEXT DEFAULT 'uploaded',
    processed_timestamp DATETIME,
    task_id TEXT,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS task_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT UNIQUE NOT NULL,
    task_kind TEXT NOT NULL,
    user_id INTEGER,
    parameters_json TEXT,
    status TEXT DEFAULT 'created',
    created_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    started_timestamp DATETIME,
    completed_timestamp DATETIME,
    duration_seconds REAL,
    success BOOLEAN,
    error_message TEXT,
    output_files_json TEXT,
    logs_json TEXT
);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    user_id INTEGER,
    task_id TEXT,
    file_id TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    details_json TEXT,
    ip_address TEXT,
    user_agent TEXT,
    severity TEXT DEFAULT 'info'
);

CREATE TABLE IF NOT EXISTS file_operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_type TEXT NOT NULL,
    file_id TEXT NOT NULL,
    task_id TEXT,
    operation_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    source_path TEXT,
    target_path TEXT,
    operation_status TEXT,
    details_json TEXT
);

CREATE TABLE IF NOT EXISTS security_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    user_id INTEGER,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    severity TEXT NOT NULL,
    description TEXT,
    details_json TEXT,
    ip_address TEXT,
    resolved BOOLEAN DEFAULT FALSE,
    resolution_notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_uploaded_files_user_id ON uploaded_files(user_id);
CREATE INDEX IF NOT EXISTS idx_uploaded_files_timestamp ON uploaded_files(upload_timestamp);
CREATE INDEX IF NOT EXISTS idx_uploaded_files_status ON uploaded_files(status);
CREATE INDEX IF NOT EXISTS idx_task_executions_user_id ON task_executions(user_id);
CREATE INDEX IF NOT EXISTS idx_task_executions_status ON task_executions(status);
CREATE INDEX IF NOT EXISTS idx_task_executions_timestamp ON task_executions(created_timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_events_user_id ON audit_events(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_timestamp ON audit_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_events_type ON audit_events(event_type);
"""

@dataclass
class UploadedFile:
    file_id: str
    user_id: int
    original_name: str
    secure_path: str
    file_size: int
    mime_type: str
    checksum: str
    upload_timestamp: datetime
    validation_result: Dict[str, Any]
    metadata: Dict[str, Any]
    status: str = 'uploaded'
    processed_timestamp: Optional[datetime] = None
    task_id: Optional[str] = None
    error_message: Optional[str] = None

@dataclass
class TaskExecution:
    task_id: str
    task_kind: str
    user_id: int
    parameters: Dict[str, Any]
    status: str = 'created'
    created_timestamp: datetime = None
    started_timestamp: Optional[datetime] = None
    completed_timestamp: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    success: Optional[bool] = None
    error_message: Optional[str] = None
    output_files: List[str] = None
    logs: List[str] = None

@dataclass
class AuditEvent:
    event_type: str
    user_id: int
    timestamp: datetime
    details: Dict[str, Any]
    task_id: Optional[str] = None
    file_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    severity: str = 'info'

class DatabaseManager:
    """Advanced database manager for TheFatRat operations"""
    
    def __init__(self, db_path: Path = DATABASE_PATH):
        self.db_path = db_path
        self.lock = threading.Lock()
        self._init_database()
    
    def _init_database(self):
        """Initialize database with schema"""
        with self.get_connection() as conn:
            conn.executescript(SCHEMA)
            conn.commit()
    
    @contextmanager
    def get_connection(self):
        """Get database connection with proper error handling"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            raise e
        finally:
            if conn:
                conn.close()
    
    def record_file_upload(self, file_info: UploadedFile) -> int:
        """Record file upload with full metadata"""
        with self.lock:
            with self.get_connection() as conn:
                cursor = conn.execute("""
                    INSERT INTO uploaded_files (
                        file_id, user_id, original_name, secure_path, file_size,
                        mime_type, checksum, validation_result, metadata_json, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    file_info.file_id,
                    file_info.user_id,
                    file_info.original_name,
                    file_info.secure_path,
                    file_info.file_size,
                    file_info.mime_type,
                    file_info.checksum,
                    json.dumps(file_info.validation_result),
                    json.dumps(file_info.metadata),
                    file_info.status
                ))
                conn.commit()
                return cursor.lastrowid
    
    def update_file_status(self, file_id: str, status: str, task_id: Optional[str] = None, error_message: Optional[str] = None):
        """Update file processing status"""
        with self.lock:
            with self.get_connection() as conn:
                conn.execute("""
                    UPDATE uploaded_files 
                    SET status = ?, task_id = ?, error_message = ?, processed_timestamp = CURRENT_TIMESTAMP
                    WHERE file_id = ?
                """, (status, task_id, error_message, file_id))
                conn.commit()
    
    def record_task_execution(self, task_info: TaskExecution) -> int:
        """Record task execution details"""
        with self.lock:
            with self.get_connection() as conn:
                cursor = conn.execute("""
                    INSERT INTO task_executions (
                        task_id, task_kind, user_id, parameters_json, status,
                        created_timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    task_info.task_id,
                    task_info.task_kind,
                    task_info.user_id,
                    json.dumps(task_info.parameters),
                    task_info.status,
                    task_info.created_timestamp or datetime.now()
                ))
                conn.commit()
                return cursor.lastrowid
    
    def update_task_status(self, task_id: str, status: str, success: Optional[bool] = None, 
                          error_message: Optional[str] = None, output_files: Optional[List[str]] = None):
        """Update task execution status"""
        with self.lock:
            with self.get_connection() as conn:
                timestamp_field = "started_timestamp" if status == "running" else "completed_timestamp"
                duration = None
                
                if status in ["completed", "failed"]:
                    # Calculate duration
                    row = conn.execute("SELECT started_timestamp FROM task_executions WHERE task_id = ?", (task_id,)).fetchone()
                    if row and row['started_timestamp']:
                        start_time = datetime.fromisoformat(row['started_timestamp'])
                        duration = (datetime.now() - start_time).total_seconds()
                
                conn.execute(f"""
                    UPDATE task_executions 
                    SET status = ?, success = ?, error_message = ?, output_files_json = ?, 
                        {timestamp_field} = CURRENT_TIMESTAMP, duration_seconds = ?
                    WHERE task_id = ?
                """, (status, success, error_message, json.dumps(output_files) if output_files else None, duration, task_id))
                conn.commit()
    
    def record_audit_event(self, event: AuditEvent) -> int:
        """Record audit event for security tracking"""
        with self.lock:
            with self.get_connection() as conn:
                cursor = conn.execute("""
                    INSERT INTO audit_events (
                        event_type, user_id, task_id, file_id, details_json,
                        ip_address, user_agent, severity
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event.event_type,
                    event.user_id,
                    event.task_id,
                    event.file_id,
                    json.dumps(event.details),
                    event.ip_address,
                    event.user_agent,
                    event.severity
                ))
                conn.commit()
                return cursor.lastrowid
    
    def record_file_operation(self, operation_type: str, file_id: str, task_id: Optional[str] = None,
                             source_path: Optional[str] = None, target_path: Optional[str] = None,
                             status: str = "success", details: Optional[Dict] = None):
        """Record file operations for audit trail"""
        with self.lock:
            with self.get_connection() as conn:
                cursor = conn.execute("""
                    INSERT INTO file_operations (
                        operation_type, file_id, task_id, source_path, target_path,
                        operation_status, details_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    operation_type,
                    file_id,
                    task_id,
                    source_path,
                    target_path,
                    status,
                    json.dumps(details) if details else None
                ))
                conn.commit()
                return cursor.lastrowid
    
    def record_security_event(self, event_type: str, user_id: int, severity: str, 
                             description: str, details: Optional[Dict] = None, 
                             ip_address: Optional[str] = None):
        """Record security-related events"""
        with self.lock:
            with self.get_connection() as conn:
                cursor = conn.execute("""
                    INSERT INTO security_events (
                        event_type, user_id, severity, description, details_json, ip_address
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    event_type,
                    user_id,
                    severity,
                    description,
                    json.dumps(details) if details else None,
                    ip_address
                ))
                conn.commit()
                return cursor.lastrowid
    
    def get_user_files(self, user_id: int, limit: int = 50, status: Optional[str] = None) -> List[Dict]:
        """Get uploaded files for a user"""
        with self.get_connection() as conn:
            query = "SELECT * FROM uploaded_files WHERE user_id = ?"
            params = [user_id]
            
            if status:
                query += " AND status = ?"
                params.append(status)
            
            query += " ORDER BY upload_timestamp DESC LIMIT ?"
            params.append(limit)
            
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]
    
    def get_user_tasks(self, user_id: int, limit: int = 50) -> List[Dict]:
        """Get task executions for a user"""
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM task_executions 
                WHERE user_id = ? 
                ORDER BY created_timestamp DESC 
                LIMIT ?
            """, (user_id, limit)).fetchall()
            return [dict(row) for row in rows]
    
    def get_audit_trail(self, user_id: Optional[int] = None, hours: int = 24, limit: int = 100) -> List[Dict]:
        """Get audit trail for security monitoring"""
        with self.get_connection() as conn:
            query = "SELECT * FROM audit_events WHERE timestamp > ?"
            params = [datetime.now() - timedelta(hours=hours)]
            
            if user_id:
                query += " AND user_id = ?"
                params.append(user_id)
            
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]
    
    def get_security_events(self, severity: Optional[str] = None, hours: int = 24, unresolved_only: bool = True) -> List[Dict]:
        """Get security events for monitoring"""
        with self.get_connection() as conn:
            query = "SELECT * FROM security_events WHERE timestamp > ?"
            params = [datetime.now() - timedelta(hours=hours)]
            
            if severity:
                query += " AND severity = ?"
                params.append(severity)
            
            if unresolved_only:
                query += " AND resolved = FALSE"
            
            query += " ORDER BY timestamp DESC"
            
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]
    
    def get_file_by_id(self, file_id: str) -> Optional[Dict]:
        """Get file information by ID"""
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM uploaded_files WHERE file_id = ?", (file_id,)).fetchone()
            return dict(row) if row else None
    
    def get_task_by_id(self, task_id: str) -> Optional[Dict]:
        """Get task information by ID"""
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM task_executions WHERE task_id = ?", (task_id,)).fetchone()
            return dict(row) if row else None
    
    def cleanup_old_records(self, days: int = 30):
        """Clean up old records for maintenance"""
        cutoff_date = datetime.now() - timedelta(days=days)
        
        with self.lock:
            with self.get_connection() as conn:
                # Clean up old audit events
                conn.execute("DELETE FROM audit_events WHERE timestamp < ?", (cutoff_date,))
                
                # Clean up old file operations
                conn.execute("DELETE FROM file_operations WHERE operation_timestamp < ?", (cutoff_date,))
                
                # Clean up completed tasks older than cutoff
                conn.execute("""
                    DELETE FROM task_executions 
                    WHERE completed_timestamp < ? AND status IN ('completed', 'failed')
                """, (cutoff_date,))
                
                # Clean up old uploaded files that are processed
                conn.execute("""
                    DELETE FROM uploaded_files 
                    WHERE processed_timestamp < ? AND status IN ('processed', 'failed')
                """, (cutoff_date,))
                
                conn.commit()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get database statistics"""
        with self.get_connection() as conn:
            stats = {}
            
            # File statistics
            stats['files'] = {
                'total': conn.execute("SELECT COUNT(*) FROM uploaded_files").fetchone()[0],
                'uploaded': conn.execute("SELECT COUNT(*) FROM uploaded_files WHERE status = 'uploaded'").fetchone()[0],
                'processing': conn.execute("SELECT COUNT(*) FROM uploaded_files WHERE status = 'processing'").fetchone()[0],
                'processed': conn.execute("SELECT COUNT(*) FROM uploaded_files WHERE status = 'processed'").fetchone()[0],
                'failed': conn.execute("SELECT COUNT(*) FROM uploaded_files WHERE status = 'failed'").fetchone()[0]
            }
            
            # Task statistics
            stats['tasks'] = {
                'total': conn.execute("SELECT COUNT(*) FROM task_executions").fetchone()[0],
                'running': conn.execute("SELECT COUNT(*) FROM task_executions WHERE status = 'running'").fetchone()[0],
                'completed': conn.execute("SELECT COUNT(*) FROM task_executions WHERE status = 'completed'").fetchone()[0],
                'failed': conn.execute("SELECT COUNT(*) FROM task_executions WHERE status = 'failed'").fetchone()[0]
            }
            
            # Recent activity (last 24 hours)
            last_24h = datetime.now() - timedelta(hours=24)
            stats['recent'] = {
                'files_uploaded': conn.execute("SELECT COUNT(*) FROM uploaded_files WHERE upload_timestamp > ?", (last_24h,)).fetchone()[0],
                'tasks_executed': conn.execute("SELECT COUNT(*) FROM task_executions WHERE created_timestamp > ?", (last_24h,)).fetchone()[0],
                'audit_events': conn.execute("SELECT COUNT(*) FROM audit_events WHERE timestamp > ?", (last_24h,)).fetchone()[0]
            }
            
            return stats

# Global database manager instance
db_manager = DatabaseManager()

class AuditTracker:
    """Advanced audit tracking for security and compliance"""
    
    @staticmethod
    def track_file_upload(user_id: int, file_id: str, file_info: Dict, ip_address: Optional[str] = None):
        """Track file upload event"""
        event = AuditEvent(
            event_type="file_upload",
            user_id=user_id,
            timestamp=datetime.now(),
            file_id=file_id,
            details={
                "original_name": file_info.get("original_name"),
                "file_size": file_info.get("file_size"),
                "mime_type": file_info.get("mime_type"),
                "checksum": file_info.get("checksum")
            },
            ip_address=ip_address,
            severity="info"
        )
        db_manager.record_audit_event(event)
    
    @staticmethod
    def track_task_creation(user_id: int, task_id: str, task_kind: str, parameters: Dict, ip_address: Optional[str] = None):
        """Track task creation event"""
        event = AuditEvent(
            event_type="task_created",
            user_id=user_id,
            timestamp=datetime.now(),
            task_id=task_id,
            details={
                "task_kind": task_kind,
                "parameters": parameters
            },
            ip_address=ip_address,
            severity="info"
        )
        db_manager.record_audit_event(event)
    
    @staticmethod
    def track_security_event(user_id: int, event_type: str, severity: str, description: str, 
                           details: Optional[Dict] = None, ip_address: Optional[str] = None):
        """Track security-related events"""
        db_manager.record_security_event(event_type, user_id, severity, description, details, ip_address)
        
        # Also create audit event
        event = AuditEvent(
            event_type=f"security_{event_type}",
            user_id=user_id,
            timestamp=datetime.now(),
            details=details or {},
            ip_address=ip_address,
            severity=severity
        )
        db_manager.record_audit_event(event)
    
    @staticmethod
    def track_file_modification(file_id: str, task_id: str, operation: str, details: Optional[Dict] = None):
        """Track file modification operations"""
        db_manager.record_file_operation(
            operation_type=operation,
            file_id=file_id,
            task_id=task_id,
            status="success",
            details=details
        )

# Export main components
__all__ = ['DatabaseManager', 'AuditTracker', 'db_manager', 'UploadedFile', 'TaskExecution', 'AuditEvent']