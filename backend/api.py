# ============================================================================
# ENHANCED api.py - WITH ALL IMPROVEMENTS
# ============================================================================

"""
Production API with:
- Database Connection Pooling
- Pagination for Large Datasets
- Race Condition Protection (asyncio.Lock)
- Multi-User Session Tracking
- Proper Export Handling
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form, HTTPException, Query, BackgroundTasks, Depends
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional
import cv2
import numpy as np
import datetime
import asyncio
import json
import os
import logging
from logging.handlers import RotatingFileHandler
import time
import uuid
import socket
import threading
from urllib.parse import urlparse
import tempfile
import re
import bcrypt
from admin import validate_email, validate_password, hash_password
import schedule


from services import (
    PooledDatabaseService, 
    FaceRecognitionServiceFAISS,
    CameraService, 
    AuthenticationService,
    WebSocketManager
)
from config import settings

# ============ LOGGING SETUP ============
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        RotatingFileHandler('logs/app.log', maxBytes=10485760, backupCount=10),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============ CAMERA URL CONFIGURATION ============

CAMERA_URL_FILE = "camera_urls.json"

def load_camera_urls():
    try:
        if os.path.exists(CAMERA_URL_FILE):
            with open(CAMERA_URL_FILE, 'r') as f:
                data = json.load(f)
                return data.get('entry_url', ''), data.get('exit_url', '')
    except Exception as e:
        logger.error(f"Error loading camera URLs: {e}")
    return '', ''

def save_camera_urls(entry_url: str, exit_url: str):
    try:
        with open(CAMERA_URL_FILE, 'w') as f:
            json.dump({'entry_url': entry_url, 'exit_url': exit_url}, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error saving camera URLs: {e}")
        return False

def get_camera_config():
    entry_url, exit_url = load_camera_urls()
    
    return {
        'entry': {'id': 'entry_camera', 'rtsp_url': entry_url, 'purpose': 'IN'},
        'exit': {'id': 'exit_camera', 'rtsp_url': exit_url, 'purpose': 'OUT'}
    }



# ============ AUTHENTICATION MIDDLEWARE ============

class AuthMiddleware(BaseHTTPMiddleware):
    EXCLUDED_PATHS = {'/login', '/api/login', '/api/health', '/docs', '/redoc', '/openapi.json', '/favicon.ico'}
    
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        if path.startswith('/static/') or any(path.startswith(excluded) for excluded in self.EXCLUDED_PATHS):
            return await call_next(request)
        
        session_token = request.cookies.get("session_token")
        
        if not session_token:
            if path != '/api/auth/check':
                logger.warning(f"Unauthorized access attempt to {path}")
                return JSONResponse(status_code=401, content={"detail": "Authentication required"})
        
        try:
            auth_service = request.app.state.auth_service
            user = auth_service.validate_session(session_token)
            
            if not user:
                logger.warning(f"Invalid session for {path}")
                return JSONResponse(status_code=401, content={"detail": "Session expired"})
            
            request.state.user = user
            
        except Exception as e:
            logger.error(f"Auth middleware error: {e}")
            return JSONResponse(status_code=500, content={"detail": "Authentication error"})
        
        response = await call_next(request)
        return response


# ============ APP INITIALIZATION ============

app = FastAPI(
    title="CCTV Attendance System - Production",
    description="UPDATE-ONLY attendance with pooling, pagination, and multi-user support",
    version="5.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(AuthMiddleware)

REQUIRED_DIRS = ["uploads", "exports", "logs"]
for directory in REQUIRED_DIRS:
    os.makedirs(directory, exist_ok=True)

DB_CONFIG = {
    'host': settings.DB_HOST,
    'port': settings.DB_PORT,
    'user': settings.DB_USER,
    'password': settings.DB_PASSWORD,
    'database': settings.DB_NAME
}


CAMERA_CONFIG = get_camera_config()

# Initialize services
try:
    db_service = PooledDatabaseService(DB_CONFIG)  # POOLED DATABASE
    auth_service = AuthenticationService(db_service)
    face_service = FaceRecognitionServiceFAISS()
    ws_manager = WebSocketManager()  # WebSocket manager with locks
    camera_service = CameraService(CAMERA_CONFIG, face_service, ws_manager)
    logger.info("All services initialized successfully")
except Exception as e:
    logger.critical(f"Service initialization failed: {e}")
    raise

# Track ongoing exports
export_status = {}

# ============ HELPER FUNCTIONS ============

def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0]
    return request.client.host if request.client else "unknown"

def log_audit(user_id: Optional[int], action: str, details: str, request: Request):
    try:
        ip_address = get_client_ip(request)
        user_agent = request.headers.get("User-Agent", "")
        
        with db_service.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO audit_log (user_id, action, details, ip_address, user_agent)
                VALUES (%s, %s, %s, %s, %s)
            """, (user_id, action, details, ip_address, user_agent))
            conn.commit()
            cursor.close()
    except Exception as e:
        logger.error(f"Audit log error: {e}")

def get_current_user(request: Request):
    return getattr(request.state, 'user', None)

