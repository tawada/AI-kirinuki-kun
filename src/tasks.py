import os
import time
from datetime import datetime, timedelta
from celery import Celery
from celery.signals import task_failure
from moviepy.editor import VideoFileClip
import yt_dlp
from src.models import db, Video, Highlight, ProcessLog, ProcessStatus
from src.youtube_downloader import download_video
from src.video_processor import get_video_highlights, process_video
from src.task_utils import update_log_with_task_id

# Celeryの設定
celery = Celery('ai_kirinuki_tasks')

def configure_celery(app):
    """FlaskアプリのコンテキストでCeleryを設定する"""
    celery.conf.update(
        broker_url=app.config['CELERY_BROKER_URL'],
        result_backend=app.config['CELERY_RESULT_BACKEND'],
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='Asia/Tokyo',
        enable_utc=True,
        # タスク実行の設定
        task_acks_late=True,      # 処理が完了したタスクのみをACKする
        worker_prefetch_multiplier=1,  # 一度にプリフェッチするタスク数を制限
        result_expires=3600,      # 結果の有効期限（秒）
        task_track_started=True,  # タスクの開始状態を追跡
        task_default_retry_delay=60,  # 失敗したタスクの再試行までの待機時間（秒）
        task_default_queue='default',  # デフォルトのキュー名
        task_time_limit=3600,     # タスクの実行時間制限（秒）
        # データベース関連の設定
        task_ignore_result=False, # タスク結果を保存
        worker_max_tasks_per_child=200,  # ワーカーが再起動するまでに処理するタスク数
        # 自動リトライの設定
        task_publish_retry=True,  # 非同期処理のリトライを有効化
        task_publish_retry_policy={
            'max_retries': 5,     # 最大リトライ回数
            'interval_start': 0,  # 初回リトライまでの待機時間（秒）
            'interval_step': 1,   # リトライごとの待機時間増分（秒）
            'interval_max': 60,   # 最大待機時間（秒）
        },
    )

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
        
        # 自動リトライ設定
        autoretry_for = (Exception,)  # すべての例外でリトライを行う
        retry_kwargs = {
            'max_retries': 3,  # 最大リトライ回数
            'countdown': 60    # リトライ間隔（秒）
        }
                
        def on_failure(self, exc, task_id, args, kwargs, einfo):
            """タスク失敗時のハンドラ"""
            if args and len(args) > 0 and isinstance(args[0], int):
                video_id = args[0]
                try:
                    from src.models import db, Video, ProcessLog, ProcessStatus
                    video = db.session.get(Video, video_id)
                    if video:
                        # リトライが失敗した回数を計算
                        retry_count = self.request.retries if hasattr(self.request, 'retries') else 0
                        
                        # 最大リトライに達していない場合、エラーを記録して状態を更新
                        if retry_count < self.retry_kwargs['max_retries']:
                            status_message = f"タスクが失敗しました。自動リトライを実行します ({retry_count+1}/{self.retry_kwargs['max_retries']})"
                            
                            # エラーログを記録
                            error_log = ProcessLog(
                                video_id=video_id,
                                status=ProcessStatus.FAILED,
                                message=f"{status_message}: {str(exc)}",
                                task_id=task_id
                            )
                            db.session.add(error_log)
                            
                            # ビデオのステータスはFAILEDに設定しない（リトライするため）
                            video.error_message = f"エラーが発生しましたが、自動リトライします: {str(exc)}"
                            db.session.commit()
                        else:
                            # 最大リトライに達した場合、最終的にFAILEDに設定
                            video.status = ProcessStatus.FAILED
                            video.error_message = f"最大リトライ回数に達しました: {str(exc)}"
                            
                            error_log = ProcessLog(
                                video_id=video_id,
                                status=ProcessStatus.FAILED,
                                message=f"最大リトライ回数({self.retry_kwargs['max_retries']})に達しました: {str(exc)}",
                                task_id=task_id
                            )
                            db.session.add(error_log)
                            db.session.commit()
                except Exception as e:
                    print(f"エラーハンドリング中に例外が発生しました: {e}")
                    
            super(ContextTask, self).on_failure(exc, task_id, args, kwargs, einfo)

    celery.Task = ContextTask
    return celery

