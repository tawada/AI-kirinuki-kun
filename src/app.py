import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from werkzeug.utils import secure_filename
import uuid
from src.youtube_downloader import download_video
from src.video_processor import process_video, get_video_highlights
from dotenv import load_dotenv

# 環境変数のロード
load_dotenv()

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.secret_key = os.getenv('SECRET_KEY', 'dev_key')

# アップロードされた動画と生成された動画の保存先
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads')
OUTPUT_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'outputs')

for folder in [UPLOAD_FOLDER, OUTPUT_FOLDER]:
    if not os.path.exists(folder):
        os.makedirs(folder)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    youtube_url = request.form.get('youtube_url')
    
    if not youtube_url:
        flash('YouTubeのURLを入力してください')
        return redirect(url_for('index'))
    
    # セッションID（ユニークな処理ID）の生成
    session_id = str(uuid.uuid4())
    
    try:
        # 動画のダウンロード
        video_path = download_video(youtube_url, UPLOAD_FOLDER, session_id)
        
        # 動画の解析と切り抜き処理
        highlights = get_video_highlights(video_path)
        output_path = process_video(video_path, highlights, OUTPUT_FOLDER, session_id)
        
        # 結果ページへリダイレクト
        return redirect(url_for('result', session_id=session_id))
        
    except Exception as e:
        flash(f'エラーが発生しました: {str(e)}')
        return redirect(url_for('index'))

@app.route('/status/<session_id>')
def status(session_id):
    # 処理状況の確認ロジックを実装（実際の実装では処理状況を保存・管理する仕組みが必要）
    # ここではダミーデータを返します
    return jsonify({
        'status': 'processing',
        'progress': 50,
        'message': '動画を解析中...'
    })

@app.route('/result/<session_id>')
def result(session_id):
    # 出力ファイル名を確認（session_idを使用）
    output_filename = f"{session_id}.mp4"
    output_path = os.path.join(OUTPUT_FOLDER, output_filename)
    
    if not os.path.exists(output_path):
        flash('動画の処理中にエラーが発生しました')
        return redirect(url_for('index'))
    
    return render_template('result.html', session_id=session_id)

@app.route('/download/<session_id>')
def download(session_id):
    output_filename = f"{session_id}.mp4"
    return send_from_directory(directory=OUTPUT_FOLDER, path=output_filename, as_attachment=True)

@app.route('/video/<session_id>')
def video(session_id):
    output_filename = f"{session_id}.mp4"
    return send_from_directory(directory=OUTPUT_FOLDER, path=output_filename)

if __name__ == '__main__':
    app.run(debug=True)