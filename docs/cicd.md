# CI/CD パイプライン構築ガイド

このドキュメントでは、AI切り抜きくんのための継続的インテグレーション/継続的デリバリー（CI/CD）パイプラインの構築方法について説明します。

## CI/CDパイプライン概要

![CI/CDパイプライン](cicd_pipeline.png)

AI切り抜きくんのCI/CDパイプラインは、以下のコンポーネントで構成されています：

1. **ソースコード管理**: GitHub
2. **ビルドプロセス**: AWS CodeBuild
3. **デプロイメント**: AWS CodePipeline & AWS ECS
4. **監視**: AWS CloudWatch

## 前提条件

- AWSアカウント
- GitHubリポジトリ（AI切り抜きくんのソースコード）
- 適切なIAM権限

## 構築手順

### 1. CodeBuildプロジェクトの作成

#### a. マネジメントコンソールから作成する場合

1. AWSマネジメントコンソールにログイン
2. CodeBuildサービスに移動
3. 「ビルドプロジェクトを作成する」を選択
4. 以下の設定を行う：
   - **プロジェクト名**: `ai-kirinuki-build`
   - **ソースプロバイダ**: GitHub
   - **リポジトリ**: リポジトリのURLを入力
   - **環境イメージ**: マネージド型イメージ
   - **オペレーティングシステム**: Amazon Linux 2
   - **ランタイム**: Standard
   - **イメージ**: aws/codebuild/amazonlinux2-x86_64-standard:3.0
   - **特権付与**: はい（Dockerイメージビルドに必要）
   - **サービスロール**: 新しいサービスロールを作成または既存のものを使用
   - **ビルド仕様**: buildspec.ymlを使用
   - **アーティファクト**: なし（ECRにプッシュするため）
   - **ログ**: CloudWatchログを有効化

#### b. AWS CLIから作成する場合

```bash
# サービスロールの作成（または既存のものを使用）
aws iam create-role --role-name CodeBuildServiceRole \
  --assume-role-policy-document file://codebuild-trust-policy.json

# ポリシーのアタッチ
aws iam attach-role-policy --role-name CodeBuildServiceRole \
  --policy-arn arn:aws:iam::aws:policy/AmazonECR-FullAccess

aws iam attach-role-policy --role-name CodeBuildServiceRole \
  --policy-arn arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess

# CodeBuildプロジェクトの作成
aws codebuild create-project \
  --name ai-kirinuki-build \
  --source type=GITHUB,location=https://github.com/yourusername/AI-kirinuki-kun.git \
  --environment type=LINUX_CONTAINER,image=aws/codebuild/amazonlinux2-x86_64-standard:3.0,computeType=BUILD_GENERAL1_SMALL,privilegedMode=true \
  --service-role CodeBuildServiceRole \
  --artifacts type=NO_ARTIFACTS
```

### 2. buildspec.yml の作成

プロジェクトのルートディレクトリに以下の内容の `buildspec.yml` ファイルを作成します：

