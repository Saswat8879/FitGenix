import pytest
from app import create_app
from app.extensions import db as _db
import tempfile, os

@pytest.fixture
def app():
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    cfg = {
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
        "SECRET_KEY": "test-secret",
        "WTF_CSRF_ENABLED": False
    }
    app = create_app()
    app.config.update(cfg)
    with app.app_context():
        _db.create_all()
    yield app
    os.close(db_fd)
    os.unlink(db_path)

@pytest.fixture
def client(app):
    return app.test_client()
