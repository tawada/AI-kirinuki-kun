from src.app import app
from src.tasks import celery
from celery.schedules import crontab
from src.tasks import monitor_failed_tasks

# 定期実行タスクの設定
celery.conf.beat_schedule = {
    'monitor-failed-tasks': {
        'task': 'src.tasks.monitor_failed_tasks',
        'schedule': crontab(minute='*/30'),  # 30分ごとに実行
    },
}

if __name__ == '__main__':
    with app.app_context():
        # celery worker と beat を同時に起動
        celery.worker_main(['worker', '--loglevel=info', '-B'])