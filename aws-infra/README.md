# aws-infra

## 概要

`aws-infra` は、このプロジェクトの AWS リソースを CDK(TypeScript) で管理するディレクトリです。  
アプリケーション実装と同じリポジトリで IaC を管理することで、実装変更とインフラ変更を同じレビュー文脈で扱えるようにしています。

設計上は、開発速度を落としすぎずに運用性を上げることを重視しています。

- 構成変更を CloudFormation 経由で再現可能にする
- 画像処理系のコンテナと API コンテナを別スケール単位にする
- 監視、通知、Slack 連携までコード化して属人運用を減らす

## CDK での実装方針

エントリーポイントは 2 つあります。

- `bin/aws-ecr.ts`
  ECR リポジトリ群を作成するためのエントリーポイント
- `bin/aws-app.ts`
  ストレージ、Lambda、App Runner、監視、通知をまとめて組み立てるエントリーポイント

環境値は `config/env.ts` で集約し、`STAGE` を軸に命名や設定値を切り替える構成です。  
この形にすることで staging / production の差分をコード上で追いやすくし、運用時の設定漏れを減らしています。

## スタック構成

- `lib/ecr-stack.ts`
  Django API、YOLO Lambda、背景除去 Lambda 用の ECR リポジトリを作成します。`imageScanOnPush`、immutable tag、ライフサイクルルールを設定し、サプライチェーンと運用保守を両立しています。
- `lib/storage-stack.ts`
  メディア用 S3 バケットと CloudFront を構築します。CloudFront を有効にした場合は OAC を使って S3 を非公開のまま配信します。
- `lib/lambda-yolo-stack.ts`
  YOLO ベースの切り抜き処理を行う Lambda コンテナを作成します。S3 への read/write 権限を持ち、Function URL でも呼び出せます。
- `lib/lambda-bg-stack.ts`
  rembg ベースの背景除去を行う Lambda コンテナを作成します。画像処理を API 本体から切り離すためのスタックです。
- `lib/apprunner-stack.ts`
  Django API を App Runner へデプロイします。ECR イメージ参照、S3 アクセス用 IAM、カスタムドメイン関連、ヘルスチェックを持ちます。
- `lib/monitoring-stack.ts`
  CloudWatch Dashboard、SNS Topic、App Runner / Lambda 向け Alarm を構成します。
- `lib/alerting-stack.ts`
  AWS Chatbot を使って SNS を Slack チャンネルへ連携します。

## CloudWatch による監視

監視は `lib/monitoring-stack.ts` に集約しています。

- Lambda
  Duration(avg / p95)、Errors、Throttles、ConcurrentExecutions を監視
- App Runner
  CPU、Memory、RequestLatency、4xx、5xx、Concurrency、ActiveInstances を監視
- Dashboard
  プロジェクト単位の Observability Dashboard を作成

単にアラームを置くだけでなく、ダッシュボードで平常時の傾向も追えるようにしているのがポイントです。  
面接では「障害検知だけでなく、性能劣化の予兆も見られる構成」と説明しやすいです。

## Slack 連携とアラート設定

通知経路は次の通りです。

1. CloudWatch Alarm
2. SNS Topic
3. AWS Chatbot
4. Slack チャンネル

`alerting-stack.ts` では Slack Workspace ID と Channel ID を受け取り、ReadOnly 権限付きの Chatbot 設定を作成しています。  
アラートを Slack に寄せることで、メールだけに依存しない初動導線を作っています。

## Lambda によるコンテナイメージのデプロイ

Lambda 自体は CDK で関数定義を管理し、実体のイメージは ECR から参照します。  
つまり、コードと実行基盤の責務を分けています。

- ECR 側
  イメージの保管、スキャン、タグ管理
- CDK 側
  Lambda 関数、IAM、タイムアウト、メモリ、環境変数、Function URL の定義

この方式により、推論モデルや画像処理ライブラリを含む重い実行環境でも、Lambda Zip ではなくコンテナ単位で扱えます。

## デプロイワークフロー

主なワークフローは 2 種類です。

### 1. CDK / CloudFormation 実行デプロイ

`.github/workflows/cdk-deploy-app-runner.yml` では、次の流れでデプロイします。

1. `aws-infra` の依存関係をインストール
2. `bin/aws-ecr.ts` で ECR スタックをデプロイ
3. Django イメージを ECR へ push
4. `bin/aws-app.ts` で storage / apprunner / monitoring / alerting をデプロイ

これは「環境構成の変更を安全に反映する」ための流れです。  
CloudFormation 管理下に置くことで、再現性と変更追跡性を確保しています。

### 2. ECR から Lambda / App Runner を反映するデプロイ

`.github/workflows/push-ecr-and-deploy-apprunner.yml` では、DjangoAPI の変更を契機にイメージをビルドし、ECR へ push した上で App Runner の deployment を開始します。

この流れは、インフラ構成を変えずにアプリだけを素早く反映したい場面に向いています。  
CDK デプロイより高速ですが、構成変更を伴うケースでは前者を使うのが前提です。

## トレードオフ

- CDK を分けることで再現性は上がるが、学習コストと管理対象は増える
- App Runner は ECS/Fargate より運用が軽いが、細かいチューニング自由度は下がる
- Lambda コンテナは画像処理と相性が良い一方、コールドスタートとイメージサイズ管理が必要
- CloudFront 配信はレイテンシと配信効率に効く一方、キャッシュ戦略を考える必要がある

## 選定理由

- App Runner
  コンテナベースでオートスケーリングでき、Django API の運用負荷を抑えやすいため
- Lambda Containers
  レイテンシの高い画像処理を API 本体から分散し、負荷特性の違う処理を切り離せるため
- CloudFront
  メディア配信をエッジに寄せ、S3 直配信よりも体感レイテンシと配信効率を改善しやすいため
- CDK / CloudFormation
  再現性、レビュー可能性、環境差分の抑制に有利なため

## 開発用コマンド

- `npm run build`
- `npm run test`
- `npx cdk synth`
- `npx cdk diff`
- `npx cdk deploy`