@celery.task(bind=True)
def process_video_task(self, video_id):
    """動画処理の全体フローを管理するタスク（非同期処理チェーン）"""
    try:
        # ビデオレコードの取得
        video = db.session.get(Video, video_id)
        if not video:
            return {'status': 'error', 'message': 'ビデオが見つかりません'}

        # ダウンロードタスクを開始
        # ここでは状態をDOWNLOADINGに設定するだけで、実際の処理は非同期に実行
        video.status = ProcessStatus.DOWNLOADING
        video.progress = 5
        video.current_task_id = self.request.id  # 現在のタスクIDを保存
        
        # ログ記録
        log = ProcessLog(
            video_id=video_id,
            status=ProcessStatus.DOWNLOADING,
            message="ダウンロードタスクをキューに追加しました",
            task_id=self.request.id
        )
        db.session.add(log)
        db.session.commit()

        # 非同期タスクチェーンを実行
        # 1. ダウンロードタスクの実行
        task = download_task.delay(video_id)
        
        # タスクIDをデータベースに記録
        video.current_task_id = task.id
        db.session.commit()
        
        return {'status': 'success', 'video_id': video_id, 'session_id': video.session_id, 'task_id': self.request.id}
    
    except Exception as e:
        # エラー発生時の処理
        video = db.session.get(Video, video_id)
        if video:
            video.status = ProcessStatus.FAILED
            video.error_message = str(e)
            
            # エラーログを記録
            error_log = ProcessLog(
                video_id=video_id,
                status=ProcessStatus.FAILED,
                message=f"処理中にエラーが発生しました: {str(e)}",
                task_id=self.request.id
            )
            db.session.add(error_log)
            db.session.commit()
        
        return {'status': 'error', 'message': str(e), 'video_id': video_id}

# 直接実行する関数版（同期実行）
def download_task_sync(video_id):
    """動画のダウンロードタスク（同期版）"""
    try:
        # ビデオレコードの取得
        video = db.session.get(Video, video_id)
        if not video:
            return {'status': 'error', 'message': 'ビデオが見つかりません'}
        
        # ステータス更新
        video.status = ProcessStatus.DOWNLOADING
        video.progress = 10
        
        # ログ記録
        log = ProcessLog(
            video_id=video_id,
            status=ProcessStatus.DOWNLOADING,
            message="動画のダウンロードを開始しました"
        )
        db.session.add(log)
        db.session.commit()
        
        # 動画のダウンロード
        upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads')
        file_path = download_video(video.youtube_url, upload_dir, video.session_id)
        
        # メタデータの抽出
        extract_metadata(video, video.youtube_url)
        
        # ビデオレコードの更新
        video.original_path = file_path
        video.progress = 30
        
        # ログ記録
        log = ProcessLog(
            video_id=video_id,
            status=ProcessStatus.DOWNLOADING,
            message="動画のダウンロードが完了しました"
        )
        db.session.add(log)
        db.session.commit()
        
        return {'status': 'success', 'video_id': video_id, 'file_path': file_path}
    
    except Exception as e:
        # エラー発生時の処理
        video = db.session.get(Video, video_id)
        if video:
            video.status = ProcessStatus.FAILED
            video.error_message = f"ダウンロード中にエラーが発生しました: {str(e)}"
            
            # エラーログを記録
            error_log = ProcessLog(
                video_id=video_id,
                status=ProcessStatus.FAILED,
                message=f"ダウンロード中にエラーが発生しました: {str(e)}"
            )
            db.session.add(error_log)
            db.session.commit()
        
        raise Exception(f"ダウンロード中にエラーが発生しました: {str(e)}")

