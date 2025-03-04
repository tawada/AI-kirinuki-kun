import os
import boto3
import logging
from botocore.exceptions import ClientError
from typing import Optional, Union, BinaryIO

logger = logging.getLogger(__name__)

class StorageManager:
    """ストレージ操作を抽象化するクラス（ローカルファイルシステムとS3）"""
    
    def __init__(self, use_s3: bool = False, upload_bucket: Optional[str] = None, 
                 output_bucket: Optional[str] = None, region: str = 'ap-northeast-1'):
        """
        ストレージマネージャーの初期化
        
        Args:
            use_s3: S3を使用するかどうか
            upload_bucket: アップロード用S3バケット名
            output_bucket: 出力用S3バケット名
            region: AWSリージョン
        """
        self.use_s3 = use_s3
        self.upload_bucket = upload_bucket
        self.output_bucket = output_bucket
        self.region = region
        
        # ローカルストレージのパス
        self.local_upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads')
        self.local_output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'outputs')
        
        # ローカルディレクトリの作成
        for directory in [self.local_upload_dir, self.local_output_dir]:
            if not os.path.exists(directory):
                os.makedirs(directory)
        
        # S3クライアントの初期化（必要な場合）
        self.s3_client = None
        if self.use_s3:
            if not upload_bucket or not output_bucket:
                raise ValueError("S3使用時はupload_bucketとoutput_bucketが必要です")
            self.s3_client = boto3.client('s3', region_name=self.region)
    
    def save_upload_file(self, file_data: Union[str, BinaryIO], filename: str) -> str:
        """
        アップロードファイルを保存する
        
        Args:
            file_data: ファイルデータまたはファイルパス
            filename: 保存するファイル名
            
        Returns:
            保存されたファイルの場所を示すパスまたはURI
        """
        if self.use_s3:
            return self._save_to_s3(file_data, filename, self.upload_bucket)
        else:
            return self._save_to_local(file_data, filename, self.local_upload_dir)
    
    def save_output_file(self, file_data: Union[str, BinaryIO], filename: str) -> str:
        """
        出力ファイルを保存する
        
        Args:
            file_data: ファイルデータまたはファイルパス
            filename: 保存するファイル名
            
        Returns:
            保存されたファイルの場所を示すパスまたはURI
        """
        if self.use_s3:
            return self._save_to_s3(file_data, filename, self.output_bucket)
        else:
            return self._save_to_local(file_data, filename, self.local_output_dir)
    
    def get_upload_file(self, filename: str) -> str:
        """
        アップロードファイルの取得（パスまたは一時ファイル）
        
        Args:
            filename: ファイル名
            
        Returns:
            ファイルパス（ローカルの場合は実際のパス、S3の場合は一時ファイルのパス）
        """
        if self.use_s3:
            return self._get_from_s3(filename, self.upload_bucket)
        else:
            return os.path.join(self.local_upload_dir, filename)
    
    def get_output_file(self, filename: str) -> str:
        """
        出力ファイルの取得（パスまたは一時ファイル）
        
        Args:
            filename: ファイル名
            
        Returns:
            ファイルパス（ローカルの場合は実際のパス、S3の場合は一時ファイルのパス）
        """
        if self.use_s3:
            return self._get_from_s3(filename, self.output_bucket)
        else:
            return os.path.join(self.local_output_dir, filename)
    
    def get_file_url(self, filename: str, is_output: bool = True) -> str:
        """
        ファイルのURLを取得
        
        Args:
            filename: ファイル名
            is_output: 出力ファイルかどうか（Falseならアップロードファイル）
            
        Returns:
            ファイルのURL
        """
        if self.use_s3:
            bucket = self.output_bucket if is_output else self.upload_bucket
            return f"https://{bucket}.s3.{self.region}.amazonaws.com/{filename}"
        else:
            # ローカル環境ではFlaskのルートを想定した相対パス
            folder = 'outputs' if is_output else 'uploads'
            return f"/{folder}/{filename}"
    
    def delete_file(self, filename: str, is_output: bool = True) -> bool:
        """
        ファイルを削除
        
        Args:
            filename: ファイル名
            is_output: 出力ファイルかどうか（Falseならアップロードファイル）
            
        Returns:
            成功したかどうか
        """
        try:
            if self.use_s3:
                bucket = self.output_bucket if is_output else self.upload_bucket
                self.s3_client.delete_object(Bucket=bucket, Key=filename)
            else:
                folder = self.local_output_dir if is_output else self.local_upload_dir
                file_path = os.path.join(folder, filename)
                if os.path.exists(file_path):
                    os.remove(file_path)
            return True
        except Exception as e:
            logger.error(f"ファイル削除中にエラーが発生しました: {str(e)}")
            return False
    
    def _save_to_s3(self, file_data: Union[str, BinaryIO], filename: str, bucket: str) -> str:
        """S3にファイルを保存"""
        try:
            # file_dataがファイルパスの場合
            if isinstance(file_data, str) and os.path.exists(file_data):
                self.s3_client.upload_file(file_data, bucket, filename)
            # file_dataがファイルオブジェクトの場合
            else:
                self.s3_client.upload_fileobj(file_data, bucket, filename)
            
            return f"s3://{bucket}/{filename}"
        except ClientError as e:
            logger.error(f"S3へのファイル保存中にエラーが発生しました: {str(e)}")
            raise
    
    def _save_to_local(self, file_data: Union[str, BinaryIO], filename: str, directory: str) -> str:
        """ローカルにファイルを保存"""
        try:
            output_path = os.path.join(directory, filename)
            
            # file_dataがファイルパスの場合
            if isinstance(file_data, str) and os.path.exists(file_data):
                if file_data != output_path:  # 同じパスでなければコピー
                    with open(file_data, 'rb') as src_file, open(output_path, 'wb') as dest_file:
                        dest_file.write(src_file.read())
            # file_dataがファイルオブジェクトの場合
            else:
                with open(output_path, 'wb') as f:
                    if hasattr(file_data, 'read'):
                        # ファイルオブジェクトの場合
                        f.write(file_data.read())
                    else:
                        # バイナリデータの場合
                        f.write(file_data)
            
            return output_path
        except Exception as e:
            logger.error(f"ローカルへのファイル保存中にエラーが発生しました: {str(e)}")
            raise
    
    def _get_from_s3(self, filename: str, bucket: str) -> str:
        """S3からファイルを取得して一時ファイルに保存"""
        try:
            # 一時ディレクトリにダウンロード
            tmp_dir = os.path.join('/tmp', 'ai-kirinuki')
            if not os.path.exists(tmp_dir):
                os.makedirs(tmp_dir)
            
            local_path = os.path.join(tmp_dir, filename)
            self.s3_client.download_file(bucket, filename, local_path)
            
            return local_path
        except ClientError as e:
            logger.error(f"S3からのファイル取得中にエラーが発生しました: {str(e)}")
            raise