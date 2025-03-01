# AI切り抜きくん (AI-kirinuki-kun)

YouTubeの動画をAIで自動解析し、重要なシーンを切り抜いた動画を作成するWebアプリケーションです。

## 機能

- YouTubeの動画URLからの自動ダウンロード
- AIによる動画解析と重要シーンの抽出
- 切り抜き動画の自動生成
- 生成された動画のプレビューとダウンロード

## セットアップ方法

### 前提条件

- Python 3.8以上
- FFmpeg（動画処理に必要）

### インストール

1. リポジトリをクローン
   ```
   git clone https://github.com/yourusername/AI-kirinuki-kun.git
   cd AI-kirinuki-kun
   ```

2. 仮想環境を作成して有効化（推奨）
   ```
   python -m venv venv
   source venv/bin/activate  # Linuxの場合
   venv\Scripts\activate     # Windowsの場合
   ```

3. 依存関係のインストール
   ```
   pip install -r requirements.txt
   ```

4. 環境変数の設定
   ```
   cp .env.example .env
   ```
   `.env`ファイルを編集して必要な環境変数を設定してください。

### 実行方法

アプリケーションを起動するには、以下のコマンドを実行します。

```
python run.py
```

ブラウザで http://localhost:5000 にアクセスするとアプリケーションが表示されます。

## 使用技術

- バックエンド: Flask (Python)
- 動画処理: MoviePy, FFmpeg
- 動画ダウンロード: PyTube
- AI解析: Transformers, PyTorch
- フロントエンド: HTML, CSS, JavaScript, Bootstrap

## 注意事項

- このアプリケーションは個人利用を目的としています。
- 著作権に配慮して使用してください。
- サーバーのリソースや帯域幅に応じて、長い動画の処理には時間がかかる場合があります。

## ライセンス

MITライセンス