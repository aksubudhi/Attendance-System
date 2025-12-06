

import cv2
import os
import insightface
import numpy as np
import psycopg2
from psycopg2 import pool, Error as PostgresError
from psycopg2.extras import RealDictCursor
import pickle
import datetime
import asyncio
import json
import base64
import logging
from logging.handlers import RotatingFileHandler
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from typing import List, Dict, Optional, Tuple
from contextlib import contextmanager
from collections import defaultdict
import time
from functools import lru_cache
import secrets
from starlette.requests import Request
from typing import List, Dict, Optional, Tuple
import faiss
import bcrypt

logger = logging.getLogger(__name__)


# ============ WEBSOCKET MANAGER WITH LOCKS ============

def get_ist_time():
    """Get current time in IST"""
    from pytz import timezone
    IST = timezone('Asia/Kolkata')
    return datetime.datetime.now(IST)

def utc_to_ist(utc_time):
    """Convert UTC datetime to IST"""
    from pytz import timezone
    IST = timezone('Asia/Kolkata')

    if utc_time.tzinfo is None:
        utc_time = utc_time.replace(tzinfo=timezone('UTC'))

    return utc_time.astimezone(IST)

class WebSocketManager:
    """Manages WebSocket connections with persistent monitoring and admin-only stop"""

    def __init__(self):
        self.active_connections = []
        self.connection_users = {}
        self.start_lock = asyncio.Lock()
        self.is_monitoring = False
        self.monitor_tasks = []
        self.started_by = None
        self.started_by_role = None
        self.last_frame = {'entry': None, 'exit': None}
        self.frame_timestamps = {'entry': None, 'exit': None}
        logger.info("WebSocketManager initialized")

    async def connect(self, websocket, user_id: str, user_name: str, user_role: str = "user"):
        """Register new WebSocket connection with role information"""
        await websocket.accept()
        self.active_connections.append(websocket)
        self.connection_users[websocket] = (user_id, user_name, user_role)
        logger.info(f"Connected: {user_name} ({user_role}). Total: {len(self.active_connections)}")

        await websocket.send_json({
            'type': 'connection_status',
            'message': 'Connected to monitoring system',
            'active_users': len(self.active_connections),
            'cameras_running': self.is_monitoring,
            'your_role': user_role,
            'can_stop': user_role == 'admin'
        })

    def disconnect(self, websocket, user_id: str):
        """Unregister WebSocket connection"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            user_info = self.connection_users.pop(websocket, ("unknown", "Unknown", "user"))
            user_name = user_info[1] if isinstance(user_info, tuple) else user_info
            logger.info(f"Disconnected: {user_name}. Remaining: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Send message to all connected users - OPTIMIZED"""
        if not self.active_connections:
            return

        
        if message.get('type') == 'frame':
            await self.cache_frame(message)

        disconnected = []
        # Send to all connections concurrently instead of sequentially
        tasks = []

        for connection in self.active_connections:
            try:
                tasks.append(connection.send_json(message))
            except Exception as e:
                logger.error(f"Broadcast error: {e}")
                disconnected.append(connection)

        # Wait for all sends concurrently
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        for ws in disconnected:
            if ws in self.active_connections:
                self.active_connections.remove(ws)
                self.connection_users.pop(ws, None)


    async def send_cached_frames(self, websocket, retry_count: int = 0, max_retries: int = 3):
        """Send last cached frames to newly joined user with retry logic"""
        try:
            frames_sent = 0
            
            if self.last_frame['entry']:
                try:
                    await websocket.send_json({
                        'type': 'frame',
                        'camera': 'entry',
                        'image': self.last_frame['entry'],
                        'faces_count': 0
                    })
                    frames_sent += 1
                    logger.debug("✅ Sent cached entry frame to new user")
                except Exception as e:
                    logger.error(f"Error sending entry frame: {e}")
            
            if self.last_frame['exit']:
                try:
                    await websocket.send_json({
                        'type': 'frame',
                        'camera': 'exit',
                        'image': self.last_frame['exit'],
                        'faces_count': 0
                    })
                    frames_sent += 1
                    logger.debug("✅ Sent cached exit frame to new user")
                except Exception as e:
                    logger.error(f"Error sending exit frame: {e}")
            
            if frames_sent == 0:
                logger.warning("⚠️ No cached frames available - cameras may not be running yet")
            else:
                logger.info(f"✅ Sent {frames_sent} cached frames to new user")
                    
        except Exception as e:
            logger.error(f"❌ Error sending cached frames: {e}")
            # Retry sending if connection still valid
            if retry_count < max_retries:
                await asyncio.sleep(0.5)
                await self.send_cached_frames(websocket, retry_count + 1, max_retries)

    # 🟢 IMPROVED: Cache frame with timestamp
    async def cache_frame(self, message: dict):
        """Cache frame in memory for new users - with timestamp tracking"""
        try:
            camera = message.get('camera')
            if camera in ['entry', 'exit']:
                self.last_frame[camera] = message.get('image')
                self.frame_timestamps[camera] = time.time()
        except Exception as e:
            logger.error(f"❌ Error caching frame: {e}")

    def get_frame_age(self, camera: str) -> float:
        """Get age of cached frame in seconds"""
        if self.frame_timestamps[camera]:
            return time.time() - self.frame_timestamps[camera]
        return float('inf')

    def has_fresh_frames(self, max_age_seconds: int = 5) -> bool:
        """Check if both cameras have fresh frames"""
        entry_age = self.get_frame_age('entry')
        exit_age = self.get_frame_age('exit')
        return entry_age <= max_age_seconds and exit_age <= max_age_seconds

# ============ POOLED DATABASE SERVICE ============

