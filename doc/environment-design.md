# staging / production 環境設計メモ

## 結論

- 環境は `STAGE=staging` と `STAGE=production` で分ける
- ブランチ運用は `develop -> staging`、`main -> production`
- GitHub Environments も `staging` / `production` で分ける
- Secrets は environment ごとに分ける
- CDK は `aws-infra/bin/aws-ecr.ts` と `aws-infra/bin/aws-app.ts` に分離する
- デプロイフローは **ECR stack deploy -> Docker image push -> app stack deploy**
- Lambda は `lambda-yolo-stack.ts` と `lambda-bg-stack.ts` に分割する
- rembg は削除
- monitoring は今回の対象外として削除
- App Runner の custom domain 再デプロイは、`associateCustomDomain` を毎回 onUpdate で叩かない構成にして安定化する

---

## 1. 環境の分け方

### 環境名
- `staging`
- `production`

### 理由
- stack 名や AWS リソース名にそのまま入れても分かりやすい
- `stage` という曖昧な値より `staging` の方が明確
- GitHub Environments 名とも揃えやすい

### 例
- `mini-museum-staging-ecr`
- `mini-museum-staging-apprunner`
- `mini-museum-production-ecr`
- `mini-museum-production-apprunner`

---

## 2. ブランチと環境の対応

- `develop` branch -> `staging`
- `main` branch -> `production`

### 運用方針
#### develop
- 日常開発用
- push で staging へ自動デプロイ
- 承認不要

#### main
- 本番反映用
- merge で production へデプロイ
- GitHub Environment の承認付き推奨
- 直接 push ではなく PR merge 推奨

---

## 3. GitHub Environments の分け方

### 作成する environment
- `staging`
- `production`

### staging に入れるもの
#### secrets
- `AWS_ACCOUNT_ID`
- `AWS_IAM_ROLE_ARN`
- `DATABASE_URL`
- `SECRET_KEY`
- `ALLOWED_HOSTS`
- `CORS_ALLOWED_ORIGINS`
- `GOOGLE_OAUTH_CLIENT_ID`
- `DOMAIN_NAME`
- `HOSTED_ZONE_DOMAIN`

#### vars
- `PROJECT_NAME`
- `AWS_REGION`
- 必要なら共通設定

### production に入れるもの
#### secrets
- staging と同じキー名で、本番値にする

#### vars
- staging と同じキー名で、本番値にする

### ポイント
- **キー名は同じ**
- **値だけ環境ごとに変える**
- workflow 側の書き方を共通化できる

---

## 4. CDK 構成の方向性

CDK 関連ファイルは以下に置く。

- `aws-infra/bin/`
- `aws-infra/lib/`

### 分離後の実行ファイル
- `aws-infra/bin/aws-ecr.ts`
- `aws-infra/bin/aws-app.ts`

### 役割
#### aws-ecr.ts
- `EcrStack` のみ作成
- ECR リポジトリを作る
- `CfnOutput` で repo 名 / repo URI を出す

#### aws-app.ts
- `StorageStack`
- `LambdaYoloStack`
- `LambdaBgStack`
- `AppRunnerStack`

※ `MonitoringStack` は今回は不要  
※ `rembg` も不要

---

## 5. Lambda Stack 分割方針

### 削除するもの
- `lambda-stack.ts`
- rembg 関数
- rembg ECR repo
- rembg 関連 env
- rembg 関連 workflow

### 新しく作るもの
- `aws-infra/lib/lambda-yolo-stack.ts`
- `aws-infra/lib/lambda-bg-stack.ts`

### 理由
- YOLO と BG を別 workflow で独立デプロイしやすくする
- 変更影響範囲を小さくする
- workflow ごとの責務を明確にする

---

## 6. ECR Stack の方針

### ECR に作る repository
- Django 用
- Lambda YOLO 用
- Lambda BG 用

### EcrStack で出力するもの
- `DjangoRepoName`
- `DjangoRepoUri`
- `LambdaYoloRepoName`
- `LambdaYoloRepoUri`
- `LambdaBgRepoName`
- `LambdaBgRepoUri`

### 理由
- GitHub Actions 側で ECR repo 名をハードコードしない
- CDK 側を repo 名の SSOT にする
- `cdk deploy --outputs-file` で URI を受け取り、そのまま push に使えるようにする

---

## 7. aws-app.ts 側の方針

### 重要
`aws-app.ts` では `EcrStack` を作らない。

### やること
- `fromRepositoryName(...)` で既存の ECR repository を参照する
- `aws-ecr.ts` で作られた repository を前提に App Runner / Lambda を組み立てる

### 理由
- `aws-ecr.ts` と責務分離するため
- 「ECR stack deploy -> image push -> app stack deploy」の流れを綺麗に成立させるため

---

## 8. デプロイフロー

### 基本フロー
1. `aws-ecr.ts` を CDK deploy
2. `CfnOutput` を `--outputs-file` で取得
3. 取得した ECR URI に Docker image を push
4. `aws-app.ts` を CDK deploy

### App Runner の場合
1. ECR stack deploy
2. Django image build
3. Django image push
4. storage + apprunner stack deploy

### Lambda YOLO の場合
1. ECR stack deploy
2. YOLO image build
3. YOLO image push
4. storage + lambda-yolo stack deploy

### Lambda BG の場合
1. ECR stack deploy
2. BG image build
3. BG image push
4. storage + lambda-bg stack deploy

---

## 9. 新しい workflow 構成

### 作成する workflow
- `deploy-app-runner.yml`
- `deploy-lambda-yolo.yml`
- `deploy-lambda-bg.yml`

### 発火条件の考え方
#### App Runner
- `DjangoAPI/**`
- `aws-infra/bin/aws-ecr.ts`
- `aws-infra/bin/aws-app.ts`
- `aws-infra/lib/ecr-stack.ts`
- `aws-infra/lib/apprunner-stack.ts`
- `aws-infra/lib/storage-stack.ts`

#### Lambda YOLO
- `LambdaContainers/Lambda_CropYOLO_Multi/**`
- `aws-infra/bin/aws-ecr.ts`
- `aws-infra/bin/aws-app.ts`
- `aws-infra/lib/ecr-stack.ts`
- `aws-infra/lib/lambda-yolo-stack.ts`
- `aws-infra/lib/storage-stack.ts`

#### Lambda BG
- `LambdaContainers/Lambda_Genai/**`
- `aws-infra/bin/aws-ecr.ts`
- `aws-infra/bin/aws-app.ts`
- `aws-infra/lib/ecr-stack.ts`
- `aws-infra/lib/lambda-bg-stack.ts`
- `aws-infra/lib/storage-stack.ts`

### ブランチ対応
- `develop` に push -> `environment=staging`
- `main` に push -> `environment=production`

---

## 10. workflow の環境変数方針

### 基本方針
workflow 側では **必要最低限のみ** 渡す。  
詳細設定は `env.ts` から読む。

### workflow 側で最低限必要なもの
- `AWS_ACCOUNT_ID`
- `AWS_REGION`
- `PROJECT_NAME`
- `STAGE`
- 対象 image tag
  - `DJANGO_IMAGE_TAG`
  - `LAMBDA_YOLO_IMAGE_TAG`
  - `LAMBDA_BG_IMAGE_TAG`
- 必要な secret
  - `DATABASE_URL`
  - `SECRET_KEY`
  - `ALLOWED_HOSTS`
  - `CORS_ALLOWED_ORIGINS`
  - `GOOGLE_OAUTH_CLIENT_ID`
  - `DOMAIN_NAME`
  - `HOSTED_ZONE_DOMAIN`

### workflow 側で極力持たないもの
- repo 名
- bucket 名
- service 名
- port
- 不要な固定値

これらは `env.ts` 側に寄せる。

---

## 11. env.ts の考え方

### `env.ts` で管理するもの
- `PROJECT_NAME`
- `STAGE`
- `DJANGO_ECR_REPO`
- `LAMBDA_YOLO_ECR_REPO`
- `LAMBDA_BG_ECR_REPO`
- `MEDIA_BUCKET_NAME`
- `ENABLE_CLOUDFRONT`
- `APP_RUNNER_SERVICE_NAME`
- `APP_RUNNER_PORT`
- 各 image tag
- Django 用 env
  - `APP_ENV`
  - `DEBUG`
  - `DATABASE_URL`
  - `SECRET_KEY`
  - `ALLOWED_HOSTS`
  - `CORS_ALLOWED_ORIGINS`
  - `GOOGLE_OAUTH_CLIENT_ID`
