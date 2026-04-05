# myapp-diary

## 概要

`myapp-diary` は、Django API・AWS CDK・Lambda コンテナを分離して構成したプロダクト実装です。  
アプリ本体は Django を App Runner 上で運用し、画像処理のようにレイテンシと計算コストが読みにくい処理は Lambda コンテナへ切り出しています。  
単一リポジトリに集約することで開発速度を確保しつつ、実行基盤は API / 画像処理 / インフラで責務分離しています。

転職向けに説明するなら、次の点がこのリポジトリの主題です。

- Web API、非同期寄りの画像処理、IaC、監視までを一気通貫で扱っている
- スケーラビリティを見据えて、常時稼働させる API とスパイクしやすい処理を分離している
- 開発速度を落としすぎないように、モノレポで実装とデプロイ導線を揃えている

## ディレクトリ構成

- `DjangoAPI/`
  Django 4.2 ベースのバックエンド API。認証、アップロード、MiniatureMuseum ドメイン、rembg API、テストを含みます。
- `aws-infra/`
  AWS CDK(TypeScript) によるインフラ定義。S3、CloudFront、ECR、Lambda、App Runner、CloudWatch、Slack 通知までをコード化しています。
- `LambdaContainers/`
  画像処理用の Lambda コンテナ群。背景除去や YOLO ベースの切り抜き処理をコンテナイメージとして管理します。
- `doc/`
  監視設計、環境設計、テスト観点などの設計メモ。
- `python_rembg_demo/`
  rembg のローカル検証用サンプル。
- `.github/workflows/`
  GitHub Actions によるデプロイ・運用ワークフロー。

## 全体アーキテクチャ

- API レイヤー
  Django API を App Runner でコンテナ実行。
- ストレージ / 配信
  メディアは S3 に保存し、CloudFront で配信。
- 重い画像処理
  背景除去や YOLO セグメンテーションは Lambda コンテナへ分散。
- 監視 / 通知
  CloudWatch Dashboard・Alarm・SNS・AWS Chatbot(Slack) を CDK で構築。

この構成は、単純に EC2 や 1 つの Django プロセスへ寄せるよりも構成要素は増えます。  
その一方で、API の安定運用と画像処理のバースト耐性を分けて最適化できるため、将来的なトラフィック増加に対して説明しやすい構成です。

## ワークフロー

このリポジトリでは、主に次の流れでデプロイします。

1. CDK / CloudFormation 実行デプロイ
`aws-infra/` の CDK から、ECR 以外の実行基盤や監視基盤をデプロイします。構成変更をコードレビュー可能にし、環境差分を抑えるための流れです。

2. ECR イメージ更新から App Runner / Lambda へ反映
アプリや画像処理のコンテナをビルドして ECR に push し、App Runner や Lambda が参照するイメージを更新します。アプリ改修時の反映速度を優先した流れです。

## リポジトリごとの README

- [aws-infra/README.md](/c:/AppDev/myapp-diary/aws-infra/README.md)
- [DjangoAPI/README.md](/c:/AppDev/myapp-diary/DjangoAPI/README.md)
- [LambdaContainers/README.md](/c:/AppDev/myapp-diary/LambdaContainers/README.md)