class PooledDatabaseService:
    """Database service with connection pooling"""

    def __init__(self, db_config: dict):
        """Initialize with pooled connections"""
        try:
            # PostgreSQL connection pool
            self.pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=5,
                maxconn=20,
                host=db_config['host'],
                port=db_config.get('port', 5432),
                user=db_config['user'],
                password=db_config['password'],
                database=db_config['database']
            )
            logger.info("PostgreSQL connection pool initialized")
        except PostgresError as e:
            logger.critical(f"PostgreSQL pool creation failed: {e}")
            raise


    @contextmanager
    def get_connection(self):
        """Thread-safe connection manager"""
        conn = None
        try:
            conn = self.pool.getconn()
            yield conn
        except PostgresError as e:
            logger.error(f"Database error: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                self.pool.putconn(conn)


    @contextmanager
    def get_conn_cursor(self, cursor_factory=None):
        """
        Thread-safe connection and cursor manager.
        Yields (connection, cursor), ensuring both are closed/released afterward.
        """
        conn = None
        cursor = None
        try:
            conn = self.pool.getconn()
            # Optionally use RealDictCursor for dictionary results
            cursor = conn.cursor(cursor_factory=cursor_factory)
            yield conn, cursor
        except PostgresError as e:
            logger.error(f"Database error in get_conn_cursor: {e}")
            if conn:
                conn.rollback()
            # Re-raise the exception so it can be handled by the caller
            raise
        finally:
            if cursor:
                cursor.close()
            if conn:
                self.pool.putconn(conn)


    def init_schema(self):
        """Initialize PostgreSQL schema with COMBINED employees table (8 angles)"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Enable pgvector extension
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")

                # COMBINED employees table with 8 face angle embeddings
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS employees (
                        id SERIAL PRIMARY KEY,
                        emp_id VARCHAR(20) UNIQUE NOT NULL,
                        name VARCHAR(100) NOT NULL,
                        department VARCHAR(50),
                        position VARCHAR(50),
                        is_active BOOLEAN DEFAULT TRUE,
                        
                        -- Front angle
                        front_embedding vector(512),
                        front_quality FLOAT,
                        
                        -- Looking up
                        looking_up_embedding vector(512),
                        looking_up_quality FLOAT,
                        
                        -- Left side
                        left_embedding vector(512),
                        left_quality FLOAT,
                        
                        -- Right side
                        right_embedding vector(512),
                        right_quality FLOAT,
                        
                        -- Up left diagonal
                        up_left_embedding vector(512),
                        up_left_quality FLOAT,
                        
                        -- Up right diagonal
                        up_right_embedding vector(512),
                        up_right_quality FLOAT,
                        
                        -- Tilt left
                        tilt_left_embedding vector(512),
                        tilt_left_quality FLOAT,
                        
                        -- Tilt right
                        tilt_right_embedding vector(512),
                        tilt_right_quality FLOAT,
                        
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_emp_name ON employees(name)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_emp_dept ON employees(department)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_emp_active ON employees(is_active)")
                
                # Vector indexes for all 8 angles (for fast similarity search)
                try:
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_front_emb ON employees USING ivfflat (front_embedding vector_cosine_ops)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_looking_up_emb ON employees USING ivfflat (looking_up_embedding vector_cosine_ops)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_left_emb ON employees USING ivfflat (left_embedding vector_cosine_ops)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_right_emb ON employees USING ivfflat (right_embedding vector_cosine_ops)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_up_left_emb ON employees USING ivfflat (up_left_embedding vector_cosine_ops)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_up_right_emb ON employees USING ivfflat (up_right_embedding vector_cosine_ops)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tilt_left_emb ON employees USING ivfflat (tilt_left_embedding vector_cosine_ops)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tilt_right_emb ON employees USING ivfflat (tilt_right_embedding vector_cosine_ops)")
                except:
                    logger.warning("Vector indexes creation skipped (may need data first)")

                # Attendance logs (NO CHANGE - same structure)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS attendance_logs (
                        id BIGSERIAL PRIMARY KEY,
                        emp_id VARCHAR(20) NOT NULL,
                        date DATE NOT NULL,
                        first_in TIME DEFAULT NULL,
                        last_out TIME DEFAULT NULL,
                        in_camera_id VARCHAR(50),
                        out_camera_id VARCHAR(50),
                        in_confidence FLOAT,
                        out_confidence FLOAT,
                        year_month VARCHAR(7),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (emp_id) REFERENCES employees(emp_id) ON DELETE CASCADE,
                        UNIQUE (emp_id, date)
                    )
                """)
                
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_att_date ON attendance_logs(date)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_att_emp_date ON attendance_logs(emp_id, date)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_att_year_month ON attendance_logs(year_month)")

                # System stats
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS system_stats (
                        id SERIAL PRIMARY KEY,
                        stat_date DATE NOT NULL UNIQUE,
                        total_attendance INT DEFAULT 0,
                        unique_employees INT DEFAULT 0,
                        total_recognitions INT DEFAULT 0,
                        avg_confidence FLOAT DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                conn.commit()
                cursor.close()
                logger.info("PostgreSQL schema initialized with combined employees table")

        except PostgresError as e:
            logger.error(f"Schema initialization failed: {e}")
            raise



    def init_auth_schema(self):
        """Initialize authentication schema"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id SERIAL PRIMARY KEY,
                        username VARCHAR(50) UNIQUE NOT NULL,
                        password_hash VARCHAR(255) NOT NULL,
                        full_name VARCHAR(100) NOT NULL,
                        email VARCHAR(100) UNIQUE NOT NULL,
                        role VARCHAR(20) DEFAULT 'user' CHECK (role IN ('admin', 'manager', 'user')),
                        is_active BOOLEAN DEFAULT TRUE,
                        failed_attempts INT DEFAULT 0,
                        locked_until TIMESTAMP NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_login TIMESTAMP NULL,
                        password_changed_at TIMESTAMP NULL
                    )
                """)
                
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_username ON users(username)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_email ON users(email)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_active ON users(is_active)")

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        id SERIAL PRIMARY KEY,
                        session_token VARCHAR(255) UNIQUE NOT NULL,
                        user_id INT NOT NULL,
                        expires_at TIMESTAMP NOT NULL,
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    )
                """)
                
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_session_token ON sessions(session_token)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_session_user ON sessions(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_session_expires ON sessions(expires_at)")

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS audit_log (
                        id BIGSERIAL PRIMARY KEY,
                        user_id INT NULL,
                        action VARCHAR(100) NOT NULL,
                        details TEXT,
                        ip_address VARCHAR(45),
                        user_agent TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
                    )
                """)
                
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at)")

                conn.commit()
                cursor.close()
                logger.info("Authentication schema initialized")

        except PostgresError as e:
            logger.error(f"Auth schema initialization failed: {e}")
            raise


    def create_employee(self, emp_id: str, name: str, department: str = "", position: str = "") -> dict:
        """Create or reactivate employee"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("SELECT emp_id, is_active FROM employees WHERE emp_id = %s", (emp_id,))
                existing = cursor.fetchone()

                if existing:
                    emp_id_db, is_active = existing
                    if not is_active:
                        cursor.execute("""
                            UPDATE employees
                            SET name = %s, department = %s, position = %s, 
                                is_active = TRUE, updated_at = CURRENT_TIMESTAMP
                            WHERE emp_id = %s
                        """, (name, department, position, emp_id_db))
                        conn.commit()
                        cursor.close()
                        self.invalidate_employee_cache()
                        logger.info(f"Employee reactivated: {emp_id_db}")
                        return {"success": True, "message": "Employee reactivated"}
                    else:
                        cursor.close()
                        return {"success": False, "message": "Employee ID already exists"}

                cursor.execute("""
                    INSERT INTO employees (emp_id, name, department, position, is_active)
                    VALUES (%s, %s, %s, %s, TRUE)
                """, (emp_id, name, department, position))

                conn.commit()
                cursor.close()
                self.invalidate_employee_cache()
                logger.info(f"Employee created: {emp_id}")
                return {"success": True, "message": "Employee created"}

        except PostgresError as e:
            logger.error(f"Create employee error: {e}")
            return {"success": False, "message": str(e)}


    @lru_cache(maxsize=1)
    def get_all_employees(self, cache_key: int = 0) -> List[dict]:
        """Get all active employees with caching (combined table structure)"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT
                        e.emp_id, e.name, e.department, e.position,
                        e.is_active, e.created_at,
                        -- Count non-null embeddings (8 possible angles)
                        (CASE WHEN front_embedding IS NOT NULL THEN 1 ELSE 0 END +
                         CASE WHEN looking_up_embedding IS NOT NULL THEN 1 ELSE 0 END +
                         CASE WHEN left_embedding IS NOT NULL THEN 1 ELSE 0 END +
                         CASE WHEN right_embedding IS NOT NULL THEN 1 ELSE 0 END +
                         CASE WHEN up_left_embedding IS NOT NULL THEN 1 ELSE 0 END +
                         CASE WHEN up_right_embedding IS NOT NULL THEN 1 ELSE 0 END +
                         CASE WHEN tilt_left_embedding IS NOT NULL THEN 1 ELSE 0 END +
                         CASE WHEN tilt_right_embedding IS NOT NULL THEN 1 ELSE 0 END) as face_count,
                        -- Average quality across all non-null embeddings
                        (COALESCE(front_quality, 0) + COALESCE(looking_up_quality, 0) +
                         COALESCE(left_quality, 0) + COALESCE(right_quality, 0) +
                         COALESCE(up_left_quality, 0) + COALESCE(up_right_quality, 0) +
                         COALESCE(tilt_left_quality, 0) + COALESCE(tilt_right_quality, 0)) /
                        NULLIF((CASE WHEN front_quality IS NOT NULL THEN 1 ELSE 0 END +
                         CASE WHEN looking_up_quality IS NOT NULL THEN 1 ELSE 0 END +
                         CASE WHEN left_quality IS NOT NULL THEN 1 ELSE 0 END +
                         CASE WHEN right_quality IS NOT NULL THEN 1 ELSE 0 END +
                         CASE WHEN up_left_quality IS NOT NULL THEN 1 ELSE 0 END +
                         CASE WHEN up_right_quality IS NOT NULL THEN 1 ELSE 0 END +
                         CASE WHEN tilt_left_quality IS NOT NULL THEN 1 ELSE 0 END +
                         CASE WHEN tilt_right_quality IS NOT NULL THEN 1 ELSE 0 END), 0) as avg_quality
                    FROM employees e
                    WHERE e.is_active = TRUE
                    ORDER BY e.created_at DESC
                """)

                employees = []
                for row in cursor.fetchall():
                    employees.append({
                        'emp_id': row[0],
                        'name': row[1],
                        'department': row[2] or '',
                        'position': row[3] or '',
                        'is_active': row[4],
                        'created_at': row[5].isoformat() if row[5] else None,
                        'face_count': row[6],
                        'avg_quality': float(row[7]) if row[7] else 0
                    })

                cursor.close()
                return employees

        except PostgresError as e:
            logger.error(f"Get employees error: {e}")
            return []


    def invalidate_employee_cache(self):
        """Clear employee cache"""
        self.get_all_employees.cache_clear()


    def update_employee(self, emp_id: str, name: str, department: str, position: str) -> dict:
        """Update employee details"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE employees
                    SET name = %s, department = %s, position = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE emp_id = %s
                """, (name, department, position, emp_id))
                
                if cursor.rowcount == 0:
                    cursor.close()
                    return {"success": False, "message": "Employee not found"}
                
                conn.commit()
                cursor.close()
                self.invalidate_employee_cache()
                logger.info(f"Employee updated: {emp_id}")
                return {"success": True, "message": "Employee updated"}

        except PostgresError as e:
            logger.error(f"Update error: {e}")
            return {"success": False, "message": str(e)}



    def delete_employee(self, emp_id: str) -> dict:
        """Soft delete employee"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE employees
                    SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP
                    WHERE emp_id = %s
                """, (emp_id,))

                if cursor.rowcount == 0:
                    cursor.close()
                    return {"success": False, "message": "Employee not found"}

                conn.commit()
                cursor.close()
                self.invalidate_employee_cache()
                logger.info(f"Employee deactivated: {emp_id}")
                return {"success": True, "message": "Employee deactivated"}

        except PostgresError as e:
            logger.error(f"Delete error: {e}")
            return {"success": False, "message": str(e)}


    def save_face_embedding(self, emp_id: str, embedding: np.ndarray, angle: str, quality: float) -> dict:
        """Save face embedding to combined employees table (8 angles)"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Map angle names to column names
                angle_mapping = {
                    'front': ('front_embedding', 'front_quality'),
                    'looking_up': ('looking_up_embedding', 'looking_up_quality'),
                    'left': ('left_embedding', 'left_quality'),
                    'right': ('right_embedding', 'right_quality'),
                    'up_left': ('up_left_embedding', 'up_left_quality'),
                    'up_right': ('up_right_embedding', 'up_right_quality'),
                    'tilt_left': ('tilt_left_embedding', 'tilt_left_quality'),
                    'tilt_right': ('tilt_right_embedding', 'tilt_right_quality')
                }

                if angle not in angle_mapping:
                    return {"success": False, "message": f"Invalid angle: {angle}"}

                emb_col, qual_col = angle_mapping[angle]

                # Convert numpy array to list for pgvector
                embedding_list = embedding.flatten().tolist()

                # Update the specific angle column
                cursor.execute(f"""
                    UPDATE employees
                    SET {emb_col} = %s::vector, {qual_col} = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE emp_id = %s
                """, (embedding_list, float(quality), emp_id))

                if cursor.rowcount == 0:
                    cursor.close()
                    return {"success": False, "message": "Employee not found"}

                conn.commit()
                cursor.close()
                logger.info(f"Face saved: {emp_id}, {angle}, quality: {quality:.2f}")
                return {"success": True, "message": "Face saved", "quality": quality}

        except PostgresError as e:
            logger.error(f"Save embedding error: {e}")
            return {"success": False, "message": str(e)}


    def load_all_embeddings(self) -> Dict[str, dict]:
        """Load all embeddings from combined employees table (8 angles)"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Fetch all employees with their embeddings (cast vector to text)
                cursor.execute("""
                    SELECT 
                        emp_id, name,
                        front_embedding::text, looking_up_embedding::text,
                        left_embedding::text, right_embedding::text,
                        up_left_embedding::text, up_right_embedding::text,
                        tilt_left_embedding::text, tilt_right_embedding::text
                    FROM employees
                    WHERE is_active = TRUE
                """)
                
                face_map = {}
                for row in cursor.fetchall():
                    emp_id = row[0]
                    name = row[1]
                    embeddings = []
                    
                    # Collect all non-null embeddings (8 possible angles)
                    for i in range(2, 10):  # columns 2-9 are embeddings
                        if row[i] is not None:
                            # pgvector returns string like "[0.1,0.2,...]"
                            # Parse it as JSON and convert to numpy array
                            emb_list = json.loads(row[i])
                            emb_array = np.array(emb_list, dtype=np.float32)
                            embeddings.append(emb_array)
                    
                    if embeddings:  # Only add if has at least one embedding
                        face_map[emp_id] = {
                            'name': name,
                            'embeddings': embeddings
                        }
                
                cursor.close()
                logger.info(f"Loaded {len(face_map)} active employees with embeddings")
                return face_map

        except PostgresError as e:
            logger.error(f"Load embeddings error: {e}")
            return {}



    def log_attendance_update_only(self, emp_id: str, event_type: str, camera_id: str,
                                    confidence: float, timestamp: datetime.datetime) -> dict:
        """UPDATE-ONLY attendance - ONE row per employee per day (IST timezone)"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Convert to IST (UTC+5:30)
                from pytz import timezone
                IST = timezone('Asia/Kolkata')

                # If timestamp is naive (no timezone), assume it's UTC
                if timestamp.tzinfo is None:
                    timestamp_utc = timestamp.replace(tzinfo=timezone('UTC'))
                else:
                    timestamp_utc = timestamp

                # Convert to IST
                timestamp_ist = timestamp_utc.astimezone(IST)

                today = timestamp_ist.date()
                time_only = timestamp_ist.strftime('%H:%M:%S')

                logger.debug(f"Logging attendance (IST) - emp_id: {emp_id}, date: {today}, time: {time_only}, event: {event_type}")

                if event_type == 'IN':
                    cursor.execute("""
                        SELECT id, first_in
                        FROM attendance_logs
                        WHERE emp_id = %s AND date = %s
                    """, (emp_id, today))

                    existing = cursor.fetchone()

                    if existing:
                        cursor.close()
                        logger.debug(f"IN already logged for {emp_id}")
                        return {"success": True, "message": "IN already logged", "action": "skipped"}
                    else:
                        cursor.execute("""
                            INSERT INTO attendance_logs
                            (emp_id, date, first_in, in_camera_id, in_confidence)
                            VALUES (%s, %s, %s, %s, %s)
                        """, (emp_id, today, time_only, camera_id, float(confidence)))

                        conn.commit()
                        cursor.close()
                        logger.info(f"IN logged (IST): {emp_id} at {time_only}")
                        return {"success": True, "message": "IN logged", "action": "inserted"}

                elif event_type == 'OUT':
                    cursor.execute("""
                        SELECT id, first_in, last_out
                        FROM attendance_logs
                        WHERE emp_id = %s AND date = %s
                    """, (emp_id, today))

                    existing = cursor.fetchone()

                    if existing:
                        record_id, first_in, last_out = existing

                        # SMART LOGIC: Check if person is already logged IN
                        if first_in is not None:
                            # Person is already logged IN - this is a valid OUT
                            cursor.execute("""
                                UPDATE attendance_logs
                                SET last_out = %s,
                                    out_camera_id = %s,
                                    out_confidence = %s,
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE id = %s
                            """, (time_only, camera_id, float(confidence), record_id))

                            conn.commit()
                            cursor.close()
                            logger.info(f"OUT updated (IST): {emp_id} at {time_only}")
                            return {"success": True, "message": "OUT updated", "action": "updated"}
                        else:
                            # Person NOT logged IN yet - treat this as IN (exit camera used as entry)
                            cursor.execute("""
                                UPDATE attendance_logs
                                SET first_in = %s,
                                    in_camera_id = %s,
                                    in_confidence = %s,
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE id = %s
                            """, (time_only, camera_id, float(confidence), record_id))

                            conn.commit()
                            cursor.close()
                            logger.info(f"IN logged on EXIT camera (IST): {emp_id} at {time_only} - Smart Detection")
                            return {"success": True, "message": "IN logged (EXIT camera used)", "action": "updated"}
                    else:
                        # No record exists - create new one with IN time
                        cursor.execute("""
                            INSERT INTO attendance_logs
                            (emp_id, date, first_in, in_camera_id, in_confidence)
                            VALUES (%s, %s, %s, %s, %s)
                        """, (emp_id, today, time_only, camera_id, float(confidence)))

                        conn.commit()
                        cursor.close()
                        logger.info(f"IN logged on EXIT camera (IST): {emp_id} at {time_only} - Smart Detection")
                        return {"success": True, "message": "IN logged (EXIT camera used)", "action": "inserted"}

                return {"success": False, "message": "Invalid event type"}

        except PostgresError as e:
            logger.error(f"Log attendance error: {e}")
            return {"success": False, "message": str(e)}



    def get_attendance_summary(self, date_from: str, date_to: str, limit: int = 10000) -> List[dict]:
        """Get attendance summary"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT
                        e.emp_id, e.name, e.department,
                        al.date, al.first_in, al.last_out
                    FROM attendance_logs al
                    JOIN employees e ON al.emp_id = e.emp_id
                    WHERE al.date BETWEEN %s AND %s
                    ORDER BY al.date DESC, e.name ASC
                    LIMIT %s
                """, (date_from, date_to, limit))

                records = []
                for row in cursor.fetchall():
                    emp_id, name, dept, date, first_in, last_out = row

                    duration = None
                    if first_in and last_out:
                        try:
                            in_time = datetime.datetime.strptime(str(first_in), '%H:%M:%S')
                            out_time = datetime.datetime.strptime(str(last_out), '%H:%M:%S')
                            diff = out_time - in_time
                            hours = diff.seconds // 3600
                            minutes = (diff.seconds % 3600) // 60
                            duration = f"{hours}h {minutes}m"
                        except:
                            duration = None

                    records.append({
                        'emp_id': emp_id,
                        'name': name,
                        'department': dept or '',
                        'date': str(date),
                        'first_in': str(first_in) if first_in else None,
                        'last_out': str(last_out) if last_out else None,
                        'duration': duration
                    })

                cursor.close()
                return records

        except PostgresError as e:
            logger.error(f"Get attendance error: {e}")
            return []


    def cleanup_old_logs(self, days_to_keep: int = 365):
        """Archive old attendance logs"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cutoff_date = datetime.date.today() - datetime.timedelta(days=days_to_keep)

                cursor.execute("""
                    DELETE FROM attendance_logs
                    WHERE date < %s
                """, (cutoff_date,))

                deleted = cursor.rowcount
                conn.commit()
                cursor.close()

                if deleted > 0:
                    logger.info(f"Cleaned {deleted} old records")
                return {"success": True, "deleted": deleted}

        except PostgresError as e:
            logger.error(f"Cleanup error: {e}")
            return {"success": False, "deleted": 0}


    def get_all_system_users(self) -> List[Dict]:
        """Retrieves all system users, including sensitive data (password hash) for admin review."""
        query = """
        SELECT id, username, full_name, email, role, password_hash
        FROM users
        ORDER BY id;
        """
        with self.get_conn_cursor(RealDictCursor) as (conn, cursor):
            cursor.execute(query)
            users = cursor.fetchall()
            return users


    def update_system_user(self, user_id: int, data: Dict):
        """Updates user details including username, password, full_name, email, and role."""

        # Filter allowed fields to prevent arbitrary updates
        allowed_fields = ['username', 'password', 'full_name', 'email', 'role']
        updates = {k: v for k, v in data.items() if k in allowed_fields and v is not None}

        if not updates:
            raise ValueError("No valid fields provided for update.")

        # Special handling for password - store as plain text (matching your current system)
        # Note: In production, you should hash passwords!
        if 'password' in updates:
            # Store password in password_hash column (as plain text in your current system)
            updates['password_hash'] = updates.pop('password')

        set_clauses = [f"{k} = %s" for k in updates.keys()]
        values = list(updates.values())
        values.append(user_id)

        query = f"""
        UPDATE users
        SET {', '.join(set_clauses)}
        WHERE id = %s;
        """

        with self.get_conn_cursor() as (conn, cursor):
            cursor.execute(query, values)

            # Check if any row was actually updated
            if cursor.rowcount == 0:
                raise ValueError(f"User with ID {user_id} not found")

            conn.commit()
            logger.info(f"User {user_id} updated successfully")



    def delete_system_user(self, user_id: int):
        """Deletes a system user by ID."""
        query = "DELETE FROM users WHERE id = %s;"
        with self.get_conn_cursor() as (conn, cursor):
            cursor.execute(query, (user_id,))
            conn.commit()

    def get_system_user_by_id(self, user_id: int) -> Optional[Dict]:
        """Retrieves a system user by ID, ensuring the role field is included."""
        query = """
        SELECT id, username, full_name, email, role
        FROM users
        WHERE id = %s;
        """
        # Use RealDictCursor to return results as a dictionary (Dict)
        with self.get_conn_cursor(RealDictCursor) as (conn, cursor):
            cursor.execute(query, (user_id,))
            user = cursor.fetchone()
            return user



    def get_user_id_by_session_id(self, session_id: str) -> Optional[int]:
        """Retrieves the user ID associated with a given session ID from the sessions table."""
        query = """
        SELECT user_id 
        FROM sessions 
        WHERE session_token = %s AND expires_at > NOW(); 
        -- FIX: Changed session_id to session_token
        """
        with self.get_conn_cursor() as (conn, cursor):
            cursor.execute(query, (session_id,))
            result = cursor.fetchone()
            return result[0] if result else None

# ============ AUTHENTICATION SERVICE ============

class AuthenticationService:
    """Production-grade authentication"""
    SESSION_COOKIE_NAME = "session_token"
    def __init__(self, db_service):
        self.db_service = db_service
        self.session_timeout = datetime.timedelta(hours=8)
        logger.info("Authentication service initialized")


    def authenticate_user(self, username: str, password: str) -> Optional[Dict]:
        try:
            with self.db_service.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT id, username, password_hash, full_name, email, role, is_active,
                           failed_attempts, locked_until
                    FROM users
                    WHERE username = %s
                """, (username,))

                user_data = cursor.fetchone()
                cursor.close()

                if not user_data:
                    logger.warning(f"Login attempt - user not found: {username}")
                    return None

                # Keep variable name as password_hash to match DB column
                (user_id, username, password_hash, full_name, email, role,
                 is_active, failed_attempts, locked_until) = user_data

                if not is_active:
                    logger.warning(f"Login attempt - inactive account: {username}")
                    return None

                if locked_until and locked_until > datetime.datetime.now():
                    logger.warning(f"Login attempt - account locked: {username}")
                    return None

                # Use bcrypt to verify password
                try:
                    # Handle both bcrypt hash and legacy plain text (optional fallback)
                    if not bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8')):
                         self._handle_failed_login(user_id)
                         logger.warning(f"Login attempt - invalid password: {username}")
                         return None
                except ValueError: 
                     # Fallback for legacy plain text passwords if necessary, or just fail
                     if password != password_hash:
                         self._handle_failed_login(user_id)
                         logger.warning(f"Login attempt - invalid password (legacy): {username}")
                         return None

                self._reset_failed_attempts(user_id)
                self._update_last_login(user_id)

                logger.info(f"User authenticated: {username}")
                return {
                    'id': user_id,
                    'username': username,
                    'full_name': full_name,
                    'email': email,
                    'role': role
                }

        except PostgresError as e:
            logger.error(f"Authentication error: {e}")
            return None



    def _handle_failed_login(self, user_id: int):
        """Handle failed login attempts with account locking"""
        try:
            with self.db_service.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE users
                    SET failed_attempts = failed_attempts + 1,
                        locked_until = CASE
                            WHEN failed_attempts >= 4 THEN NOW() + INTERVAL '30 minutes'
                            ELSE locked_until
                        END
                    WHERE id = %s
                """, (user_id,))
                conn.commit()
                cursor.close()
        except PostgresError as e:
            logger.error(f"Failed login handling error: {e}")


    def _reset_failed_attempts(self, user_id: int):
        """Reset failed login attempts after successful login"""
        try:
            with self.db_service.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE users
                    SET failed_attempts = 0, locked_until = NULL
                    WHERE id = %s
                """, (user_id,))
                conn.commit()
                cursor.close()
        except PostgresError as e:
            logger.error(f"Reset failed attempts error: {e}")


    def _update_last_login(self, user_id: int):
        """Update last login timestamp"""
        try:
            with self.db_service.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE users
                    SET last_login = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (user_id,))
                conn.commit()
                cursor.close()
        except PostgresError as e:
            logger.error(f"Update last login error: {e}")

    def create_session(self, user_id: int, username: str) -> str:
        """Create a new session for authenticated user"""
        try:
            session_token = secrets.token_urlsafe(32)
            # expires_at calculated in DB to avoid timezone mismatch
            with self.db_service.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO sessions (session_token, user_id, expires_at, created_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP + INTERVAL '8 hours', CURRENT_TIMESTAMP)
                """, (session_token, user_id))
                conn.commit()
                cursor.close()

            logger.info(f"Session created for user: {username}")
            return session_token

        except PostgresError as e:
            logger.error(f"Session creation error: {e}")
            return None

    def validate_session(self, session_token: str) -> Optional[Dict]:
        try:
            with self.db_service.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT s.user_id, u.username, u.full_name, u.email, u.role
                    FROM sessions s
                    JOIN users u ON s.user_id = u.id
                    WHERE s.session_token = %s 
                    AND s.is_active = TRUE 
                    AND u.is_active = TRUE
                    AND s.expires_at > CURRENT_TIMESTAMP
                """, (session_token,))

                result = cursor.fetchone()
                cursor.close()

                if not result:
                    # If not found (or expired/inactive), return None
                    return None

                user_id, username, full_name, email, role = result

                return {
                    'id': user_id,
                    'username': username,
                    'full_name': full_name,
                    'email': email,
                    'role': role
                }

        except PostgresError as e:
            logger.error(f"Session validation error: {e}")
            return None


    def delete_session(self, session_token: str):
        """Invalidate session (logout)"""
        try:
            with self.db_service.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE sessions
                    SET is_active = FALSE
                    WHERE session_token = %s
                """, (session_token,))
                conn.commit()
                cursor.close()
        except PostgresError as e:
            logger.error(f"Session deletion error: {e}")

    def cleanup_expired_sessions(self):
        """Clean up expired sessions"""
        try:
            with self.db_service.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    DELETE FROM sessions
                    WHERE expires_at < CURRENT_TIMESTAMP OR is_active = FALSE
                """)
                deleted = cursor.rowcount
                conn.commit()
                cursor.close()

                if deleted > 0:
                    logger.info(f"Cleaned up {deleted} expired sessions")
                return deleted
        except PostgresError as e:
            logger.error(f"Session cleanup error: {e}")
            return 0



    def create_user(self, username: str, password: str, full_name: str, email: str, role: str) -> dict:
        """Creates a new user with BCrypt hashed password"""
        try:
            with self.db_service.get_connection() as conn:
                cursor = conn.cursor()

                # Hash password before storing
                salt = bcrypt.gensalt(rounds=12)
                hashed_pw = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

                cursor.execute("""
                    INSERT INTO users (username, password_hash, full_name, email, role)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                """, (username, hashed_pw, full_name, email, role))

                user_id = cursor.fetchone()[0]
                conn.commit()
                cursor.close()
                logger.info(f"Admin created user: {username}")
                return {"success": True, "message": "User created", "user_id": user_id}

        except PostgresError as e:
            logger.error(f"Database error during user creation: {e}")
            return {"success": False, "message": str(e)}



    def get_user_from_session(self, request: Request) -> Optional[Dict]:
        """Retrieves user details from the session ID stored in the cookie."""
        session_id = request.cookies.get(self.SESSION_COOKIE_NAME)
        if not session_id:
            return None

        user_id = self.get_user_id_from_session(session_id)
        if user_id is None:
            return None

        user = self.db_service.get_system_user_by_id(user_id)
        return user


    def get_user_id_from_session(self, session_id: str) -> Optional[int]:
        """Retrieves the user_id from the session ID using the database service."""
        # Calls a new database method to check the session table
        return self.db_service.get_user_id_by_session_id(session_id)

