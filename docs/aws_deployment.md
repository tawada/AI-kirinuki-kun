# AWS環境へのデプロイガイド

このドキュメントでは、AI切り抜きくんをAWS環境にデプロイする方法について詳しく説明します。

## アーキテクチャ概要

![AWSアーキテクチャ](aws_architecture.png)

## 前提条件

- AWSアカウント
- IAM権限（ECS, ECR, RDS, S3, CloudFront, ElastiCache, など）
- AWS CLI（設定済み）
- Docker
- Terraform（またはCloudFormation）

## デプロイ手順

### 1. インフラストラクチャのセットアップ

#### a. Terraformを使用する場合

```bash
# Terraformディレクトリに移動
cd terraform

# 初期化
terraform init

# 実行計画の確認
terraform plan

# インフラストラクチャのデプロイ
terraform apply
```

適用後、以下のリソースが作成されます：
- VPCとサブネット
- セキュリティグループ
- ECRリポジトリ
- ECSクラスター
- RDSインスタンス
- ElastiCacheクラスター
- S3バケット
- CloudFrontディストリビューション
- ALB
- 各種IAMロール

### 2. コンテナイメージのビルドとプッシュ

#### a. アプリケーションイメージ

```bash
# ECRへのログイン
aws ecr get-login-password --region <REGION> | docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com

# イメージのビルド
docker build -t <ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/ai-kirinuki-app:latest -f docker/Dockerfile.app .

# イメージのプッシュ
docker push <ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/ai-kirinuki-app:latest
```

#### b. ワーカーイメージ

```bash
# イメージのビルド
docker build -t <ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/ai-kirinuki-worker:latest -f docker/Dockerfile.worker .

# イメージのプッシュ
docker push <ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/ai-kirinuki-worker:latest
```

### 3. ECSサービスのデプロイ

#### a. タスク定義の更新

タスク定義には以下の環境変数が必要です：

- `DATABASE_URL`: RDS接続文字列
- `CELERY_BROKER_URL`: ElastiCache Redis接続URL
- `CELERY_RESULT_BACKEND`: 同上
- `S3_UPLOAD_BUCKET`: アップロード用S3バケット
- `S3_OUTPUT_BUCKET`: 出力用S3バケット
- `SECRET_KEY`: Flaskセッション用の秘密鍵
- その他アプリケーションに必要な環境変数

#### b. サービスの作成

Terraformで作成されたECSサービスは、自動的に新しいタスク定義をデプロイします。

### 4. データベースのマイグレーション

初回デプロイ時にはデータベースのマイグレーションが必要です：

```bash
# ECSタスクを使ってマイグレーションを実行
aws ecs run-task \
  --cluster ai-kirinuki-cluster \
  --task-definition ai-kirinuki-migration \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxxxxxxx],securityGroups=[sg-xxxxxxxx],assignPublicIp=ENABLED}" \
  --launch-type FARGATE
```

### 5. S3バケットのライフサイクル設定

S3バケットには適切なライフサイクルポリシーを設定することをお勧めします：

```bash
# uploads/バケットの設定
aws s3api put-bucket-lifecycle-configuration \
  --bucket ai-kirinuki-uploads \
  --lifecycle-configuration file://s3-lifecycle-uploads.json

# outputs/バケットの設定
aws s3api put-bucket-lifecycle-configuration \
  --bucket ai-kirinuki-outputs \
  --lifecycle-configuration file://s3-lifecycle-outputs.json
```

### 6. CloudFrontの設定

CloudFrontディストリビューションを使用して、生成された動画を効率的に配信します：

```bash
# OAIの作成（すでにTerraformで作成されている場合は不要）
aws cloudfront create-cloud-front-origin-access-identity \
  --cloud-front-origin-access-identity-config CallerReference=ai-kirinuki,Comment="OAI for AI Kirinuki"
```

### 7. セキュリティ設定の確認

デプロイ後、以下のセキュリティ設定を確認してください：

- RDS: 暗号化が有効になっていること
- S3: バケットポリシーが適切に設定されていること
- セキュリティグループ: 最小権限原則に基づいて設定されていること
- IAMロール: 必要最小限の権限が付与されていること

## スケーリングの設定

### 1. Webアプリケーションのスケーリング