def analyze_task_sync(video_id):
    """動画の解析タスク（同期版）"""
    try:
        # ビデオレコードの取得
        video = db.session.get(Video, video_id)
        if not video:
            return {'status': 'error', 'message': 'ビデオが見つかりません'}
        
        # ステータス更新
        video.status = ProcessStatus.ANALYZING
        video.progress = 40
        
        # ログ記録
        log = ProcessLog(
            video_id=video_id,
            status=ProcessStatus.ANALYZING,
            message="動画の解析を開始しました"
        )
        db.session.add(log)
        db.session.commit()
        
        # 動画の解析
        highlights_data = get_video_highlights(video.original_path)
        
        # ハイライトの保存
        for start_time, end_time in highlights_data:
            highlight = Highlight(
                video_id=video_id,
                start_time=start_time,
                end_time=end_time,
                importance_score=0.8  # 実際の実装ではスコアを計算
            )
            db.session.add(highlight)
        
        # ビデオレコードの更新
        video.progress = 70
        
        # ログ記録
        log = ProcessLog(
            video_id=video_id,
            status=ProcessStatus.ANALYZING,
            message="動画の解析が完了しました"
        )
        db.session.add(log)
        db.session.commit()
        
        return {'status': 'success', 'video_id': video_id, 'highlights_count': len(highlights_data)}
    
    except Exception as e:
        # エラー発生時の処理
        video = db.session.get(Video, video_id)
        if video:
            video.status = ProcessStatus.FAILED
            video.error_message = f"解析中にエラーが発生しました: {str(e)}"
            
            # エラーログを記録
            error_log = ProcessLog(
                video_id=video_id,
                status=ProcessStatus.FAILED,
                message=f"解析中にエラーが発生しました: {str(e)}"
            )
            db.session.add(error_log)
            db.session.commit()
        
        raise Exception(f"解析中にエラーが発生しました: {str(e)}")

def create_highlights_task_sync(video_id):
    """切り抜き動画の作成タスク（同期版）"""
    try:
        # ビデオレコードの取得
        video = db.session.get(Video, video_id)
        if not video:
            return {'status': 'error', 'message': 'ビデオが見つかりません'}
        
        # ステータス更新
        video.status = ProcessStatus.PROCESSING
        video.progress = 80
        
        # ログ記録
        log = ProcessLog(
            video_id=video_id,
            status=ProcessStatus.PROCESSING,
            message="切り抜き動画の作成を開始しました"
        )
        db.session.add(log)
        db.session.commit()
        
        # ハイライト情報の取得
        highlights = [(h.start_time, h.end_time) for h in video.highlights]
        
        # 出力ディレクトリの設定
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'outputs')
        
        # 切り抜き動画の作成
        output_path = process_video(video.original_path, highlights, output_dir, video.session_id)
        
        # ビデオレコードの更新
        video.output_path = output_path
        video.status = ProcessStatus.COMPLETED
        video.progress = 100
        
        # ログ記録
        log = ProcessLog(
            video_id=video_id,
            status=ProcessStatus.COMPLETED,
            message="切り抜き動画の作成が完了しました"
        )
        db.session.add(log)
        db.session.commit()
        
        return {'status': 'success', 'video_id': video_id, 'output_path': output_path}
    
    except Exception as e:
        # エラー発生時の処理
        video = db.session.get(Video, video_id)
        if video:
            video.status = ProcessStatus.FAILED
            video.error_message = f"動画作成中にエラーが発生しました: {str(e)}"
            
            # エラーログを記録
            error_log = ProcessLog(
                video_id=video_id,
                status=ProcessStatus.FAILED,
                message=f"動画作成中にエラーが発生しました: {str(e)}"
            )
            db.session.add(error_log)
            db.session.commit()
        
        raise Exception(f"動画作成中にエラーが発生しました: {str(e)}")