```yaml
version: 0.2

phases:
  pre_build:
    commands:
      - echo Logging in to Amazon ECR...
      - aws ecr get-login-password --region $AWS_DEFAULT_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_DEFAULT_REGION.amazonaws.com
      - COMMIT_HASH=$(echo $CODEBUILD_RESOLVED_SOURCE_VERSION | cut -c 1-7)
      - IMAGE_TAG=${COMMIT_HASH:=latest}
  build:
    commands:
      - echo Building the Docker images...
      - docker build -t $AWS_ACCOUNT_ID.dkr.ecr.$AWS_DEFAULT_REGION.amazonaws.com/ai-kirinuki-app:$IMAGE_TAG -t $AWS_ACCOUNT_ID.dkr.ecr.$AWS_DEFAULT_REGION.amazonaws.com/ai-kirinuki-app:latest -f docker/Dockerfile.app .
      - docker build -t $AWS_ACCOUNT_ID.dkr.ecr.$AWS_DEFAULT_REGION.amazonaws.com/ai-kirinuki-worker:$IMAGE_TAG -t $AWS_ACCOUNT_ID.dkr.ecr.$AWS_DEFAULT_REGION.amazonaws.com/ai-kirinuki-worker:latest -f docker/Dockerfile.worker .
  post_build:
    commands:
      - echo Pushing the Docker images...
      - docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_DEFAULT_REGION.amazonaws.com/ai-kirinuki-app:$IMAGE_TAG
      - docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_DEFAULT_REGION.amazonaws.com/ai-kirinuki-app:latest
      - docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_DEFAULT_REGION.amazonaws.com/ai-kirinuki-worker:$IMAGE_TAG
      - docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_DEFAULT_REGION.amazonaws.com/ai-kirinuki-worker:latest
      - echo Writing image definitions file...
      - printf '{"ImageURI":"%s"}' $AWS_ACCOUNT_ID.dkr.ecr.$AWS_DEFAULT_REGION.amazonaws.com/ai-kirinuki-app:$IMAGE_TAG > imageDefinition.json
artifacts:
  files:
    - imageDefinition.json
    - appspec.yml
    - taskdef.json
```

### 3. CodePipelineの作成

#### a. マネジメントコンソールから作成する場合

1. AWSマネジメントコンソールにログイン
2. CodePipelineサービスに移動
3. 「パイプラインを作成する」を選択
4. 以下の設定を行う：
   - **パイプライン名**: `ai-kirinuki-pipeline`
   - **サービスロール**: 新しいサービスロールを作成
   - **アーティファクトストア**: デフォルト
   - **ソースプロバイダ**: GitHub (Version 2)
   - **リポジトリ名**: リポジトリを選択
   - **ブランチ名**: main（またはデプロイに使用するブランチ）
   - **検出オプション**: GitHub Webhooksを使用
   - **ビルドプロバイダ**: AWS CodeBuild
   - **プロジェクト名**: `ai-kirinuki-build`
   - **デプロイプロバイダ**: Amazon ECS
   - **クラスター名**: `ai-kirinuki-cluster`
   - **サービス名**: `ai-kirinuki-app`
   - **イメージ定義ファイル**: imageDefinition.json

#### b. AWS CLIから作成する場合

```bash
# サービスロールの作成
aws iam create-role --role-name CodePipelineServiceRole \
  --assume-role-policy-document file://codepipeline-trust-policy.json

# ポリシーのアタッチ
aws iam attach-role-policy --role-name CodePipelineServiceRole \
  --policy-arn arn:aws:iam::aws:policy/AWSCodeBuildAdminAccess

aws iam attach-role-policy --role-name CodePipelineServiceRole \
  --policy-arn arn:aws:iam::aws:policy/AmazonECS-FullAccess

aws iam attach-role-policy --role-name CodePipelineServiceRole \
  --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess

# S3バケットの作成（アーティファクト用）
aws s3 mb s3://ai-kirinuki-pipeline-artifacts

# パイプラインの作成
aws codepipeline create-pipeline \
  --cli-input-json file://codepipeline-definition.json
```

ここで、`codepipeline-definition.json` は以下のような内容になります：