```bash
# オートスケーリングポリシーの作成
aws application-autoscaling put-scaling-policy \
  --service-namespace ecs \
  --scalable-dimension ecs:service:DesiredCount \
  --resource-id service/ai-kirinuki-cluster/ai-kirinuki-app \
  --policy-name cpu-tracking \
  --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration file://app-scaling-policy.json
```

### 2. ワーカーのスケーリング

```bash
# キュー長に基づくスケーリングポリシーの作成
aws application-autoscaling put-scaling-policy \
  --service-namespace ecs \
  --scalable-dimension ecs:service:DesiredCount \
  --resource-id service/ai-kirinuki-cluster/ai-kirinuki-worker \
  --policy-name queue-length-tracking \
  --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration file://worker-scaling-policy.json
```

## モニタリングとログ

### 1. CloudWatchダッシュボードの作成

```bash
# ダッシュボードの作成
aws cloudwatch put-dashboard \
  --dashboard-name AI-Kirinuki-Dashboard \
  --dashboard-body file://cloudwatch-dashboard.json
```

### 2. アラームの設定

重要なメトリクスに対してアラームを設定します：

```bash
# エラー率アラームの作成
aws cloudwatch put-metric-alarm \
  --alarm-name AI-Kirinuki-HighErrorRate \
  --alarm-description "High error rate in AI Kirinuki application" \
  --metric-name 5XXError \
  --namespace AWS/ApplicationELB \
  --statistic Sum \
  --period 60 \
  --threshold 5 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=LoadBalancer,Value=<ALB_ARN> \
  --evaluation-periods 1 \
  --alarm-actions <SNS_TOPIC_ARN>
```

## トラブルシューティング

### 1. ログの確認

```bash
# アプリケーションログの表示
aws logs get-log-events \
  --log-group-name /ecs/ai-kirinuki-app \
  --log-stream-name <LOG_STREAM_NAME>

# ワーカーログの表示
aws logs get-log-events \
  --log-group-name /ecs/ai-kirinuki-worker \
  --log-stream-name <LOG_STREAM_NAME>
```

### 2. タスク定義の確認

```bash
# 最新のタスク定義を確認
aws ecs describe-task-definition \
  --task-definition ai-kirinuki-app:ACTIVE
```

### 3. コンテナインスタンスの確認

```bash
# 実行中のタスクを確認
aws ecs list-tasks \
  --cluster ai-kirinuki-cluster
```

## バックアップと復元

### 1. RDSバックアップ

```bash
# 手動スナップショットの作成
aws rds create-db-snapshot \
  --db-instance-identifier ai-kirinuki-db \
  --db-snapshot-identifier ai-kirinuki-snapshot-$(date +%Y%m%d)
```

### 2. S3バックアップ

```bash
# バケット間コピーの例
aws s3 sync s3://ai-kirinuki-outputs s3://ai-kirinuki-backup/outputs-$(date +%Y%m%d)
```

## メンテナンスとアップデート

### 1. アプリケーションの更新

新しいバージョンをデプロイするには：

1. 新しいイメージをビルドしてECRにプッシュ
2. ECSサービスを更新

```bash
# サービスの更新（新しいデプロイを強制）
aws ecs update-service \
  --cluster ai-kirinuki-cluster \
  --service ai-kirinuki-app \
  --force-new-deployment
```

### 2. インフラストラクチャの更新

Terraformを使用している場合：

```bash
cd terraform
terraform apply
```

## コスト最適化

### 1. Fargateスポットの活用

ワーカータスクにはFargate Spotを使用して、コストを最大70%削減できます。

### 2. S3ストレージクラスの最適化

長期保存が必要なファイルに対しては、S3 Intelligent-TieringまたはS3 Glacier Deep Archiveを検討してください。

### 3. リザーブドインスタンス

RDSやElastiCacheなど、長期的に使用するサービスにはリザーブドインスタンスの購入を検討してください。

## セキュリティのベストプラクティス

### 1. 定期的なセキュリティスキャン

```bash
# ECRイメージの脆弱性スキャン
aws ecr start-image-scan \
  --repository-name ai-kirinuki-app \
  --image-id imageTag=latest
```

### 2. IAMポリシーの最小権限原則

すべてのIAMロールで最小権限原則を徹底し、定期的に見直しを行ってください。

### 3. 暗号化の徹底

転送中および保存中のデータはすべて暗号化してください。