# ============ FACE RECOGNITION SERVICE ============


class FaceRecognitionServiceFAISS:
    """Production Face Recognition with InsightFace and FAISS - FIXED FOR COSINE SIMILARITY"""

    def __init__(self):
        try:
            # --- MODIFICATION ---
            # DO NOT LOAD THE MODEL YET. We will load it manually after FAISS.
            self.model = None
            # --- END MODIFICATION ---

            self.face_map = {}

            # ✅ OPTIMIZED FOR POOR CAMERAS WITH MULTI-ANGLE VALIDATION
            self.recognition_threshold = 0.40  # Requires 40% confidence
            self.quality_threshold = 0.30  # Lenient on quality
            self.min_face_width = 50  # Accept small faces
            self.min_face_height = 50  # Accept small faces

            # ✅ FAISS INDEX FOR FAST COSINE SIMILARITY SEARCH
            self.faiss_index = None
            self.emp_id_map = []  # Maps FAISS index positions to emp_ids
            self.embeddings_cache = []  # Cache embeddings for index rebuilding
            self.last_reload = time.time()

            # We change this log since the model isn't loaded yet
            logger.info("✅ Face recognition service initialized (model not loaded yet)")
            logger.info(f"  Recognition threshold: {self.recognition_threshold}")
            logger.info(f"  Multi-angle validation: ENABLED")
            logger.info(f"  FAISS Index: Ready for initialization")

        except Exception as e:
            logger.critical(f"Face recognition init failed: {e}")
            raise


    def load_model(self):
        """Initializes the InsightFace model. Call this AFTER FAISS is loaded."""
        try:
            if self.model:
                logger.info("InsightFace model already loaded.")
                return

            # Allow CPU fallback if CUDA is not available
            providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']

            logger.info(f"Attempting to initialize InsightFace with: {providers}")

            self.model = insightface.app.FaceAnalysis(
                providers=providers,
                allowed_modules=['detection', 'recognition']
            )
            # ctx_id=0 tells InsightFace to use GPU device 0
            self.model.prepare(ctx_id=0, det_size=(320, 320), det_thresh=0.5)

            # Log the *actual* provider being used to confirm it worked
            session = self.model.models['detection'].session
            actual_provider = session.get_providers()
            logger.info(f"✅ InsightFace detection model is using: {actual_provider}")

            if 'recognition' in self.model.models:
                rec_session = self.model.models['recognition'].session
                rec_provider = rec_session.get_providers()
                logger.info(f"✅ InsightFace recognition model is using: {rec_provider}")

            if 'CUDAExecutionProvider' not in actual_provider:
                logger.error("="*50)
                logger.error("🚨 CRITICAL: CUDAExecutionProvider NOT FOUND.")
                logger.error("🚨 InsightFace has fallen back to CPU!")
                logger.error("="*50)

            logger.info("✅ InsightFace model loading complete.")

        except Exception as e:
            logger.critical(f"InsightFace model loading failed: {e}")
            raise


    def load_face_map(self, face_map: Dict[str, dict]):
        """Load face embeddings into FAISS index with COSINE SIMILARITY"""
        self.face_map = face_map
        self.embeddings_cache = []
        self.emp_id_map = []

        for emp_id, data in face_map.items():
            for emb in data['embeddings']:
                self.embeddings_cache.append(emb)
                self.emp_id_map.append(emp_id)

        if self.embeddings_cache:
            embeddings_array = np.array(self.embeddings_cache).astype(np.float32)

            # ✅ CRITICAL FIX: Normalize embeddings for cosine similarity
            faiss.normalize_L2(embeddings_array)

            # ✅ USE IndexFlatIP (Inner Product) for cosine similarity after normalization
            embedding_dim = embeddings_array.shape[1]

            # --- START GPU FAISS MODIFICATION ---
            
            # 1. Create a CPU index first
            index_cpu = faiss.IndexFlatIP(embedding_dim) # IP = Inner Product
            
            # 2. Check for GPU resources
            try:
                if hasattr(faiss, 'StandardGpuResources'):
                    logger.info("Initializing FAISS GPU resources...")
                    res = faiss.StandardGpuResources()
                    self.faiss_index = faiss.index_cpu_to_gpu(res, 0, index_cpu)
                    logger.info(f"   Index type: GPU Flat Inner Product (Cosine Similarity)")
                else:
                    self.faiss_index = index_cpu
                    logger.info(f"   Index type: CPU Flat Inner Product (Cosine Similarity)")
            except Exception as e:
                logger.warning(f"Failed to use GPU for FAISS, falling back to CPU: {e}")
                self.faiss_index = index_cpu
                logger.info(f"   Index type: CPU Flat Inner Product (Cosine Similarity)")
            
            # 3. Add the embeddings directly to the index
            self.faiss_index.add(embeddings_array)
        else:
            self.faiss_index = None
            logger.warning("⚠️ No embeddings to load - FAISS index is empty")


        self.last_reload = time.time()
        logger.info(f"Face map loaded: {len(face_map)} employees, {len(self.embeddings_cache)} embeddings")

    def should_reload_face_map(self, max_age_seconds: int = 300) -> bool:
        """Check if face map needs reloading"""
        return (time.time() - self.last_reload) > max_age_seconds

    def detect_faces(self, image: np.ndarray) -> List:
        """Detect faces in image"""
        # --- ADD THIS CHECK ---
        if not self.model:
            logger.warning("Model not loaded yet, skipping face detection.")
            return []
        # --- END CHECK ---
        try:
            faces = self.model.get(image)
            return faces
        except Exception as e:
            logger.error(f"Face detection error: {e}")
            return []

    def calculate_quality(self, image: np.ndarray, face_bbox: np.ndarray) -> dict:
        """Calculate face quality score"""
        try:
            bbox = face_bbox.astype(int)
            face_width = bbox[2] - bbox[0]
            face_height = bbox[3] - bbox[1]
            face_area = face_width * face_height
            img_area = image.shape[0] * image.shape[1]

            size_ratio = face_area / img_area
            size_score = min(size_ratio / 0.05, 1.0)

            face_region = image[bbox[1]:bbox[3], bbox[0]:bbox[2]]
            if face_region.size > 0:
                gray = cv2.cvtColor(face_region, cv2.COLOR_BGR2GRAY)
                sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
                sharpness_score = min(sharpness / 100, 1.0)
            else:
                sharpness_score = 0

            brightness = np.mean(face_region)
            brightness_score = 1.0 - abs(brightness - 127) / 127

            quality = (size_score * 0.4 + sharpness_score * 0.4 + brightness_score * 0.2)

            return {
                'quality': quality,
                'size_ratio': size_ratio,
                'sharpness': sharpness_score,
                'brightness': brightness_score,
                'face_width': face_width,
                'face_height': face_height
            }
        except Exception as e:
            logger.error(f"Quality calc error: {e}")
            return {'quality': 0, 'size_ratio': 0, 'sharpness': 0, 'brightness': 0,
                    'face_width': 0, 'face_height': 0}

    def recognize_face(self, face_embedding: np.ndarray) -> Tuple[Optional[str], float]:
        """
        ✅ FAISS-BASED RECOGNITION WITH COSINE SIMILARITY + MULTI-ANGLE VALIDATION
        Requires 2+ angles to match same person - prevents false recognitions

        FAISS IndexFlatIP returns cosine similarities (after normalization)
        Higher similarity = better match (same as sklearn's cosine_similarity)
        Range: [-1, 1], but normalized embeddings give [0, 1]
        """
        if self.faiss_index is None or len(self.emp_id_map) == 0:
            logger.warning("FAISS index not initialized")
            return None, 0.0

        try:
            # ✅ CRITICAL: Normalize query embedding for cosine similarity
            query_embedding = face_embedding.astype(np.float32).reshape(1, -1)
            faiss.normalize_L2(query_embedding)  # Normalize for cosine similarity

            # Search for top 20 nearest neighbors (to cover all 8 angles per person)
            k = min(20, len(self.embeddings_cache))
            similarities, indices = self.faiss_index.search(query_embedding, k)

            # ✅ FAISS IndexFlatIP returns similarities directly (not distances!)
            similarities = similarities[0]  # Get first (and only) query's results
            indices = indices[0]

            logger.debug(f"🔍 Top 5 similarities: {similarities[:5]}")

            # Group by employee
            emp_scores = defaultdict(list)
            for idx, sim in zip(indices, similarities):
                emp_id = self.emp_id_map[idx]
                emp_scores[emp_id].append(sim)

            best_match = None
            best_confidence = 0.0

            for emp_id, sims in emp_scores.items():
                # Sort all angles from best to worst
                sims_sorted = sorted(sims, reverse=True)

                # ✅ MULTI-ANGLE CHECK
                if len(sims_sorted) >= 2:
                    top_sim = sims_sorted[0]  # Best matching angle
                    second_sim = sims_sorted[1]  # Second best matching angle

                    # If top 2 angles are close = likely real person
                    if (top_sim - second_sim) <= 0.08:  # Both similar
                        confidence = (top_sim + second_sim) / 2  # Average of top 2
                    else:
                        # Only 1 angle matches = suspicious, penalize
                        confidence = top_sim * 0.6  # Reduce confidence
                else:
                    confidence = sims_sorted[0] if sims_sorted else 0

                if confidence > best_confidence:
                    best_confidence = confidence
                    best_match = emp_id

            # Threshold
            if best_confidence >= self.recognition_threshold:
                logger.debug(f"✅ Match found: {best_match} (confidence: {best_confidence:.2f})")
                return best_match, best_confidence

            logger.debug(
                f"❌ No match (best confidence: {best_confidence:.2f} < threshold: {self.recognition_threshold})")
            return None, best_confidence

        except Exception as e:
            logger.error(f"Recognition error: {e}", exc_info=True)
            return None, 0.0

    def extract_embedding(self, image: np.ndarray) -> Tuple[Optional[np.ndarray], dict]:
        """Extract face embedding from image"""
        try:
            faces = self.detect_faces(image)

            if len(faces) == 0:
                return None, {"error": "No face detected"}

            if len(faces) > 1:
                return None, {"error": "Multiple faces detected"}

            face = faces[0]
            quality_info = self.calculate_quality(image, face.bbox)

            if quality_info['quality'] < self.quality_threshold:
                return None, {"error": "Poor quality", "quality": quality_info['quality']}

            if quality_info['size_ratio'] < 0.01:
                return None, {"error": "Face too small"}

            if quality_info['face_width'] < self.min_face_width or quality_info['face_height'] < self.min_face_height:
                return None, {"error": "Face resolution too low"}

            return face.embedding, quality_info

        except Exception as e:
            logger.error(f"Extract embedding error: {e}")
            return None, {"error": str(e)}

    def save_index_to_disk(self, filepath: str = "faiss_index.bin"):
        """Save FAISS index to disk for fast loading"""
        try:
            if self.faiss_index is not None:
                faiss.write_index(self.faiss_index, filepath)
                logger.info(f"✅ FAISS index saved to {filepath}")
                return True
        except Exception as e:
            logger.error(f"Error saving FAISS index: {e}")
            return False

    def load_index_from_disk(self, filepath: str = "faiss_index.bin"):
        """Load FAISS index from disk"""
        try:
            if os.path.exists(filepath):
                self.faiss_index = faiss.read_index(filepath)
                logger.info(f"✅ FAISS index loaded from {filepath}")
                return True
        except Exception as e:
            logger.error(f"Error loading FAISS index: {e}")
        return False