@celery.task(bind=True)
def download_task(self, video_id):
    """動画のダウンロードタスク（非同期版）"""
    try:
        # ビデオレコードの取得
        video = db.session.get(Video, video_id)
        if not video:
            return {'status': 'error', 'message': 'ビデオが見つかりません'}
        
        # ステータス更新（すでにDOWNLOADINGに設定されているはず）
        # 進捗を更新
        video.progress = 10
        video.current_task_id = self.request.id  # 現在のタスクIDを保存
        
        # ログ記録
        log = ProcessLog(
            video_id=video_id,
            status=ProcessStatus.DOWNLOADING,
            message="動画のダウンロードを開始しました",
            task_id=self.request.id
        )
        db.session.add(log)
        db.session.commit()
        
        # 動画のダウンロード
        upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads')
        file_path = download_video(video.youtube_url, upload_dir, video.session_id)
        
        # メタデータの抽出
        extract_metadata(video, video.youtube_url)
        
        # ビデオレコードの更新
        video.original_path = file_path
        video.progress = 30
        
        # ログ記録
        log = ProcessLog(
            video_id=video_id,
            status=ProcessStatus.DOWNLOADING,
            message="動画のダウンロードが完了しました"
        )
        db.session.add(log)
        db.session.commit()
        
        # 次のタスク（解析タスク）を自動的に実行
        task = analyze_task.delay(video_id)
        
        # 次のタスクIDをデータベースに記録
        video.current_task_id = task.id
        db.session.commit()
        
        return {'status': 'success', 'video_id': video_id, 'file_path': file_path, 'task_id': self.request.id}
    
    except Exception as e:
        # エラー発生時の処理
        video = db.session.get(Video, video_id)
        if video:
            video.status = ProcessStatus.FAILED
            video.error_message = f"ダウンロード中にエラーが発生しました: {str(e)}"
            
            # エラーログを記録
            error_log = ProcessLog(
                video_id=video_id,
                status=ProcessStatus.FAILED,
                message=f"ダウンロード中にエラーが発生しました: {str(e)}"
            )
            db.session.add(error_log)
            db.session.commit()
        
        # エラーを記録するだけで再スローしない（タスクチェーンを中断）
        return {'status': 'error', 'message': str(e), 'video_id': video_id, 'task_id': self.request.id}

@celery.task(bind=True)
def analyze_task(self, video_id):
    """動画の解析タスク（非同期版）"""
    try:
        # ビデオレコードの取得
        video = db.session.get(Video, video_id)
        if not video:
            return {'status': 'error', 'message': 'ビデオが見つかりません'}
        
        # ステータス更新
        video.status = ProcessStatus.ANALYZING
        video.progress = 40
        video.current_task_id = self.request.id  # 現在のタスクIDを保存
        
        # ログ記録 - タスクIDを含める
        update_log_with_task_id(
            video_id=video_id,
            status=ProcessStatus.ANALYZING,
            message="動画の解析を開始しました",
            task_id=self.request.id
        )
        
        # 動画の解析
        highlights_data = get_video_highlights(video.original_path)
        
        # ハイライトの保存
        for start_time, end_time in highlights_data:
            highlight = Highlight(
                video_id=video_id,
                start_time=start_time,
                end_time=end_time,
                importance_score=0.8  # 実際の実装ではスコアを計算
            )
            db.session.add(highlight)
        
        # ビデオレコードの更新
        video.progress = 70
        
        # ログ記録 - タスクIDを含める
        update_log_with_task_id(
            video_id=video_id,
            status=ProcessStatus.ANALYZING,
            message="動画の解析が完了しました",
            task_id=self.request.id
        )
        
        # 次のタスク（動画作成タスク）を実行
        task = create_highlights_task.delay(video_id)
        
        # 次のタスクIDをデータベースに記録
        video.current_task_id = task.id
        db.session.commit()
        
        return {'status': 'success', 'video_id': video_id, 'highlights_count': len(highlights_data), 'task_id': self.request.id}
    
    except Exception as e:
        # エラー発生時の処理
        video = db.session.get(Video, video_id)
        if video:
            video.status = ProcessStatus.FAILED
            video.error_message = f"解析中にエラーが発生しました: {str(e)}"
            
            # エラーログを記録
            update_log_with_task_id(
                video_id=video_id,
                status=ProcessStatus.FAILED,
                message=f"解析中にエラーが発生しました: {str(e)}",
                task_id=self.request.id
            )
        
        # エラーを記録するだけで再スローしない（タスクチェーンを中断）
        return {'status': 'error', 'message': str(e), 'video_id': video_id, 'task_id': self.request.id}

