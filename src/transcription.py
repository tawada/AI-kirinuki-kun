import os
import whisper
import torch
from typing import Dict, List, Tuple
import tempfile
from moviepy.editor import VideoFileClip

# 音声認識モデルのサイズ（'tiny', 'base', 'small', 'medium', 'large'）
WHISPER_MODEL_SIZE = "small"

def extract_audio(video_path: str) -> str:
    """
    動画ファイルから音声を抽出する

    Args:
        video_path: 動画ファイルのパス

    Returns:
        抽出した音声ファイルの一時パス
    """
    # FFmpegの存在チェック
    try:
        import subprocess
        result = subprocess.run(['ffmpeg', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            raise Exception("FFmpegの実行時にエラーが発生しました。FFmpegが正しくインストールされているか確認してください。")
    except FileNotFoundError:
        raise Exception("FFmpegがインストールされていないか、パスが通っていません。インストール方法はREADMEを参照してください。")
    
    # 一時ファイルを作成
    temp_audio = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    temp_audio_path = temp_audio.name
    temp_audio.close()
    
    try:
        # 動画を読み込み
        video = VideoFileClip(video_path)
        
        # 音声トラックが存在することを確認
        if video.audio is None:
            raise Exception("動画に音声トラックが含まれていません。")
        
        # 音声を抽出して保存
        video.audio.write_audiofile(temp_audio_path, 
                                   codec='pcm_s16le',  # wav形式
                                   ffmpeg_params=['-ac', '1'],  # モノラル
                                   verbose=False,
                                   logger=None)
        
        # リソースを解放
        video.close()
        
        return temp_audio_path
    
    except Exception as e:
        # エラー時は一時ファイルを削除
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)
        raise Exception(f"音声抽出中にエラーが発生しました: {str(e)}")

def transcribe_audio(audio_path: str) -> Dict:
    """
    音声ファイルを文字起こしする

    Args:
        audio_path: 音声ファイルのパス

    Returns:
        文字起こし結果の辞書（Whisper APIの出力形式）
    """
    try:
        # GPUが利用可能か確認
        device = "cuda" if torch.cuda.is_available() else "cpu"
        
        # Whisperモデルのロード
        model = whisper.load_model(WHISPER_MODEL_SIZE, device=device)
        
        # 文字起こしを実行
        result = model.transcribe(
            audio_path,
            language="ja",  # 日本語を指定（自動検出も可能）
            fp16=torch.cuda.is_available(),  # GPUがある場合はfp16を使用
            verbose=False
        )
        
        return result
    
    except Exception as e:
        raise Exception(f"文字起こし中にエラーが発生しました: {str(e)}")
    
    finally:
        # 一時ファイルを削除
        if os.path.exists(audio_path):
            os.remove(audio_path)

def process_transcript(transcript_result: Dict) -> Tuple[str, List[Dict]]:
    """
    Whisperの出力結果を処理し、テキストとセグメント情報を抽出する

    Args:
        transcript_result: Whisperの出力結果

    Returns:
        (完全なテキスト, セグメントのリスト)
    """
    try:
        # 完全なテキスト
        full_text = transcript_result.get("text", "")
        
        # セグメント情報（時間情報付きのテキスト断片）
        segments = []
        for segment in transcript_result.get("segments", []):
            segments.append({
                "start_time": segment.get("start", 0),
                "end_time": segment.get("end", 0),
                "text": segment.get("text", "")
            })
        
        return full_text, segments
    
    except Exception as e:
        raise Exception(f"文字起こし結果の処理中にエラーが発生しました: {str(e)}")

def transcribe_video(video_path: str) -> Tuple[str, List[Dict]]:
    """
    動画ファイルを文字起こしする（メイン関数）

    Args:
        video_path: 動画ファイルのパス

    Returns:
        (完全なテキスト, セグメントのリスト)
    """
    try:
        # 音声の抽出
        audio_path = extract_audio(video_path)
        
        # 文字起こしの実行
        transcript_result = transcribe_audio(audio_path)
        
        # 結果の処理
        return process_transcript(transcript_result)
    
    except Exception as e:
        raise Exception(f"動画の文字起こし中にエラーが発生しました: {str(e)}")