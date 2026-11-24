"""Initialise the NetDrishti SQLite database: python init_db.py"""
from app import app

print("Database ready:", app.config["SQLALCHEMY_DATABASE_URI"])
print("Demo admin:", app.config["DEMO_ADMIN_EMAIL"])
