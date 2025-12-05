#!/usr/bin/env python3
import psycopg2

print("=" * 70)
print("COMBINING ALL 8 FACE ANGLES PER EMPLOYEE")
print("=" * 70)

POSTGRES_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'user': 'oasys',
    'password': 'Oasys1234',
    'database': 'face_attendance'
}

try:
    print("\n[1] Connecting to PostgreSQL...")
    pg_conn = psycopg2.connect(**POSTGRES_CONFIG)
    pg_c = pg_conn.cursor()
    print("OK PostgreSQL connected")
except Exception as e:
    print(f"ERROR: {e}")
    exit(1)

try:
    print("\n[2] Creating new combined employees table with 8 angles...")
    pg_c.execute("""
        DROP TABLE IF EXISTS employees_combined CASCADE
    """)
    pg_c.execute("""
        CREATE TABLE employees_combined (
            id SERIAL PRIMARY KEY,
            emp_id VARCHAR(20) UNIQUE NOT NULL,
            name VARCHAR(100) NOT NULL,
            department VARCHAR(50),
            position VARCHAR(50),
            is_active BOOLEAN DEFAULT TRUE,
            front_embedding vector(512),
            front_quality FLOAT,
            looking_up_embedding vector(512),
            looking_up_quality FLOAT,
            left_embedding vector(512),
            left_quality FLOAT,
            right_embedding vector(512),
            right_quality FLOAT,
            up_left_embedding vector(512),
            up_left_quality FLOAT,
            up_right_embedding vector(512),
            up_right_quality FLOAT,
            tilt_left_embedding vector(512),
            tilt_left_quality FLOAT,
            tilt_right_embedding vector(512),
            tilt_right_quality FLOAT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    pg_conn.commit()
    print("OK New table created with 8 angle types")
except Exception as e:
    print(f"ERROR: {e}")
    pg_conn.rollback()
    exit(1)

try:
    print("\n[3] Copying employee data...")
    pg_c.execute("""
        INSERT INTO employees_combined (emp_id, name, department, position, is_active, created_at, updated_at)
        SELECT emp_id, name, department, position, is_active, created_at, updated_at
        FROM employees
    """)
    pg_conn.commit()
    pg_c.execute("SELECT COUNT(*) FROM employees_combined")
    count = pg_c.fetchone()[0]
    print(f"OK Copied {count} employees")
except Exception as e:
    print(f"ERROR: {e}")
    pg_conn.rollback()
    exit(1)

try:
    print("\n[4] Merging all 8 face angles...")
    
    angles = [
        ('front', 'front'),
        ('looking_up', 'looking_up'),
        ('left', 'left'),
        ('right', 'right'),
        ('up_left', 'up_left'),
        ('up_right', 'up_right'),
        ('tilt_left', 'tilt_left'),
        ('tilt_right', 'tilt_right')
    ]
    
    for col_name, angle_type in angles:
        pg_c.execute(f"""
            UPDATE employees_combined ec
            SET {col_name}_embedding = fe.embedding,
                {col_name}_quality = fe.quality_score
            FROM face_embeddings fe
            WHERE ec.emp_id = fe.emp_id AND fe.angle_type = %s
        """, (angle_type,))
    
    pg_conn.commit()
    
    print("\nEmbeddings per angle:")
    for col_name, angle_type in angles:
        pg_c.execute(f"SELECT COUNT(*) FROM employees_combined WHERE {col_name}_embedding IS NOT NULL")
        count = pg_c.fetchone()[0]
        print(f"  {angle_type}: {count}")
    
except Exception as e:
    print(f"ERROR: {e}")
    pg_conn.rollback()
    exit(1)

try:
    print("\n[5] Creating vector indexes for all 8 angles...")
    pg_c.execute("CREATE INDEX idx_front_embedding ON employees_combined USING ivfflat (front_embedding vector_cosine_ops)")
    pg_c.execute("CREATE INDEX idx_looking_up_embedding ON employees_combined USING ivfflat (looking_up_embedding vector_cosine_ops)")
    pg_c.execute("CREATE INDEX idx_left_embedding ON employees_combined USING ivfflat (left_embedding vector_cosine_ops)")
    pg_c.execute("CREATE INDEX idx_right_embedding ON employees_combined USING ivfflat (right_embedding vector_cosine_ops)")
    pg_c.execute("CREATE INDEX idx_up_left_embedding ON employees_combined USING ivfflat (up_left_embedding vector_cosine_ops)")
    pg_c.execute("CREATE INDEX idx_up_right_embedding ON employees_combined USING ivfflat (up_right_embedding vector_cosine_ops)")
    pg_c.execute("CREATE INDEX idx_tilt_left_embedding ON employees_combined USING ivfflat (tilt_left_embedding vector_cosine_ops)")
    pg_c.execute("CREATE INDEX idx_tilt_right_embedding ON employees_combined USING ivfflat (tilt_right_embedding vector_cosine_ops)")
    pg_conn.commit()
    print("OK All vector indexes created")
except Exception as e:
    print(f"WARNING: {e}")

try:
    print("\n[6] Dropping old tables...")
    pg_c.execute("DROP TABLE IF EXISTS face_embeddings CASCADE")
    pg_c.execute("DROP TABLE IF EXISTS employees CASCADE")
    pg_conn.commit()
    print("OK Old tables dropped")
except Exception as e:
    print(f"ERROR: {e}")
    pg_conn.rollback()
    exit(1)

try:
    print("\n[7] Renaming new table to employees...")
    pg_c.execute("ALTER TABLE employees_combined RENAME TO employees")
    pg_conn.commit()
    print("OK Table renamed")
except Exception as e:
    print(f"ERROR: {e}")
    pg_conn.rollback()
    exit(1)

pg_c.close()
pg_conn.close()

print("\n" + "=" * 70)
print("OK ALL 8 ANGLES COMBINED!")
print("=" * 70)
