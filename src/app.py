import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory, abort
from werkzeug.utils import secure_filename
import uuid
from src.youtube_downloader import is_valid_youtube_url
from src.models import db, Video, Highlight, ProcessLog, ProcessStatus
from src.tasks import process_video_task, configure_celery
from src.db_manager import init_db
from dotenv import load_dotenv

# 環境変数のロード
load_dotenv()

def create_app():
    app = Flask(__name__, template_folder='../templates', static_folder='../static')
    
    # アプリケーション設定
    app.secret_key = os.getenv('SECRET_KEY', 'dev_key')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///../instance/kirinuki.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['CELERY_BROKER_URL'] = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
    app.config['CELERY_RESULT_BACKEND'] = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
    
    # アップロードされた動画と生成された動画の保存先
    app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads')
    app.config['OUTPUT_FOLDER'] = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'outputs')
    
    # 必要なディレクトリの作成
    for folder in [app.config['UPLOAD_FOLDER'], app.config['OUTPUT_FOLDER']]:
        if not os.path.exists(folder):
            os.makedirs(folder)
    
    # データベースの初期化
    init_db(app)
    
    # Celeryの設定
    configure_celery(app)
    
    return app

app = create_app()

@app.route('/')
def index():
    """トップページ"""
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    """動画処理のリクエスト受付"""
    youtube_url = request.form.get('youtube_url')
    
    if not youtube_url:
        flash('YouTubeのURLを入力してください')
        return redirect(url_for('index'))
    
    if not is_valid_youtube_url(youtube_url):
        flash('有効なYouTube URLを入力してください')
        return redirect(url_for('index'))
    
    # セッションID（ユニークな処理ID）の生成
    session_id = str(uuid.uuid4())
    
    try:
        # データベースにビデオレコードを作成
        new_video = Video(
            youtube_url=youtube_url,
            session_id=session_id,
            status=ProcessStatus.PENDING,
            progress=0
        )
        db.session.add(new_video)
        db.session.commit()
        
        # 処理開始のログを記録
        log = ProcessLog(
            video_id=new_video.id,
            status=ProcessStatus.PENDING,
            message="動画処理リクエストを受け付けました"
        )
        db.session.add(log)
        db.session.commit()
        
        # Celeryタスクを非同期に実行
        process_video_task.delay(new_video.id)
        
        # 処理状況確認ページへリダイレクト
        return redirect(url_for('processing', session_id=session_id))
        
    except Exception as e:
        flash(f'エラーが発生しました: {str(e)}')
        return redirect(url_for('index'))

@app.route('/processing/<session_id>')
def processing(session_id):
    """処理状況確認ページ"""
    # セッションIDからビデオレコードを検索
    video = Video.query.filter_by(session_id=session_id).first()
    
    if not video:
        flash('指定された処理が見つかりません')
        return redirect(url_for('index'))
    
    # 処理が完了している場合は結果ページへリダイレクト
    if video.status == ProcessStatus.COMPLETED:
        return redirect(url_for('result', session_id=session_id))
    
    # 処理中または待機中の場合は処理状況確認ページを表示
    return render_template('processing.html', session_id=session_id, video=video)

@app.route('/status/<session_id>')
def status(session_id):
    """処理状況のAPIエンドポイント"""
    video = Video.query.filter_by(session_id=session_id).first()
    
    if not video:
        return jsonify({
            'status': 'error',
            'message': '指定された処理が見つかりません'
        }), 404
    
    # 最新のログメッセージを取得
    latest_log = ProcessLog.query.filter_by(video_id=video.id).order_by(ProcessLog.created_at.desc()).first()
    message = latest_log.message if latest_log else ""
    
    return jsonify({
        'status': video.status.value,
        'progress': video.progress,
        'message': message,
        'title': video.title,
        'thumbnail_url': video.thumbnail_url
    })

@app.route('/result/<session_id>')
def result(session_id):
    """結果表示ページ"""
    video = Video.query.filter_by(session_id=session_id).first()
    
    if not video:
        flash('指定された処理が見つかりません')
        return redirect(url_for('index'))
    
    # 処理が完了していない場合は処理状況確認ページへリダイレクト
    if video.status != ProcessStatus.COMPLETED:
        return redirect(url_for('processing', session_id=session_id))
    
    # 出力ファイルの存在確認
    output_filename = f"{session_id}.mp4"
    output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)
    
    if not os.path.exists(output_path):
        flash('動画ファイルが見つかりません')
        return redirect(url_for('index'))
    
    # ハイライト情報を取得
    highlights = Highlight.query.filter_by(video_id=video.id).order_by(Highlight.start_time).all()
    
    return render_template('result.html', 
                          session_id=session_id, 
                          video=video, 
                          highlights=highlights)

@app.route('/download/<session_id>')
def download(session_id):
    """動画ダウンロードエンドポイント"""
    video = Video.query.filter_by(session_id=session_id).first()
    
    if not video or video.status != ProcessStatus.COMPLETED:
        abort(404)
    
    output_filename = f"{session_id}.mp4"
    return send_from_directory(directory=app.config['OUTPUT_FOLDER'], path=output_filename, as_attachment=True)

@app.route('/video/<session_id>')
def video(session_id):
    """動画ストリーミングエンドポイント"""
    video = Video.query.filter_by(session_id=session_id).first()
    
    if not video or video.status != ProcessStatus.COMPLETED:
        abort(404)
    
    output_filename = f"{session_id}.mp4"
    return send_from_directory(directory=app.config['OUTPUT_FOLDER'], path=output_filename)

@app.route('/history')
def history():
    """処理履歴一覧ページ"""
    videos = Video.query.order_by(Video.created_at.desc()).limit(20).all()
    return render_template('history.html', videos=videos)

@app.route('/detail/<session_id>')
def detail(session_id):
    """詳細情報ページ"""
    video = Video.query.filter_by(session_id=session_id).first()
    
    if not video:
        flash('指定された処理が見つかりません')
        return redirect(url_for('index'))
    
    # 処理ログを取得
    logs = ProcessLog.query.filter_by(video_id=video.id).order_by(ProcessLog.created_at).all()
    
    # ハイライト情報を取得
    highlights = Highlight.query.filter_by(video_id=video.id).order_by(Highlight.start_time).all()
    
    return render_template('detail.html', video=video, logs=logs, highlights=highlights)

if __name__ == '__main__':
    app.run(debug=True)