@celery.task(bind=True)
def create_highlights_task(self, video_id):
    """切り抜き動画の作成タスク（非同期版）"""
    try:
        # ビデオレコードの取得
        video = db.session.get(Video, video_id)
        if not video:
            return {'status': 'error', 'message': 'ビデオが見つかりません'}
        
        # ステータス更新
        video.status = ProcessStatus.PROCESSING
        video.progress = 80
        
        # ログ記録
        log = ProcessLog(
            video_id=video_id,
            status=ProcessStatus.PROCESSING,
            message="切り抜き動画の作成を開始しました"
        )
        db.session.add(log)
        db.session.commit()
        
        # ハイライト情報の取得
        highlights = [(h.start_time, h.end_time) for h in video.highlights]
        
        # 出力ディレクトリの設定
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'outputs')
        
        # 切り抜き動画の作成
        output_path = process_video(video.original_path, highlights, output_dir, video.session_id)
        
        # ビデオレコードの更新
        video.output_path = output_path
        video.status = ProcessStatus.COMPLETED
        video.progress = 100
        
        # ログ記録
        log = ProcessLog(
            video_id=video_id,
            status=ProcessStatus.COMPLETED,
            message="切り抜き動画の作成が完了しました"
        )
        db.session.add(log)
        db.session.commit()
        
        return {'status': 'success', 'video_id': video_id, 'output_path': output_path, 'task_id': self.request.id}
    
    except Exception as e:
        # エラー発生時の処理
        video = db.session.get(Video, video_id)
        if video:
            video.status = ProcessStatus.FAILED
            video.error_message = f"動画作成中にエラーが発生しました: {str(e)}"
            
            # エラーログを記録
            error_log = ProcessLog(
                video_id=video_id,
                status=ProcessStatus.FAILED,
                message=f"動画作成中にエラーが発生しました: {str(e)}"
            )
            db.session.add(error_log)
            db.session.commit()
        
        # エラーを記録するだけで再スローしない（タスクチェーンを中断）
        return {'status': 'error', 'message': str(e), 'video_id': video_id, 'task_id': self.request.id}

def extract_metadata(video, youtube_url):
    """動画のメタデータを抽出する"""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,  # 動画のダウンロードをスキップ
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            
            # メタデータの設定
            video.title = info.get('title')
            video.description = info.get('description')
            video.duration = info.get('duration')
            
            # サムネイルURLの取得（可能であれば最高品質を選択）
            thumbnails = info.get('thumbnails', [])
            if thumbnails:
                # サイズでソート（大きい順）
                sorted_thumbnails = sorted(
                    thumbnails, 
                    key=lambda x: (x.get('width', 0) * x.get('height', 0)), 
                    reverse=True
                )
                video.thumbnail_url = sorted_thumbnails[0].get('url') if sorted_thumbnails else None
    
    except Exception as e:
        # メタデータ抽出のエラーは致命的ではないので、ログに記録するだけ
        print(f"メタデータの抽出中にエラーが発生しました: {str(e)}")


