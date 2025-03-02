from flask_migrate import Migrate
from src.models import db

migrate = Migrate()

def init_db(app):
    """データベースの初期化"""
    db.init_app(app)
    migrate.init_app(app, db)
    
    with app.app_context():
        db.create_all()