```json
{
  "pipeline": {
    "name": "ai-kirinuki-pipeline",
    "roleArn": "arn:aws:iam::<ACCOUNT_ID>:role/CodePipelineServiceRole",
    "artifactStore": {
      "type": "S3",
      "location": "ai-kirinuki-pipeline-artifacts"
    },
    "stages": [
      {
        "name": "Source",
        "actions": [
          {
            "name": "Source",
            "actionTypeId": {
              "category": "Source",
              "owner": "AWS",
              "provider": "CodeStarSourceConnection",
              "version": "1"
            },
            "configuration": {
              "ConnectionArn": "<CONNECTION_ARN>",
              "FullRepositoryId": "yourusername/AI-kirinuki-kun",
              "BranchName": "main"
            },
            "outputArtifacts": [
              {
                "name": "SourceCode"
              }
            ]
          }
        ]
      },
      {
        "name": "Build",
        "actions": [
          {
            "name": "BuildAndPush",
            "actionTypeId": {
              "category": "Build",
              "owner": "AWS",
              "provider": "CodeBuild",
              "version": "1"
            },
            "configuration": {
              "ProjectName": "ai-kirinuki-build"
            },
            "inputArtifacts": [
              {
                "name": "SourceCode"
              }
            ],
            "outputArtifacts": [
              {
                "name": "BuildOutput"
              }
            ]
          }
        ]
      },
      {
        "name": "Deploy",
        "actions": [
          {
            "name": "DeployToECS",
            "actionTypeId": {
              "category": "Deploy",
              "owner": "AWS",
              "provider": "ECS",
              "version": "1"
            },
            "configuration": {
              "ClusterName": "ai-kirinuki-cluster",
              "ServiceName": "ai-kirinuki-app",
              "FileName": "imageDefinition.json"
            },
            "inputArtifacts": [
              {
                "name": "BuildOutput"
              }
            ]
          }
        ]
      }
    ]
  }
}
```

### 4. Webhookの設定（GitHub連携）

#### a. GitHub Appの連携を使用する場合

1. AWS CodePipelineコンソールの「設定」から「コネクション」を選択
2. 「接続を作成」を選択
3. 「GitHub」を選択し、接続名を入力
4. 「GitHub に接続」ボタンをクリックして認証を行う
5. パイプラインの作成または編集時にこの接続を使用

#### b. GitHub Webhookを手動で設定する場合

```bash
# GitHub Webhookの作成
aws codepipeline create-webhook \
  --name ai-kirinuki-webhook \
  --authentication-configuration type=GITHUB_HMAC,secret=<WEBHOOK_SECRET> \
  --definition type=GITHUB,host=github.com,owner=yourusername,repository=AI-kirinuki-kun \
  --target-pipeline ai-kirinuki-pipeline \
  --target-action Source \
  --filters name=REFERENCE_NAME,value=main,pattern=main
```

### 5. ワーカーのデプロイ設定

ワーカーについても同様のデプロイパイプラインを構築する場合は、別のCodePipelineを作成するか、同じパイプラインに並列的なデプロイステージを追加します。

```bash
# 同じパイプラインに並列ステージを追加する例
aws codepipeline update-pipeline \
  --cli-input-json file://codepipeline-with-worker.json
```

### 6. デプロイ承認の追加（オプション）

本番環境へのデプロイ前に手動承認を追加する場合：

```bash
# 承認ステージを追加
aws codepipeline update-pipeline \
  --cli-input-json file://codepipeline-with-approval.json
```

`codepipeline-with-approval.json` には、以下のような承認ステージを追加します：

```json
{
  "name": "Approval",
  "actions": [
    {
      "name": "ManualApproval",
      "actionTypeId": {
        "category": "Approval",
        "owner": "AWS",
        "provider": "Manual",
        "version": "1"
      },
      "configuration": {
        "NotificationArn": "<SNS_TOPIC_ARN>",
        "CustomData": "Please review and approve the deployment to production"
      }
    }
  ]
}
```

## テスト自動化

パイプラインに自動テストを統合するには、ビルドフェーズまたは個別のテストフェーズでテストを実行します。

### 1. テスト用のbuildspec.ymlの例

```yaml
version: 0.2

phases:
  install:
    runtime-versions:
      python: 3.8
    commands:
      - echo Installing dependencies...
      - pip install -r requirements.txt
      - pip install pytest pytest-cov
  pre_build:
    commands:
      - echo Running tests...
      - pytest --cov=src tests/
  build:
    commands:
      - echo Build started on `date`
      # ここに実際のビルドコマンドを追加
  post_build:
    commands:
      - echo Build completed on `date`
reports:
  pytest_reports:
    files:
      - "test-report.xml"
    file-format: "JUNITXML"
artifacts:
  files:
    - appspec.yml
    - taskdef.json
    - imageDefinition.json
```

