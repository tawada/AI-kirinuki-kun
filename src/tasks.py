import os
from celery import Celery
from moviepy.editor import VideoFileClip
import yt_dlp
from src.models import db, Video, Highlight, ProcessLog, ProcessStatus
from src.youtube_downloader import download_video
from src.video_processor import get_video_highlights, process_video

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
    )

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery

@celery.task
def process_video_task(video_id):
    """動画処理の全体フローを管理するタスク"""
    try:
        # ビデオレコードの取得
        video = db.session.get(Video, video_id)
        if not video:
            return {'status': 'error', 'message': 'ビデオが見つかりません'}

        # ダウンロードタスクを直接実行（非同期化しない）
        # ステータスがPENDINGからDOWNLOADINGに変わることを確認するため
        download_task_sync(video_id)
        
        # 以下のタスクも直接実行（実際のプロダクションでは非同期化が望ましい）
        analyze_task_sync(video_id)
        create_highlights_task_sync(video_id)
        
        return {'status': 'success', 'video_id': video_id, 'session_id': video.session_id}
    
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
                message=f"処理中にエラーが発生しました: {str(e)}"
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

# 以下は非同期タスクとして定義（将来的に使用）
@celery.task
def download_task(video_id):
    """動画のダウンロードタスク（非同期版）"""
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

@celery.task
def analyze_task(video_id):
    """動画の解析タスク"""
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

@celery.task
def create_highlights_task(video_id):
    """切り抜き動画の作成タスク"""
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