def require_auth(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user

def require_admin(request: Request):
    user = require_auth(request)
    if user['role'] != 'admin':
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

# ============ AUTHENTICATION ROUTES ============



@app.post("/api/login", tags=["Authentication"])
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    user = auth_service.authenticate_user(username, password)
    
    if not user:
        log_audit(None, "login_failed", f"Failed login: {username}", request)
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    session_token = auth_service.create_session(user['id'], user['username'])
    if not session_token:
        raise HTTPException(status_code=500, detail="Session creation failed")
    
    log_audit(user['id'], "login_success", f"User logged in: {username}", request)
    
    response = JSONResponse(content={"success": True, "user": user})
    response.set_cookie(key="session_token", value=session_token, httponly=True, 
                       max_age=3600 * 8, samesite="lax", secure=False)
    
    logger.info(f"Login successful: {username}")
    return response

@app.get("/api/logout", tags=["Authentication"])
async def logout(request: Request):
    session_token = request.cookies.get("session_token")
    user = get_current_user(request)
    
    if session_token:
        auth_service.delete_session(session_token)
    
    if user:
        log_audit(user['id'], "logout", f"User logged out: {user['username']}", request)
    
    response = JSONResponse(content={"success": True, "message": "Logged out"})
    response.delete_cookie("session_token")
    return response

@app.get("/api/auth/check", tags=["Authentication"])
async def check_auth(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    return {
        "authenticated": True,
        "user": {
            "username": user['username'],
            "full_name": user['full_name'],
            "role": user['role']
        }
    }

# ============ PROTECTED PAGES ============



# ============ CAMERA URL MANAGEMENT ============

@app.get("/api/camera/urls", tags=["Camera Management"])
async def get_camera_urls(request: Request):
    require_auth(request)
    entry_url, exit_url = load_camera_urls()
    if not entry_url:
        entry_url = CAMERA_CONFIG['entry']['rtsp_url']
    if not exit_url:
        exit_url = CAMERA_CONFIG['exit']['rtsp_url']
    
    return {"entry_url": entry_url, "exit_url": exit_url}

@app.post("/api/camera/urls", tags=["Camera Management"])
async def update_camera_urls(request: Request, data: dict):
    user = require_admin(request)  # ADMIN ONLY
    
    entry_url = data.get('entry_url', '').strip()
    exit_url = data.get('exit_url', '').strip()
    
    if not entry_url or not exit_url:
        return {"success": False, "message": "Both URLs required"}
    
    if not entry_url.startswith('rtsp://') or not exit_url.startswith('rtsp://'):
        return {"success": False, "message": "URLs must start with rtsp://"}
    
    if save_camera_urls(entry_url, exit_url):
        global CAMERA_CONFIG
        CAMERA_CONFIG = get_camera_config()
        camera_service.cameras = CAMERA_CONFIG
        
        log_audit(user['id'], "update_camera_urls", "Updated camera URLs", request)
        logger.info(f"Camera URLs updated")
        
        return {"success": True, "message": "Camera URLs saved. Restart cameras to apply."}
    else:
        return {"success": False, "message": "Failed to save URLs"}

# ============ WEBSOCKET WITH LOCKS & USER TRACKING ============

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint with multi-user feed sharing and frame caching"""
    
    session_token = websocket.cookies.get("session_token")
    user_id = "anonymous"
    user_name = "Unknown"
    user_role = "user"
    
    try:
        if session_token:
            user = auth_service.validate_session(session_token)
            if user:
                user_id = user['id']
                user_name = user['username']
                user_role = user.get('role', 'user')
    except:
        pass
    
    await ws_manager.connect(websocket, str(user_id), user_name, user_role)
    
    logger.info(f"🟢 User {user_name} connected. Monitoring: {ws_manager.is_monitoring}")
    
    # 🟢 NEW: Send cached frames automatically on connection
    if ws_manager.is_monitoring:
        logger.info(f"📦 Sending cached frames to {user_name}")
        await ws_manager.send_cached_frames(websocket)
        
        # 🟢 NEW: Send connection status
        await websocket.send_json({
            'type': 'status',
            'camera_status': 'already_running',
            'started_by': ws_manager.started_by,
            'message': f'Cameras already running (started by {ws_manager.started_by})',
            'active_users': len(ws_manager.active_connections)
        })
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get('action') == 'start':
                async with ws_manager.start_lock:
                    if not ws_manager.is_monitoring:
                        ws_manager.is_monitoring = True
                        ws_manager.started_by = user_name
                        
                        logger.info(f"🎬 Cameras starting by {user_name}")
                        
                        task1 = asyncio.create_task(camera_service.process_camera('entry', db_service))
                        task2 = asyncio.create_task(camera_service.process_camera('exit', db_service))
                        ws_manager.monitor_tasks = [task1, task2]
                        
                        await ws_manager.broadcast({
                            'type': 'status',
                            'camera_status': 'started',
                            'started_by': user_name,
                            'active_users': len(ws_manager.active_connections),
                            'message': f'Cameras started by {user_name}'
                        })
                    else:
                        logger.info(f"ℹ️ User {user_name} tried to start (already running)")
                        await websocket.send_json({
                            'type': 'status',
                            'camera_status': 'already_running',
                            'started_by': ws_manager.started_by,
                            'message': f'Cameras already running (started by {ws_manager.started_by})',
                            'active_users': len(ws_manager.active_connections)
                        })
                        
                        # 🟢 NEW: Send cached frames
                        await ws_manager.send_cached_frames(websocket)
            
            elif message.get('action') == 'stop':
                if user_role == 'admin' or user_name == ws_manager.started_by:
                    ws_manager.is_monitoring = False
                    logger.info(f"⏹️ Cameras stopped by {user_name}")
                    
                    await ws_manager.broadcast({
                        'type': 'status',
                        'camera_status': 'stopped',
                        'stopped_by': user_name,
                        'message': f'Cameras stopped by {user_name}'
                    })
                else:
                    await websocket.send_json({
                        'type': 'error',
                        'message': f'Only {ws_manager.started_by} or admin can stop cameras'
                    })
            
            # 🟢 NEW: Handle frame cache request
            elif message.get('action') == 'get_cached_frames':
                logger.info(f"📦 User {user_name} requesting cached frames")
                await ws_manager.send_cached_frames(websocket)
            
            elif message.get('action') == 'stats':
                stats = camera_service.get_stats()
                await websocket.send_json({
                    'type': 'stats',
                    'data': stats,
                    'active_users': len(ws_manager.active_connections),
                    'started_by': ws_manager.started_by if ws_manager.is_monitoring else None
                })
    
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, user_id)
        logger.info(f"🔌 User {user_name} disconnected. Remaining: {len(ws_manager.active_connections)}")
    except Exception as e:
        logger.error(f"❌ WebSocket error for {user_name}: {e}")
        ws_manager.disconnect(websocket, user_id)

# ============ API ROUTES ============

@app.post("/api/create-employee", tags=["Employee Management"])
async def create_employee(request: Request, data: dict):
    user = require_auth(request)
    emp_id = data.get('emp_id', '').strip()
    name = data.get('name', '').strip()
    department = data.get('department', '').strip()
    position = data.get('position', '').strip()
    
    if not emp_id or not name:
        return {"success": False, "message": "Employee ID and Name required"}
    
    result = db_service.create_employee(emp_id, name, department, position)
    if result['success']:
        log_audit(user['id'], "create_employee", f"Created: {emp_id}", request)
    
    return result


@app.get("/api/employees/list", tags=["Employee Management"])
async def get_employees(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500)  # ✅ NEW: Default 100, Max 500
):
    require_auth(request)
    cache_key = int(time.time())
    all_employees = db_service.get_all_employees(cache_key)

    total_employees = len(all_employees)
    paginated = all_employees[skip:skip + limit]

    return {
        "employees": paginated,
        "pagination": {
            "skip": skip,
            "limit": limit,
            "total": total_employees,
            "pages": (total_employees + limit - 1) // limit,
            "current_page": (skip // limit) + 1
        },
        "stats": {
            "total": total_employees,
            "complete": sum(1 for e in all_employees if e['face_count'] >= 6),
            "incomplete": sum(1 for e in all_employees if 0 < e['face_count'] < 6),
            "no_faces": sum(1 for e in all_employees if e['face_count'] == 0)
        }
    }


@app.put("/api/employee/{emp_id}", tags=["Employee Management"])
async def update_employee(request: Request, emp_id: str, data: dict):
    user = require_auth(request)
    result = db_service.update_employee(emp_id, data.get('name'), data.get('department'), data.get('position'))
    
    if result['success']:
        face_map = db_service.load_all_embeddings()
        face_service.load_face_map(face_map)
        log_audit(user['id'], "update_employee", f"Updated: {emp_id}", request)
    
    return result

@app.delete("/api/employee/{emp_id}", tags=["Employee Management"])
async def delete_employee(request: Request, emp_id: str):
    user = require_auth(request)
    result = db_service.delete_employee(emp_id)
    
    if result['success']:
        face_map = db_service.load_all_embeddings()
        face_service.load_face_map(face_map)
        log_audit(user['id'], "delete_employee", f"Deleted: {emp_id}", request)
    
    return result

@app.post("/api/capture-face", tags=["Face Registration"])
async def capture_face(request: Request, image: UploadFile = File(...), angle: str = Form(...), emp_id: str = Form(...)):
    require_auth(request)
    
    image_data = await image.read()
    nparr = np.frombuffer(image_data, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if img is None:
        return {"success": False, "message": "Invalid image"}
    
    embedding, info = face_service.extract_embedding(img)
    if embedding is None:
        return {"success": False, "message": info.get('error', 'Failed to extract face')}
    
    result = db_service.save_face_embedding(emp_id, embedding, angle, info['quality'])
    return result

@app.post("/api/finalize-registration", tags=["Face Registration"])
async def finalize_registration(request: Request, data: dict):
    user = require_auth(request)
    emp_id = data.get('emp_id')
    captured_angles = data.get('captured_angles', [])
    
    if len(captured_angles) < 6:
        return {"success": False, "message": "Need at least 6 angles"}
    
    face_map = db_service.load_all_embeddings()
    face_service.load_face_map(face_map)
    
    if emp_id in face_service.face_map:
        log_audit(user['id'], "finalize_registration", f"Finalized: {emp_id}", request)
        return {"success": True, "message": "Registration complete"}
    
    return {"success": False, "message": "Failed to load face data"}

@app.get("/api/attendance/summary", tags=["Attendance"])
async def get_attendance_summary(
    request: Request,
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    emp_id: Optional[str] = Query(None)
):
    require_auth(request)
    
    if not from_date or not to_date:
        today = datetime.date.today()
        to_date = str(today)
        from_date = str(today - datetime.timedelta(days=7))
    
    all_records = db_service.get_attendance_summary(from_date, to_date, limit=50000)
    
    if emp_id:
        all_records = [r for r in all_records if r['emp_id'] == emp_id]
    
    total_records = len(all_records)
    paginated_records = all_records[skip:skip + limit]
    
    return {
        "records": paginated_records,
        "pagination": {
            "skip": skip,
            "limit": limit,
            "total": total_records,
            "pages": (total_records + limit - 1) // limit,
            "current_page": (skip // limit) + 1
        },
        "stats": {
            "total_records": total_records,
            "unique_employees": len(set(r['emp_id'] for r in all_records)),
            "total_days": len(set(r['date'] for r in all_records)),
            "date_range": f"{from_date} to {to_date}"
        }
    }


async def generate_excel_with_tracking(records, filepath, export_id):
    """Generate Excel file"""
    try:
        import pandas as pd
        import os

        excel_data = [{
            'Date': r['date'],
            'Employee ID': r['emp_id'],
            'Name': r['name'],
            'Department': r['department'],
            'First IN': r['first_in'] or '-',
            'Last OUT': r['last_out'] or '-',
            'Duration': r['duration'] or '-'
        } for r in records]

        df = pd.DataFrame(excel_data)
        df.to_excel(filepath, index=False, engine='openpyxl')
        logger.info(f"Export completed: {filepath}")

    except Exception as e:
        logger.error(f"Export failed: {e}")


# Replace this in api.py

@app.get("/api/attendance/export", tags=["Attendance"])
async def export_by_date_range(
    request: Request,
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None)
):
    user = require_auth(request)
    
    if not from_date or not to_date:
        today = datetime.date.today()
        to_date = str(today)
        from_date = str(today - datetime.timedelta(days=7))
    
    try:
        datetime.datetime.strptime(from_date, '%Y-%m-%d')
        datetime.datetime.strptime(to_date, '%Y-%m-%d')
    except ValueError:
        return {"success": False, "message": "Invalid date format. Use YYYY-MM-DD"}
    
    # Get records (can be empty)
    records = db_service.get_attendance_summary(from_date, to_date)
    
    filename = f"attendance_{from_date}_to_{to_date}.xlsx"
    filepath = f"exports/{filename}"
    
    try:
        import pandas as pd
        
        # Always create with headers, even if no records
        if records:
            excel_data = [{
                'Date': r['date'],
                'Employee ID': r['emp_id'],
                'Name': r['name'],
                'Department': r['department'],
                'First IN': r['first_in'] or '-',
                'Last OUT': r['last_out'] or '-',
                'Duration': r['duration'] or '-'
            } for r in records]
            df = pd.DataFrame(excel_data)
        else:
            # Create empty DataFrame with headers
            df = pd.DataFrame(columns=[
                'Date', 
                'Employee ID', 
                'Name', 
                'Department', 
                'First IN', 
                'Last OUT', 
                'Duration'
            ])
        
        # Ensure exports directory exists
        os.makedirs("exports", exist_ok=True)
        
        # Write to Excel
        df.to_excel(filepath, index=False, engine='openpyxl')
        
        log_audit(user['id'], "export_attendance", f"Exported: {from_date} to {to_date} ({len(records)} records)", request)
        logger.info(f"Export file created: {filepath} - {len(records)} records")
        
        # Return file for download
        return FileResponse(
            filepath,
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            filename=filename,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        logger.error(f"Export error: {e}")
        return {"success": False, "message": f"Export failed: {str(e)}"}

@app.get("/api/attendance/export-status/{export_id}", tags=["Attendance"])
async def get_export_status(request: Request, export_id: str):
    require_auth(request)
    status = export_status.get(export_id, {"status": "not_found"})
    return status

@app.get("/api/system/stats", tags=["System"])
async def get_system_stats(request: Request):
    require_auth(request)
    
    return {
        "camera_stats": camera_service.get_stats(),
        "is_monitoring": ws_manager.is_monitoring,
        "active_users": len(ws_manager.active_connections),
        "started_by": ws_manager.started_by if ws_manager.is_monitoring else None,
        "face_map_size": len(face_service.face_map),
        "total_embeddings": len(face_service.flat_embeddings),
        "timestamp": datetime.datetime.now().isoformat()
    }

@app.post("/api/system/cleanup", tags=["System"])
async def cleanup_old_logs(request: Request, days: int = Query(365, ge=30)):
    user = require_admin(request)
    result = db_service.cleanup_old_logs(days)
    log_audit(user['id'], "cleanup_logs", f"Cleaned {result.get('deleted', 0)} records", request)
    return result

@app.get("/api/health", tags=["System"])
async def health_check():
    return {"status": "healthy", "timestamp": datetime.datetime.now().isoformat()}



# Add this endpoint in api.py (after other endpoints)

@app.get("/api/attendance/stats/today", tags=["Attendance"])
async def get_today_stats(request: Request):
    """Get today's attendance statistics from database"""
    require_auth(request)

    try:
        today = datetime.date.today()

        with db_service.get_connection() as conn:
            cursor = conn.cursor()

            # Get total IN events today
            cursor.execute("""
                SELECT COUNT(*) as total_in
                FROM attendance_logs
                WHERE date = %s AND first_in IS NOT NULL
            """, (today,))
            result_in = cursor.fetchone()
            total_in = result_in[0] if result_in else 0

            # Get total OUT events today
            cursor.execute("""
                SELECT COUNT(*) as total_out
                FROM attendance_logs
                WHERE date = %s AND last_out IS NOT NULL
            """, (today,))
            result_out = cursor.fetchone()
            total_out = result_out[0] if result_out else 0

            # Get total unique employees who came today
            cursor.execute("""
                SELECT COUNT(DISTINCT emp_id) as unique_employees
                FROM attendance_logs
                WHERE date = %s
            """, (today,))
            result_unique = cursor.fetchone()
            unique_employees = result_unique[0] if result_unique else 0

            cursor.close()

            return {
                "success": True,
                "date": str(today),
                "total_in": total_in,
                "total_out": total_out,
                "unique_employees": unique_employees,
                "timestamp": datetime.datetime.now().isoformat()
            }

    except Exception as e:
        logger.error(f"Error getting attendance stats: {e}")
        return {
            "success": False,
            "message": str(e),
            "total_in": 0,
            "total_out": 0,
            "unique_employees": 0
        }


# ============ CAMERA CONNECTION TEST ============

# Add this to your api.py - Replace the old test_camera_connection endpoint

# Add this to your api.py - Replace the old test_camera_connection endpoint


async def validate_rtsp_stream(rtsp_url: str, timeout: int = 5) -> dict:
    """
    Actually test if RTSP stream works (Method 2)
    Tests: Connection + Frame Reading
    """
    result_container = {'result': None}
    
    def rtsp_test_worker():
        try:
            # Parse URL to get host and port for initial connection test
            parsed = urlparse(rtsp_url)
            host = parsed.hostname
            port = parsed.port or 554
            
            if not host:
                result_container['result'] = {
                    "connected": False,
                    "status": "Invalid URL",
                    "message": "Cannot parse RTSP URL"
                }
                return
            
            # Step 1: Test socket connection (ping)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            
            try:
                sock.connect((host, port))
                sock.close()
            except socket.timeout:
                result_container['result'] = {
                    "connected": False,
                    "status": "Timeout",
                    "message": "No response in 2 seconds - Camera offline"
                }
                return
            except Exception as e:
                result_container['result'] = {
                    "connected": False,
                    "status": "Error",
                    "message": f"Cannot reach camera: {str(e)[:40]}"
                }
                return
            
            # Step 2: Actual RTSP stream test (try to read a frame)
            try:
                cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                
                # Try to read a frame with timeout
                ret = False
                for attempt in range(3):
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        break
                
                cap.release()
                
                if ret and frame is not None:
                    # SUCCESS: Stream is working
                    result_container['result'] = {
                        "connected": True,
                        "status": "Connected",
                        "message": "Stream is working and readable"
                    }
                else:
                    # Stream path exists but no frames (corrupted or stream issues)
                    result_container['result'] = {
                        "connected": False,
                        "status": "No Frames",
                        "message": "Camera reachable but cannot read video frames"
                    }
                    
            except Exception as e:
                error_msg = str(e)
                
                # Parse OpenCV error messages
                if "404" in error_msg or "Not Found" in error_msg:
                    result_container['result'] = {
                        "connected": False,
                        "status": "404 Not Found",
                        "message": "Stream path doesn't exist on camera"
                    }
                elif "401" in error_msg or "Unauthorized" in error_msg:
                    result_container['result'] = {
                        "connected": False,
                        "status": "401 Unauthorized",
                        "message": "Username or password incorrect"
                    }
                elif "Connection refused" in error_msg:
                    result_container['result'] = {
                        "connected": False,
                        "status": "Connection Refused",
                        "message": "Camera refused RTSP connection"
                    }
                else:
                    result_container['result'] = {
                        "connected": False,
                        "status": "Stream Error",
                        "message": error_msg[:50]
                    }
                    
        except Exception as e:
            result_container['result'] = {
                "connected": False,
                "status": "Error",
                "message": str(e)[:40]
            }
    
    # Run test in thread with timeout
    thread = threading.Thread(target=rtsp_test_worker, daemon=True)
    thread.start()
    thread.join(timeout=timeout + 2)
    
    if result_container['result'] is None:
        return {
            "connected": False,
            "status": "Test Timeout",
            "message": "Test took too long (> 5 seconds)"
        }
    
    return result_container['result']


@app.post("/api/camera/test-connection", tags=["Camera Management"])
async def test_camera_connection(request: Request, data: dict):
    """
    Test camera RTSP URLs - Method 2 (Full Stream Test)
    Tests both socket connection AND actual video stream
    """
    try:
        require_auth(request)
        entry_url = data.get('entry_url', '').strip()
        exit_url = data.get('exit_url', '').strip()
        
        if not entry_url or not exit_url:
            return {
                "success": False,
                "message": "Both URLs required",
                "entry": {
                    "connected": False,
                    "status": "Missing",
                    "message": "No URL provided"
                },
                "exit": {
                    "connected": False,
                    "status": "Missing",
                    "message": "No URL provided"
                }
            }
        
        if not entry_url.startswith('rtsp://') or not exit_url.startswith('rtsp://'):
            return {
                "success": False,
                "message": "URLs must start with rtsp://",
                "entry": {
                    "connected": False,
                    "status": "Invalid",
                    "message": "URL must start with rtsp://"
                },
                "exit": {
                    "connected": False,
                    "status": "Invalid",
                    "message": "URL must start with rtsp://"
                }
            }
        
        logger.info(f"Testing Entry Camera: {entry_url[:60]}...")
        logger.info(f"Testing Exit Camera: {exit_url[:60]}...")
        
        # Test both cameras with actual stream validation
        entry_result = await asyncio.wait_for(
            validate_rtsp_stream(entry_url, timeout=5),
            timeout=7
        )
        
        exit_result = await asyncio.wait_for(
            validate_rtsp_stream(exit_url, timeout=5),
            timeout=7
        )
        
        both_connected = entry_result.get("connected", False) and exit_result.get("connected", False)
        
        logger.info(f"Entry Camera Result: {entry_result['status']} - {entry_result['message']}")
        logger.info(f"Exit Camera Result: {exit_result['status']} - {exit_result['message']}")
        
        return {
            "success": both_connected,
            "entry": entry_result,
            "exit": exit_result,
            "message": "Both cameras working" if both_connected else "One or more cameras not working - check errors below"
        }
        
    except asyncio.TimeoutError:
        logger.error("Camera test timeout - took too long")
        return {
            "success": False,
            "message": "Test timed out - cameras not responding",
            "entry": {
                "connected": False,
                "status": "Timeout",
                "message": "Entry camera test timed out (>7 seconds)"
            },
            "exit": {
                "connected": False,
                "status": "Timeout",
                "message": "Exit camera test timed out (>7 seconds)"
            }
        }
    except Exception as e:
        logger.error(f"Camera test endpoint error: {e}")
        return {
            "success": False,
            "message": f"Server error: {str(e)[:60]}",
            "entry": {
                "connected": False,
                "status": "Error",
                "message": str(e)[:40]
            },
            "exit": {
                "connected": False,
                "status": "Error",
                "message": str(e)[:40]
            }
        }

#============= Employee Count ===============
@app.get("/api/dashboard/stats", tags=["Dashboard"])
async def get_dashboard_stats(request: Request):
    """
    Get dashboard statistics:
    - Total employees
    - Present today
    - Present yesterday
    - Average attendance (last 30 days)
    """
    try:
        user = require_auth(request)

        with db_service.get_connection() as conn:
            cursor = conn.cursor()

            # --- Get total employees ---
            cursor.execute("SELECT COUNT(*) FROM employees WHERE is_active = TRUE;")
            total_employees = cursor.fetchone()[0] or 0

            # --- Define date ranges ---
            today = datetime.date.today()
            yesterday = today - datetime.timedelta(days=1)
            start_date = today - datetime.timedelta(days=30)

            # --- Present today ---
            cursor.execute(
                "SELECT COUNT(DISTINCT emp_id) FROM attendance_logs WHERE date = %s;",
                (today,),
            )
            present_today = cursor.fetchone()[0] or 0

            # --- Present yesterday ---
            cursor.execute(
                "SELECT COUNT(DISTINCT emp_id) FROM attendance_logs WHERE date = %s;",
                (yesterday,),
            )
            present_yesterday = cursor.fetchone()[0] or 0

            # --- Average attendance (last 30 days) ---
            # Count total unique employee-date pairs
            cursor.execute(
                """
                SELECT COUNT(DISTINCT (emp_id, date))
                FROM attendance_logs
                WHERE date BETWEEN %s AND %s;
                """,
                (start_date, today),
            )
            total_present_30 = cursor.fetchone()[0] or 0

            # Count distinct days with attendance logs
            cursor.execute(
                """
                SELECT COUNT(DISTINCT date)
                FROM attendance_logs
                WHERE date BETWEEN %s AND %s;
                """,
                (start_date, today),
            )
            total_days_30 = cursor.fetchone()[0] or 1  # avoid division by zero

            # Compute average attendance percentage
            avg_attendance = (
                round((total_present_30 / (total_days_30 * total_employees)) * 100, 1)
                if total_employees > 0
                else 0.0
            )

            cursor.close()

            return {
                "total_employees": total_employees,
                "present_today": present_today,
                "present_yesterday": present_yesterday,
                "absent_today": total_employees - present_today,
                "avg_attendance": avg_attendance
            }

    except Exception as e:
        import traceback
        logger.error(f"Dashboard stats error: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))




@app.get("/api/attendance/stats/today", tags=["Attendance"])
async def get_attendance_stats_today(request: Request):
    """
    Get today's attendance statistics
    
    Uses correct column names:
    - attendance_logs.event_type (enum: 'IN', 'OUT')
    - attendance_logs.date (date field)
    """
    try:
        user = require_auth(request)
        today = datetime.date.today().strftime('%Y-%m-%d')
        
        with db_service.get_connection() as conn:
            cursor = conn.cursor()
            
            # Count IN events today
            cursor.execute("""
                SELECT COUNT(*) 
                FROM attendance_logs
                WHERE date = %s AND event_type = 'IN'
            """, (today,))
            total_in = cursor.fetchone()[0]
            
            # Count OUT events today
            cursor.execute("""
                SELECT COUNT(*) 
                FROM attendance_logs
                WHERE date = %s AND event_type = 'OUT'
            """, (today,))
            total_out = cursor.fetchone()[0]
            
            cursor.close()
            
            return {
                "success": True,
                "total_in": total_in,
                "total_out": total_out
            }
            
    except Exception as e:
        logger.error(f"Attendance stats error: {e}")
        return {
            "success": True,
            "total_in": 0,
            "total_out": 0
        }



# =========== User creation =================

@app.post("/api/admin/create-user", tags=["User Management"])
async def create_user(request: Request, data: dict):
    """Admin-only endpoint to create a new user."""
    user = require_admin(request) # Requires Admin role
    
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    full_name = data.get('full_name', '').strip()
    email = data.get('email', '').strip()
    role = data.get('role', 'user').strip()
    
    if not all([username, password, full_name, email]):
        raise HTTPException(status_code=400, detail="Missing required fields: username, password, full_name, email")

    try:
        # Calls the fixed function in AuthenticationService
        result = auth_service.create_user(username, password, full_name, email, role)
        
        if result['success']:
            log_audit(user['id'], "create_user", f"Created user: {username} with role {role}", request)
            return {"success": True, "message": "User created successfully"}
        else:
            # Handle common database errors like unique constraint violation
            if "duplicate key value" in result.get('message', ''):
                raise HTTPException(status_code=409, detail="Username or email already exists")
            
            logger.error(f"Error during user creation: {result['message']}")
            raise HTTPException(status_code=500, detail="Database error during user creation")
            
    except HTTPException:
        # Re-raise explicit HTTP exceptions (e.g., 400/409)
        raise
    except Exception as e:
        logger.error(f"User creation API error: {e}")
        log_audit(user['id'], "user_creation_failed", f"Failed to create user {username}: {str(e)[:50]}", request)
        raise HTTPException(status_code=500, detail="Internal Server Error")


# ==================================
# ADMIN MANAGEMENT ROUTES
# ==================================
@app.get("/manage-users")
async def manage_users_page(request: Request):
    """Serve the user management page (Admin only)."""
    user = auth_service.get_user_from_session(request) # Using the corrected method name
    
    # 1. ADD TEMPORARY DEBUGGING LOGGING
    if user:
        logger.info(f"Accessing /manage-users. User: {user.get('username')}, Role: {user.get('role')}")
    else:
        logger.warning("Accessing /manage-users. User not authenticated.")
    
    # 2. USE ROBUST DICTIONARY ACCESS FOR ROLE CHECK
    user_role = user.get('role') if user else None

    if not user or user.get('role') != 'admin':
        # Redirect non-admins or unauthenticated users
        return RedirectResponse(url="/", status_code=302)
    
    # Render the manage_users.html template
    return templates.TemplateResponse("manage_users.html", {"request": request, "user": user})

@app.get("/api/admin/users")
async def get_all_users_api(request: Request):
    """Retrieve all system users (Admin only)."""
    user = auth_service.get_user_from_session(request)
    if not user or user.get('role') != 'admin':
        raise HTTPException(status_code=403, detail="Permission denied")
    
    # Assuming db_service has a method to get users
    # We will implement this in services.py next
    try:
        users = db_service.get_all_system_users()
        return {"success": True, "users": users}
    except Exception as e:
        logger.error(f"Error fetching users: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve users.")

@app.post("/api/admin/user/{user_id}/update")
async def update_user_api(request: Request, user_id: int):
    # This endpoint logic will be implemented fully later, but the structure is here
    user = auth_service.get_user_from_session(request)
    if not user or user.get('role') != 'admin':
        raise HTTPException(status_code=403, detail="Permission denied")
    
    try:
        data = await request.json()
        db_service.update_system_user(user_id, data)
        return {"success": True, "message": "User updated successfully"}
    except Exception as e:
        logger.error(f"Error updating user: {e}")
        raise HTTPException(status_code=500, detail="Failed to update user.")

@app.delete("/api/admin/user/{user_id}/delete")
async def delete_user_api(request: Request, user_id: int):
    # This endpoint logic will be implemented fully later
    user = auth_service.get_user_from_session(request)
    if not user or user.get('role') != 'admin':
        raise HTTPException(status_code=403, detail="Permission denied")
    
    try:
        db_service.delete_system_user(user_id)
        return {"success": True, "message": "User deleted successfully"}
    except Exception as e:
        logger.error(f"Error deleting user: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete user.")


# ============ STARTUP & SHUTDOWN ============

@app.on_event("startup")
async def startup():
    try:
        logger.info("Starting system...")
        
        # Initialize database
        db_service.init_schema()
        db_service.init_auth_schema()
        
        # Load camera URLs and update config
        global CAMERA_CONFIG
        CAMERA_CONFIG = get_camera_config()
        
        entry_url = CAMERA_CONFIG['entry']['rtsp_url']
        exit_url = CAMERA_CONFIG['exit']['rtsp_url']
        
        logger.info(f"Camera URLs loaded:")
        logger.info(f"  Entry: {entry_url[:60]}...")
        logger.info(f"  Exit: {exit_url[:60]}...")
        
        # Load face embeddings
        face_map = db_service.load_all_embeddings()
        face_service.load_face_map(face_map)
        
        # Store in app state
        app.state.auth_service = auth_service
        app.state.db_service = db_service
        app.state.ws_manager = ws_manager
        
        # Update camera service with config
        camera_service.cameras = CAMERA_CONFIG
        start_scheduler()
 
        logger.info("=" * 70)
        logger.info(" SYSTEM READY - PRODUCTION v5.0.0")
        logger.info(" Features: Connection Pooling, Pagination, Multi-User, Race-Safe")
        logger.info(f" Loaded {len(face_map)} employees")
        logger.info("=" * 70)
    except Exception as e:
        logger.critical(f"Startup failed: {e}")
        raise

@app.on_event("shutdown")
async def shutdown():
    try:
        ws_manager.is_monitoring = False
        auth_service.cleanup_expired_sessions()
        
        # Close connection pool
        if hasattr(db_service, 'engine'):
            db_service.engine.dispose()
        
        logger.info("System shutdown complete")
    except Exception as e:
        logger.error(f"Shutdown error: {e}")


def daily_reset_task():
    """Reset daily dashboard counters at 12:30 AM IST (19:00 UTC)"""
    try:
        from pytz import timezone
        IST = timezone('Asia/Kolkata')
        now_ist = datetime.datetime.now(IST)

        logger.info("=" * 70)
        logger.info(f"🔄 DAILY RESET - {now_ist.strftime('%Y-%m-%d %H:%M:%S IST')}")
        logger.info("=" * 70)

        # ✅ Reset camera stats (dashboard counters only)
        camera_service.stats = {
            'total_faces': 0,        # Reset total faces detected
            'recognized': 0,         # Reset Entry IN recognized
            'unknown': 0             # Reset Exit OUT recognized
        }

        logger.info("✅ Counters reset:")
        logger.info("   - Entry Camera (IN) Recognized: 0")
        logger.info("   - Exit Camera (OUT) Recognized: 0")
        logger.info("   - Total Faces: 0")
        logger.info("=" * 70)

    except Exception as e:
        logger.error(f"❌ Reset failed: {e}")


def scheduler_thread():
    """Run scheduler - 12:30 AM IST = 19:00 UTC (server timezone)"""
    try:
        # Schedule reset for 19:00 UTC every day (= 12:30 AM IST)
        schedule.every().day.at("19:00").do(daily_reset_task)

        logger.info("=" * 70)
        logger.info("✅ Daily Scheduler Started")
        logger.info("   Reset time: 12:30 AM IST (19:00 UTC)")
        logger.info("=" * 70)

        while True:
            schedule.run_pending()
            time.sleep(60)

    except Exception as e:
        logger.error(f"Scheduler error: {e}")


def start_scheduler():
    """Start background scheduler thread"""
    scheduler = threading.Thread(target=scheduler_thread, daemon=True)
    scheduler.start()
    logger.info("🕐 Background scheduler thread started")



if __name__ == "__main__":
    import uvicorn
    print("=" * 70)
    print(" CCTV Attendance System - Production v5.0.0")
    print(" Features:")
    print("   âœ“ Database Connection Pooling")
    print("   âœ“ Pagination for Large Datasets")
    print("   âœ“ Race Condition Protection (asyncio.Lock)")
    print("   âœ“ Multi-User Session Tracking")
    print("   âœ“ Proper Export Handling")
    print("   âœ“ Admin-Only Camera URL Updates")
    print("=" * 70)
    print("Server: http://localhost:8000")
    print("Login: http://localhost:8000/login")
    print("=" * 70)
    uvicorn.run(app, host="0.0.0.0", port=8000, ssl_keyfile="key.pem", ssl_certfile="cert.pem",log_level="info")