### 2. テスト結果の通知設定

```bash
# SNSトピックの作成
aws sns create-topic --name ai-kirinuki-test-results

# CodeBuildプロジェクトに通知を設定
aws codestarnotifications create-notification-rule \
  --name ai-kirinuki-test-notification \
  --resource arn:aws:codebuild:<REGION>:<ACCOUNT_ID>:project/ai-kirinuki-build \
  --detail-type FULL \
  --event-type-ids codebuild-project-build-state-failed \
  --targets TargetType=SNS,TargetAddress=<SNS_TOPIC_ARN>
```

## デプロイの監視

### 1. CloudWatchダッシュボードの設定

```bash
# デプロイモニタリング用ダッシュボードの作成
aws cloudwatch put-dashboard \
  --dashboard-name AI-Kirinuki-Deployment-Dashboard \
  --dashboard-body file://deployment-dashboard.json
```

### 2. デプロイアラームの設定

```bash
# デプロイ失敗アラームの作成
aws cloudwatch put-metric-alarm \
  --alarm-name AI-Kirinuki-DeploymentFailure \
  --alarm-description "Alarm when deployment fails" \
  --metric-name DeploymentFailure \
  --namespace AWS/CodeDeploy \
  --statistic Sum \
  --period 60 \
  --threshold 1 \
  --comparison-operator GreaterThanOrEqualToThreshold \
  --dimensions Name=Application,Value=ai-kirinuki Name=DeploymentGroup,Value=production \
  --evaluation-periods 1 \
  --alarm-actions <SNS_TOPIC_ARN>
```

## ロールバック戦略

### 1. 自動ロールバックの設定

```bash
# ECSサービスの更新で自動ロールバックを有効化
aws ecs update-service \
  --cluster ai-kirinuki-cluster \
  --service ai-kirinuki-app \
  --deployment-configuration maximumPercent=200,minimumHealthyPercent=100,deploymentCircuitBreaker={enable=true,rollback=true}
```

### 2. 手動ロールバックの手順

1. 前回の成功したデプロイのイメージタグを特定
2. ECSサービスを更新して以前のイメージにロールバック

```bash
# 手動ロールバックの実行
aws ecs update-service \
  --cluster ai-kirinuki-cluster \
  --service ai-kirinuki-app \
  --force-new-deployment \
  --task-definition ai-kirinuki-app:<PREVIOUS_REVISION>
```

## セキュリティのベストプラクティス

### 1. シークレット管理

- AWS Systems Manager Parameter Storeまたは AWS Secrets Managerを使用
- ビルドスクリプトやソースコードには機密情報を含めない

```bash
# パラメータの保存例
aws ssm put-parameter \
  --name /ai-kirinuki/production/database-password \
  --value "YOUR_PASSWORD" \
  --type SecureString
```

### 2. IAM権限の最小化

各サービスのIAMロールには、必要最小限の権限のみを付与します。

### 3. イメージスキャン

ECRのイメージスキャンを有効にして、脆弱性を検出します。

```bash
# ECRリポジトリにスキャンを設定
aws ecr put-image-scanning-configuration \
  --repository-name ai-kirinuki-app \
  --image-scanning-configuration scanOnPush=true
```

## トラブルシューティング

### 1. パイプライン実行ステータスの確認

```bash
# パイプラインの最新の実行を表示
aws codepipeline get-pipeline-state \
  --name ai-kirinuki-pipeline
```

### 2. ビルドログの確認

```bash
# ビルドプロジェクトのビルドIDを取得
aws codebuild list-builds-for-project \
  --project-name ai-kirinuki-build

# ビルドログを表示
aws codebuild batch-get-builds \
  --ids <BUILD_ID>
```

### 3. デプロイの失敗原因の特定

```bash
# ECSデプロイのイベントを確認
aws ecs describe-services \
  --cluster ai-kirinuki-cluster \
  --services ai-kirinuki-app
```