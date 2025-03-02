import os
from celery import Celery
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
    )

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
                
        def on_failure(self, exc, task_id, args, kwargs, einfo):
            """タスク失敗時のハンドラ"""
            if args and len(args) > 0 and isinstance(args[0], int):
                video_id = args[0]
                try:
                    from src.models import db, Video, ProcessLog, ProcessStatus
                    video = db.session.get(Video, video_id)
                    if video:
                        video.status = ProcessStatus.FAILED
                        video.error_message = str(exc)
                        
                        error_log = ProcessLog(
                            video_id=video_id,
                            status=ProcessStatus.FAILED,
                            message=f"タスク実行中にエラーが発生しました: {str(exc)}"
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