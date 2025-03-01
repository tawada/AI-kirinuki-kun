import os
from pytube import YouTube
import re

def is_valid_youtube_url(url):
    """YouTubeのURLが有効かチェックする"""
    youtube_regex = r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
    return bool(re.match(youtube_regex, url))

def download_video(youtube_url, download_dir, session_id):
    """YouTubeの動画をダウンロードする"""
    if not is_valid_youtube_url(youtube_url):
        raise ValueError("無効なYouTube URLです")
    
    try:
        yt = YouTube(youtube_url)
        
        # 最高画質の動画をダウンロード
        video_stream = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc().first()
        
        if not video_stream:
            raise ValueError("ダウンロード可能な動画ストリームが見つかりませんでした")
        
        # セッションIDを使用してファイル名を生成
        file_name = f"{session_id}.mp4"
        file_path = os.path.join(download_dir, file_name)
        
        # 動画をダウンロード
        video_stream.download(download_dir, filename=file_name)
        
        return file_path
    
    except Exception as e:
        raise Exception(f"動画のダウンロード中にエラーが発生しました: {str(e)}")