# タスク失敗検出とリカバリ用の定期タスク
@celery.task
def monitor_failed_tasks():
    """失敗したタスクを検出し、必要に応じて再起動するタスク"""
    try:
        from src.models import db, Video, ProcessLog, ProcessStatus
        
        # FAILEDステータスのビデオを取得（最終更新から一定時間経過したもののみ）
        recovery_threshold = datetime.utcnow() - timedelta(minutes=5)  # 5分前までに失敗したタスク
        
        # 失敗したビデオとステータスが中途半端なビデオを検索
        failed_videos = db.session.query(Video).filter(
            (Video.status == ProcessStatus.FAILED) &
            (Video.updated_at <= recovery_threshold) &
            (Video.progress < 100)  # 完了していないものを対象に
        ).all()
        
        # 中断したビデオ（タイムアウトや不正終了など）
        stalled_videos = db.session.query(Video).filter(
            Video.status.in_([
                ProcessStatus.DOWNLOADING,
                ProcessStatus.ANALYZING,
                ProcessStatus.PROCESSING
            ]) &
            (Video.updated_at <= recovery_threshold) &
            (Video.progress < 100)
        ).all()
        
        recovery_count = 0
        
        # 失敗したタスクのリカバリ
        for video in failed_videos:
            # 最新のプロセスログを取得して失敗したステップを特定
            last_log = db.session.query(ProcessLog).filter(
                ProcessLog.video_id == video.id
            ).order_by(ProcessLog.created_at.desc()).first()
            
            if not last_log:
                continue
            
            # ステータスに応じて適切なタスクを開始
            restart_task(video, last_log)
            recovery_count += 1
        
        # 中断したタスクのリカバリ
        for video in stalled_videos:
            # 最新のプロセスログを取得
            last_log = db.session.query(ProcessLog).filter(
                ProcessLog.video_id == video.id
            ).order_by(ProcessLog.created_at.desc()).first()
            
            if not last_log:
                continue
            
            # ステータスに応じて適切なタスクを開始
            restart_task(video, last_log)
            recovery_count += 1
        
        return {
            'status': 'success',
            'recovered_tasks': recovery_count,
            'failed_videos': len(failed_videos),
            'stalled_videos': len(stalled_videos)
        }
        
    except Exception as e:
        print(f"タスクモニタリング中にエラーが発生しました: {str(e)}")
        return {'status': 'error', 'message': str(e)}


def restart_task(video, last_log):
    """失敗または中断したタスクを再開する"""
    try:
        # リカバリーログを追加
        recovery_log = ProcessLog(
            video_id=video.id,
            status=ProcessStatus.PENDING,
            message=f"タスクの自動リカバリーを開始します。前回のステータス: {video.status.value}"
        )
        db.session.add(recovery_log)
        
        # ビデオのステータスをリセット
        video.status = ProcessStatus.PENDING
        video.error_message = None
        
        # タスクの状態に応じて、適切なポイントからタスクを再開
        if not video.original_path:
            # ダウンロードから失敗した場合
            video.status = ProcessStatus.DOWNLOADING
            new_task = download_task.delay(video.id)
            video.current_task_id = new_task.id
        elif video.status == ProcessStatus.DOWNLOADING or video.status == ProcessStatus.ANALYZING:
            # 解析中に失敗した場合
            video.status = ProcessStatus.ANALYZING
            new_task = analyze_task.delay(video.id)
            video.current_task_id = new_task.id
        elif video.status == ProcessStatus.PROCESSING:
            # ハイライト作成中に失敗した場合
            video.status = ProcessStatus.PROCESSING
            new_task = create_highlights_task.delay(video.id)
            video.current_task_id = new_task.id
        else:
            # その他の状態では最初からやり直し
            video.status = ProcessStatus.PENDING
            new_task = process_video_task.delay(video.id)
            video.current_task_id = new_task.id
        
        db.session.commit()
        
        return True
    except Exception as e:
        print(f"タスク再開中にエラーが発生しました (video_id={video.id}): {str(e)}")
        return False