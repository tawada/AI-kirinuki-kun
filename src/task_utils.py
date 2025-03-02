"""タスク処理でのログ記録やステータス更新のユーティリティ関数"""

from src.models import db, ProcessLog

def update_log_with_task_id(video_id, status, message, task_id):
    """タスクIDを含めて処理ログを記録する関数"""
    log = ProcessLog(
        video_id=video_id,
        status=status,
        message=message,
        task_id=task_id
    )
    db.session.add(log)
    db.session.commit()
    
    return log