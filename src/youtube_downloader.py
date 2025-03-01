import os
import re
import yt_dlp

def is_valid_youtube_url(url):
    """YouTubeのURLが有効かチェックする"""
    youtube_regex = r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
    return bool(re.match(youtube_regex, url))

def download_video(youtube_url, download_dir, session_id):
    """YouTubeの動画をダウンロードする"""
    if not is_valid_youtube_url(youtube_url):
        raise ValueError("無効なYouTube URLです")
    
    try:
        # セッションIDを使用してファイル名を生成
        file_name = f"{session_id}.mp4"
        file_path = os.path.join(download_dir, file_name)
        
        # yt-dlpのオプション設定
        ydl_opts = {
            'format': 'best[ext=mp4]/best',  # 最高品質のmp4を選択、なければ最高品質
            'outtmpl': file_path,           # 出力ファイルパス
            'quiet': False,                 # 進捗情報を表示
            'no_warnings': False,           # 警告を表示
            'ignoreerrors': False,          # エラーを無視しない
            'noplaylist': True,             # プレイリストをダウンロードしない
            'geo_bypass': True,             # 地域制限をバイパス
            'nocheckcertificate': True,     # SSL証明書チェックを無効化
        }
        
        # 動画をダウンロード
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([youtube_url])
        
        # ファイルが正常に作成されたか確認
        if not os.path.exists(file_path):
            raise ValueError("動画のダウンロードに失敗しました")
        
        return file_path
    
    except Exception as e:
        raise Exception(f"動画のダウンロード中にエラーが発生しました: {str(e)}")