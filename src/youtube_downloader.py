import os
import re
import yt_dlp
import tempfile
import logging
from typing import Optional

logger = logging.getLogger(__name__)

def is_valid_youtube_url(url: str) -> bool:
    """YouTubeのURLが有効かチェックする"""
    youtube_regex = r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
    return bool(re.match(youtube_regex, url))

def download_video(youtube_url: str, download_dir: str, session_id: str, storage_manager=None) -> str:
    """
    YouTubeの動画をダウンロードする
    
    Args:
        youtube_url: YouTubeのURL
        download_dir: ダウンロード先ディレクトリ（ローカルモード時のみ使用）
        session_id: セッションID（ファイル名生成用）
        storage_manager: ストレージマネージャー（S3対応時に使用）
        
    Returns:
        ダウンロードしたファイルのパス
    """
    if not is_valid_youtube_url(youtube_url):
        raise ValueError("無効なYouTube URLです")
    
    try:
        # セッションIDを使用してファイル名を生成
        file_name = f"{session_id}.mp4"
        
        # S3モードかローカルモードかを判断
        use_s3 = storage_manager is not None and storage_manager.use_s3
        
        if use_s3:
            # S3モードの場合は一時ファイルにダウンロード
            temp_dir = tempfile.gettempdir()
            temp_file_path = os.path.join(temp_dir, file_name)
            download_path = temp_file_path
        else:
            # ローカルモードの場合は直接指定のディレクトリにダウンロード
            download_path = os.path.join(download_dir, file_name)
        
        # yt-dlpのオプション設定
        ydl_opts = {
            'format': 'best[ext=mp4]/best',  # 最高品質のmp4を選択、なければ最高品質
            'outtmpl': download_path,        # 出力ファイルパス
            'quiet': False,                  # 進捗情報を表示
            'no_warnings': False,            # 警告を表示
            'ignoreerrors': False,           # エラーを無視しない
            'noplaylist': True,              # プレイリストをダウンロードしない
            'geo_bypass': True,              # 地域制限をバイパス
            'nocheckcertificate': True,      # SSL証明書チェックを無効化
        }
        
        # 動画をダウンロード
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"動画のダウンロードを開始: {youtube_url}")
            ydl.download([youtube_url])
        
        # ファイルが正常に作成されたか確認
        if not os.path.exists(download_path):
            raise ValueError("動画のダウンロードに失敗しました")
        
        # S3モードの場合はS3にアップロード
        if use_s3:
            logger.info(f"S3にファイルをアップロード: {file_name}")
            s3_path = storage_manager.save_upload_file(download_path, file_name)
            # 一時ファイルを削除
            os.remove(download_path)
            return s3_path
        else:
            return download_path
    
    except Exception as e:
        logger.error(f"動画のダウンロード中にエラーが発生しました: {str(e)}")
        raise Exception(f"動画のダウンロード中にエラーが発生しました: {str(e)}")