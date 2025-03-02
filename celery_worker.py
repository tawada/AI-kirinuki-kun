from src.app import app
from src.tasks import celery

if __name__ == '__main__':
    with app.app_context():
        celery.worker_main(['worker', '--loglevel=info'])