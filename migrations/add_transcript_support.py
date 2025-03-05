"""add transcript support

Revision ID: 1234567890ab
Revises: 
Create Date: 2023-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '1234567890ab'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # トランスクリプションステータスの追加
    op.execute("ALTER TYPE processstatus ADD VALUE 'transcribing' AFTER 'downloading'")
    
    # Videoテーブルにtranscriptカラムを追加
    op.add_column('videos', sa.Column('transcript', sa.Text(), nullable=True))
    
    # TranscriptSegmentテーブルの作成
    op.create_table('transcript_segments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('video_id', sa.Integer(), nullable=False),
        sa.Column('start_time', sa.Float(), nullable=False),
        sa.Column('end_time', sa.Float(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

def downgrade():
    # TranscriptSegmentテーブルを削除
    op.drop_table('transcript_segments')
    
    # Videoテーブルからtranscriptカラムを削除
    op.drop_column('videos', 'transcript')
    
    # トランスクリプションステータスの削除はサポートされていないため実装しない