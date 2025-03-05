from datetime import datetime
from enum import Enum
import json
from sqlalchemy import Column, Integer, String, Text, DateTime, Float, Boolean, ForeignKey, Enum as SQLAEnum
from sqlalchemy.orm import relationship
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class ProcessStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    TRANSCRIBING = "transcribing"
    ANALYZING = "analyzing"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class Video(db.Model):
    __tablename__ = 'videos'
    
    id = Column(Integer, primary_key=True)
    youtube_url = Column(String(255), nullable=False)
    session_id = Column(String(36), unique=True, nullable=False)
    title = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    duration = Column(Float, nullable=True)  # 秒単位での動画の長さ
    thumbnail_url = Column(String(255), nullable=True)
    original_path = Column(String(255), nullable=True)  # ダウンロードされた元動画のパス
    output_path = Column(String(255), nullable=True)  # 生成された切り抜き動画のパス
    transcript = Column(Text, nullable=True)  # 文字起こし結果
    status = Column(SQLAEnum(ProcessStatus), default=ProcessStatus.PENDING)
    error_message = Column(Text, nullable=True)
    progress = Column(Integer, default=0)  # 処理進捗を0-100で表す
    current_task_id = Column(String(255), nullable=True)  # 現在実行中のタスクID
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # リレーションシップ
    highlights = relationship("Highlight", back_populates="video", cascade="all, delete-orphan")
    process_logs = relationship("ProcessLog", back_populates="video", cascade="all, delete-orphan")
    transcript_segments = relationship("TranscriptSegment", back_populates="video", cascade="all, delete-orphan")
    
    def to_dict(self):
        return {
            'id': self.id,
            'youtube_url': self.youtube_url,
            'session_id': self.session_id,
            'title': self.title,
            'description': self.description,
            'duration': self.duration,
            'thumbnail_url': self.thumbnail_url,
            'transcript': self.transcript,
            'status': self.status.value,
            'progress': self.progress,
            'current_task_id': self.current_task_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class Highlight(db.Model):
    __tablename__ = 'highlights'
    
    id = Column(Integer, primary_key=True)
    video_id = Column(Integer, ForeignKey('videos.id'), nullable=False)
    start_time = Column(Float, nullable=False)  # ハイライト開始時間（秒）
    end_time = Column(Float, nullable=False)  # ハイライト終了時間（秒）
    importance_score = Column(Float, nullable=True)  # 重要度スコア
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # リレーションシップ
    video = relationship("Video", back_populates="highlights")
    
    def to_dict(self):
        return {
            'id': self.id,
            'video_id': self.video_id,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'importance_score': self.importance_score,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class ProcessLog(db.Model):
    __tablename__ = 'process_logs'
    
    id = Column(Integer, primary_key=True)
    video_id = Column(Integer, ForeignKey('videos.id'), nullable=False)
    status = Column(SQLAEnum(ProcessStatus), nullable=False)
    message = Column(Text, nullable=True)
    details = Column(Text, nullable=True)  # JSON形式で詳細情報を保存
    task_id = Column(String(255), nullable=True)  # 関連するタスクID
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # リレーションシップ
    video = relationship("Video", back_populates="process_logs")
    
    def set_details(self, details_dict):
        self.details = json.dumps(details_dict)
    
    def get_details(self):
        if self.details:
            return json.loads(self.details)
        return {}
    
    def to_dict(self):
        return {
            'id': self.id,
            'video_id': self.video_id,
            'status': self.status.value,
            'message': self.message,
            'details': self.get_details(),
            'task_id': self.task_id,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
        
class TranscriptSegment(db.Model):
    __tablename__ = 'transcript_segments'
    
    id = Column(Integer, primary_key=True)
    video_id = Column(Integer, ForeignKey('videos.id'), nullable=False)
    start_time = Column(Float, nullable=False)  # 開始時間（秒）
    end_time = Column(Float, nullable=False)    # 終了時間（秒）
    text = Column(Text, nullable=False)         # セグメントのテキスト
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # リレーションシップ
    video = relationship("Video", back_populates="transcript_segments")
    
    def to_dict(self):
        return {
            'id': self.id,
            'video_id': self.video_id,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'text': self.text,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }