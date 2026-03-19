# DjangoAPI Museumテスト設計レビュー

更新日: 2026-03-19
対象: `DjangoAPI/` のうち museum 機能に直接関係する `MiniatureMuseum`、依存する `core` の認証・アップロード、`rembgAPI`

## 1. レビュー結論

既存の `backend_test_design_museum.md` は、テスト観点そのものは有用だが、現行実装に対して範囲が広すぎる。  
そのため、本書は「妥当性レビューと参照ハブ」に縮約し、詳細設計はテスト種類ごとの文書へ分離した。

### 妥当な点
- Guest と User の認証経路を分けて検証する方針
- `Gallery` / `Exhibit` の soft delete と active 制約を重点確認する方針
- `uploads issue -> confirm` の所有者チェックを重点化する方針
- 公開 gallery と private gallery の公開範囲を分けて確認する方針
- OpenAPI schema を契約テストで監視する方針

### 削除・縮小した点
- `Notebook` `Page` `Schedule` `Sticker` まで含めた設計
- CloudWatch ダッシュボード、SLO、Alarm などの運用設計詳細
- `healthz` / `readyz` のような現時点で未実装のエンドポイント前提
- staging / CI / 本番監視の詳細な段階設計
- museum API の設計書としては過剰な性能目標値の細目

### 追加した点
- 現行 URL / View / Serializer / Model 制約に即した対象一覧
- `rembgAPI` のユニット・スモーク対象
- OpenAPI の camelCase / snake_case 変換に対する契約テスト
- `pytest` 系ツール、`factory-boy`、`DRF APIClient`、`pytest-mock`、`coverage`、`freezegun`、`moto`、`k6` の利用位置
- 実装上の注意点を踏まえた優先テストケース

## 2. 現行実装に基づくテスト対象

### 対象に含める
- `POST /api/auth/guest/`
- `POST /api/token/`
- `POST /api/token/refresh/`
- `GET /api/me/`
- `POST /api/uploads/issue/`
- `POST /api/uploads/confirm/`
- `GET|POST|PATCH|DELETE /api/guest/gallery/`
- `GET|POST|PATCH|DELETE /api/galleries/` と `/api/galleries/{id}/`
- `POST /api/galleries/{gallery_id}/exhibits/`
- `PUT|DELETE /api/galleries/{gallery_id}/exhibits/{slot_index}/`
- `GET /api/galleries/g/{slug}/`
- `POST /api/image/rembg/{model_name}/`
- `schema.yml` の museum 関連 path / schema

### 対象から外す
- museum 機能と無関係な `Sticker` `Page` `Schedule` `Notebook` の CRUD
- 未実装の health check API
- AWS / CloudWatch の運用手順書レベルの詳細


## 3. テスト設計書一覧

- [ユニットテスト設計](/c:/AppDev/myapp-diary/doc/backend_test_design_museum_unit.md)
- [APIテスト設計](/c:/AppDev/myapp-diary/doc/backend_test_design_museum_api.md)
- [Smokeテスト設計](/c:/AppDev/myapp-diary/doc/backend_test_design_museum_smoke.md)
- [契約テスト設計](/c:/AppDev/myapp-diary/doc/backend_test_design_museum_contract.md)
- [負荷テスト設計](/c:/AppDev/myapp-diary/doc/backend_test_design_museum_load.md)

## 4. 必須モジュールの使用方針

- `pytest`, `pytest-django`: 全テスト基盤
- `factory-boy`: User / Gallery / Exhibit / UploadSession の factory
- `rest_framework.test.APIClient`: API / Smoke テストのクライアント
- `pytest-mock`: boto3、Google token verify、`process_event` のモック
- `coverage`: CI の coverage 計測
- `freezegun`: soft delete 時刻、upload expiration の固定
- `moto`: S3 presigned URL / `head_object` を伴う upload テスト
- `k6`: 負荷テスト

## 5. 優先度

### 最優先
- Guest/User の権限制御
- `Gallery` と `Exhibit` の active 制約
- uploads の所有者整合性
- 公開 gallery の情報露出制御

### 次点
- OpenAPI 契約
- rembgAPI のエラーハンドリング
- 性能のベースライン取得
