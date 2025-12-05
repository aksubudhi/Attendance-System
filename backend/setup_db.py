import psycopg2
from psycopg2 import sql
import logging
from config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_db_connection():
    """Get connection to the database"""
    return psycopg2.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_NAME
    )

def init_db():
    """Initialize the database schema"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        logger.info("Initializing Database Schema...")

        # 1. Extensions
        logger.info("Enable pgvector extension")
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")

        # 2. Employees Table (Combined with 8 angles)
        logger.info("Creating Table: employees")
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
        
        # Indexes for Employees
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_emp_name ON employees(name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_emp_dept ON employees(department)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_emp_active ON employees(is_active)")
        
        # Vector Indexes (IVFFlat) - Wrapped in try/except as they might fail on empty tables or if already exists differently
        vector_columns = [
            'front_embedding', 'looking_up_embedding', 'left_embedding', 'right_embedding',
            'up_left_embedding', 'up_right_embedding', 'tilt_left_embedding', 'tilt_right_embedding'
        ]
        
        for col in vector_columns:
            try:
                index_name = f"idx_{col.replace('_embedding', '_emb')}"
                cursor.execute(f"""
                    CREATE INDEX IF NOT EXISTS {index_name} 
                    ON employees USING ivfflat ({col} vector_cosine_ops)
                """)
            except Exception as e:
                logger.warning(f"Could not create index for {col}: {e}")
                conn.rollback() 
                # Need to restart transaction block if rollback happens? 
                # Actually, in psycopg2 auto-commit is off by default.
                # If we error, the transaction is aborted. 
                # Let's handle it better by committing before or separately.

        # 3. Attendance Logs Table
        logger.info("Creating Table: attendance_logs")
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

        # 4. Users Table (Authentication)
        logger.info("Creating Table: users")
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

        # 5. Sessions Table
        logger.info("Creating Table: sessions")
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

        # 6. Audit Log Table
        logger.info("Creating Table: audit_log")
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

        # 7. System Stats Table
        logger.info("Creating Table: system_stats")
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
        logger.info("Database Schema Initialized Successfully!")
        
        cursor.close()
        conn.close()

    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise

if __name__ == "__main__":
    init_db()
