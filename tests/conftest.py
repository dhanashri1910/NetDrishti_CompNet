import copy, json, os, sys, tempfile
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture()
def app():
    d = tempfile.mkdtemp()
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///" + os.path.join(d, "t.db"),
                       "UPLOAD_FOLDER": os.path.join(d, "up"), "REPORT_FOLDER": os.path.join(d, "rep")})


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def admin(client):
    client.post("/login", data={"email": "admin@netpulse.lab", "password": "Admin@12345"})
    return client


@pytest.fixture()
def base():
    return copy.deepcopy(json.load(open(os.path.join(ROOT, "data", "sample_network.json")))["topology"])