- ドメイン
  - `DOMAIN_NAME`
  - `API_SUBDOMAIN`
  - `MEDIA_SUBDOMAIN`
  - `HOSTED_ZONE_DOMAIN`

### ポイント
- repo 名や bucket 名はここを SSOT にする
- workflow は `STAGE` と secrets のみ渡せばよい状態を目指す

---

## 12. AppRunnerStack の再デプロイ安定化

### 問題
custom domain の関連付けを `onUpdate` でも毎回叩くと不安定になりやすい。

### 対応方針
- `associateCustomDomain` は create 時のみ
- update 時は `describeCustomDomains` のみ
- delete 時は `disassociateCustomDomain`
- custom domain の DNS レコードは `describeCustomDomains` の結果から使う

### 期待効果
- 同じ stack 名で何度も `cdk deploy` しやすくなる
- custom domain 周りの再デプロイ失敗を減らせる

---

## 13. staging の目的

- 開発中の統合確認
- App Runner / Lambda / S3 / CloudFront / ドメイン疎通確認
- CDK の差分適用確認
- GitHub Actions の流れ確認
- 本番反映前の検証

### 特徴
- `develop` から自動デプロイ
- 本番に近い構成
- 必要に応じてやや簡易な運用でもよい

---

## 14. production との差分方針

### 基本
**構成差はできるだけ小さくする。**

### 差分を持つべきもの
- ドメイン
- DB 接続先
- secret 値
- CORS
- OAuth 設定値
- GitHub Environment 保護ルール

### なるべく差分を持たないもの
- Stack 構成
- workflow の流れ
- CDK の論理構造
- Docker build フロー

---

## 15. URL 方針

### staging
- API: `api-staging` 系、または staging 用サブドメイン
- media: `media-staging` 系、または staging 用サブドメイン

### production
- API: 本番サブドメイン
- media: 本番サブドメイン

### ポイント
- staging / production で URL を分ける
- cookie / CORS / OAuth callback が混ざらないようにする

---

## 16. AWS リソース名方針

すべての主要リソースに stage を入れる。

### 例
- `mini-museum-staging-ecr`
- `mini-museum-production-ecr`
- `mini-museum-staging-apprunner`
- `mini-museum-production-apprunner`
- `mini-museum-staging-lambda-yolo`
- `mini-museum-production-lambda-yolo`
- `mini-museum-staging-lambda-bg`
- `mini-museum-production-lambda-bg`

### 理由
- staging / production の衝突防止
- AWS コンソールで見分けやすい
- CloudFormation stack 名としても分かりやすい

---

## 17. 確認手順

### staging 確認
1. `develop` に push
2. workflow 実行確認
3. ECR stack deploy 成功確認
4. image push 成功確認
5. app stack deploy 成功確認
6. App Runner URL の疎通確認
7. Lambda Function URL の疎通確認
8. S3 / CloudFront の読み書き確認
9. custom domain / certificate validation 確認
10. アプリ機能確認

### production 確認
1. `main` へ PR merge
2. production environment 承認
3. workflow 実行確認
4. ECR stack deploy 成功確認
5. image push 成功確認
6. app stack deploy 成功確認
7. 本番 URL 疎通確認
8. 主要機能確認
9. エラーログ確認

---

## 18. 削除・整理対象

### 削除するもの
- rembg 関連 stack / env / repo / workflow
- `lambda-stack.ts`
- `monitoring-stack.ts`
- 旧 `aws-infra.ts`
- 旧 direct deploy 系 workflow

### 置き換えるもの
- `lambda-yolo-stack.ts`
- `lambda-bg-stack.ts`
- `aws-ecr.ts`
- `aws-app.ts`
- 新しい 3 本の workflow

---

## 19. 最終方針

### 環境
- `STAGE=staging`
- `STAGE=production`

### GitHub
- `develop -> staging`
- `main -> production`
- environment secrets / vars を環境ごとに分ける

### CDK
- `aws-ecr.ts`
- `aws-app.ts`
- ECR は先行 deploy
- app stack は後続 deploy

### workflow
- App Runner / Lambda YOLO / Lambda BG の3本
- `paths` で影響範囲ベースに発火
- branch に応じて staging / production を切り替える

### 運用
- staging で常時検証
- production は承認付き反映
- 構成差は最小限