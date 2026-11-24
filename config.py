import os
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    BASE_DIR = BASE_DIR
    SECRET_KEY = os.environ.get("SECRET_KEY", "netdrishti-dev-secret-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "instance", "netpulse.db"))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    REPORT_FOLDER = os.path.join(BASE_DIR, "reports")
    DATA_FOLDER = os.path.join(BASE_DIR, "data")
    MAX_CONTENT_LENGTH = 32 * 1024 * 1024
    # Optional AI explanations (never required). Key is read from the environment only.
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    AI_MODEL = os.environ.get("NETDRISHTI_AI_MODEL", os.environ.get("NETPULSE_AI_MODEL", "claude-sonnet-5-5"))
    DEMO_ADMIN_EMAIL = "admin@netpulse.lab"
    DEMO_ADMIN_PASSWORD = "Admin@12345"
