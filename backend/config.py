import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # Database Configuration
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", 5432))
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
    DB_NAME = os.getenv("DB_NAME", "face_attendance")
    FRONTEND_HOST = os.getenv("FRONTEND_HOST", "http://localhost:5173")

    # Camera
    CAMERA_URL_FILE = "camera_urls.json"

settings = Settings()