# ============ CAMERA SERVICE - UPDATED FACE DETECTION THRESHOLD ============

class CameraService:
    """Camera processing with UPDATE-ONLY attendance"""
    
    def __init__(self, camera_configs: dict, face_service: FaceRecognitionServiceFAISS, ws_manager: WebSocketManager = None):
        self.cameras = camera_configs
        self.face_service = face_service
        self.ws_manager = ws_manager
        self.stats = {'total_faces': 0, 'recognized': 0, 'unknown': 0}
        logger.info("Camera service initialized with UPDATE-ONLY mode")
    
    async def process_camera(self, camera_type: str, db_service):
        """Process camera stream with UPDATE-ONLY attendance"""
        camera = self.cameras[camera_type]
        cap = None
        frame_count = 0
        reconnect_attempts = 0
        max_reconnect = 5
        
        # Skip more frames to reduce processing
        FRAME_SKIP = 3  # Process every 5th frame instead of every 2nd
        
        while self.ws_manager and self.ws_manager.is_monitoring and reconnect_attempts < max_reconnect:
            try:
                cap = cv2.VideoCapture(camera['rtsp_url'], cv2.CAP_FFMPEG)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                
                for _ in range(20):
                    cap.grab()
                
                logger.info(f"Camera {camera_type} started")
                reconnect_attempts = 0
                
                while self.ws_manager and self.ws_manager.is_monitoring:
                    if self.face_service.should_reload_face_map():
                        face_map = db_service.load_all_embeddings()
                        self.face_service.load_face_map(face_map)
                    
                    # SKIP MORE FRAMES
                    if frame_count % FRAME_SKIP != 0:
                        cap.grab()
                        frame_count += 1
                        await asyncio.sleep(0.030)
                        continue
                    
                    ret, frame = cap.read()
                    if not ret:
                        logger.warning(f"Frame read failed: {camera_type}")
                        await asyncio.sleep(0.5)
                        break
                    
                    frame_count += 1
                   
                    from pytz import timezone
                    IST = timezone('Asia/Kolkata')
                    timestamp = datetime.datetime.now(IST)  # Get IST time directly

                    # Reduce resolution for faster processing
                    frame = cv2.resize(frame, (640, 480))
                    frame = self._enhance_frame(frame)
                    faces = self.face_service.detect_faces(frame)
                    
                    self.stats['total_faces'] += len(faces)
                    
                    # FIXED: Increased detection threshold from 0.65 to 0.85
                    for face in faces[:10]:
                        if face.det_score < 0.35:  # ✅ CHANGED (was 0.30, now 0.35)
                            continue
                        
                        # ✅ Uses new multi-angle validation function
                        emp_id, confidence = self.face_service.recognize_face(face.embedding)
                        
                        # ✅ Threshold: 0.40 with multi-angle validation
                        if emp_id and confidence >= 0.40:
                            self.stats['recognized'] += 1
                            
                            result = db_service.log_attendance_update_only(
                                emp_id, 
                                camera['purpose'],
                                camera['id'], 
                                float(confidence), 
                                timestamp
                            )
                            
                            if result['success'] and result.get('action') != 'skipped' and self.ws_manager:
                                await self.ws_manager.broadcast({
                                    'type': 'attendance',
                                    'emp_id': emp_id,
                                    'name': self.face_service.face_map.get(emp_id, {}).get('name', 'Unknown'),
                                    'event_type': camera['purpose'],
                                    'confidence': float(confidence),
                                    'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                                    'action': result.get('action', 'logged')
                                })
                        else:
                            self.stats['unknown'] += 1


                    await self.send_frame(frame, faces, camera_type)
                    await asyncio.sleep(0.033)
                    
            except Exception as e:
                logger.error(f"Camera {camera_type} error: {e}")
                reconnect_attempts += 1
                await asyncio.sleep(2 ** reconnect_attempts)
            finally:
                if cap:
                    cap.release()
        
        logger.warning(f"Camera {camera_type} stopped")

    def _enhance_frame(self, frame: np.ndarray) -> np.ndarray:
        """Enhance frame for better processing"""
        try:
            height, width = frame.shape[:2]
            if width > 1280:
                scale = 1280 / width
                frame = cv2.resize(frame, (int(width * scale), int(height * scale)))
            frame = cv2.convertScaleAbs(frame, alpha=1.1, beta=5)
            return frame
        except:
            return frame
    


    async def send_frame(self, frame: np.ndarray, faces: List, camera_type: str):
        """Send processed frame with VISIBLE rectangles on ALL detected faces"""
        try:
            # Make a copy to draw on
            display_frame = frame.copy()
            
            #logger.info(f"[{camera_type}] send_frame called with {len(faces)} faces")
            
            # Draw rectangles on EVERY face regardless of score
            for idx, face in enumerate(faces):
                #logger.info(f"[{camera_type}] Face {idx}: det_score={face.det_score}")
                
                bbox = face.bbox.astype(int)
                x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
                
                # ALWAYS recognize - don't skip any faces
                emp_id, confidence = self.face_service.recognize_face(face.embedding)
                
                # Determine color
                if emp_id and confidence >= self.face_service.recognition_threshold:
                    name = self.face_service.face_map.get(emp_id, {}).get('name', 'Unknown')
                    color = (0, 255, 0)  # Green
                    text = f"{name} {confidence:.0%}"
                else:
                    color = (0, 0, 255)  # Red
                    text = f"Unknown {confidence:.0%}"
                
                # Draw thick rectangle - VERY VISIBLE
                cv2.rectangle(display_frame, (x1, y1), (x2, y2), color, 1)
                
                # Draw text with background for visibility
                font = cv2.FONT_HERSHEY_SIMPLEX
                font_scale = 0.8
                thickness = 1
                
                # Get text size
                text_size = cv2.getTextSize(text, font, font_scale, thickness)[0]
                
                # Draw background rectangle for text
                cv2.rectangle(display_frame, 
                             (x1, y1 - text_size[1] - 3),
                             (x1 + text_size[0] + 3, y1),
                             color, -1)
                
                # Draw text
                cv2.putText(display_frame, text, (x1 + 2, y1 - 2),
                           font, font_scale, (255, 255, 255), thickness)
                
                #logger.info(f"[{camera_type}] Drew rectangle for: {text}")
            
            # Add header info
            header_text = f"{camera_type.upper()} - {len(faces)} Face(s) Detected"
            cv2.putText(display_frame, header_text, (20, 40),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1)
            
            # Resize for transmission
            small_frame = cv2.resize(display_frame, (640, 480))
            
            # Encode
            _, buffer = cv2.imencode('.jpg', small_frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
            frame_base64 = base64.b64encode(buffer).decode('utf-8')
            
            if self.ws_manager:
                await self.ws_manager.broadcast({
                    'type': 'frame',
                    'camera': camera_type,
                    'image': frame_base64,
                    'faces_count': len(faces)
                })
            
        except Exception as e:
            logger.error(f"Send frame error for {camera_type}: {e}", exc_info=True)

    def get_stats(self) -> dict:
        """Get camera statistics"""
        return self.stats.copy()

