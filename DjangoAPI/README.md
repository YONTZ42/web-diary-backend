# DjangoAPI

## 概要

`DjangoAPI` は Django 4.2 + Django REST Framework によるバックエンド API です。  
主な責務は、認証、アップロード、MiniatureMuseum ドメインの CRUD、画像処理 API の受付、API スキーマ公開、テストです。

実装の特徴は、次の 3 点です。

- User と Guest の両方を扱える API 設計
- 論理削除と制約を併用した整合性重視のデータ設計
- 画像処理を完全には外出しせず、`rembgAPI` を同居させて API 境界を単純化している点

## ディレクトリ構成

- `core/`
  User、UploadSession、認証、アップロード、汎用ドメインの実装
- `MiniatureMuseum/`
  Gallery / Exhibit を中心としたミュージアム機能
- `rembgAPI/`
  背景除去 API と画像処理サービス
- `config/`
  settings、URL ルーティング、logging、health check
- `tests/`
  API、unit、smoke、load テスト

## URL 設計

ルートは `config/urls.py` に集約されています。

- `/api/`
  `core.urls` と `MiniatureMuseum.urls`、`rembgAPI.urls` を統合
- `/api/token/`, `/api/token/refresh/`
  JWT 発行 / 更新
- `/api/schema/`, `/api/docs/`
  OpenAPI スキーマとドキュメント
- `/healthz`
  App Runner 用 shallow health check
- `/health`
  DB や外部依存を含む deep health check

MiniatureMuseum の API は、REST Router とユースケース特化のネスト URL を併用しています。

- `galleries/`, `exhibits/`
  標準的な CRUD 導線
- `guest/gallery/`
  Guest の単一ギャラリーを簡潔に扱う専用エンドポイント
- `galleries/<gallery_id>/exhibits/`
  ギャラリー配下の Exhibit 作成
- `galleries/<gallery_id>/exhibits/<slot_index>/`
  スロット単位の upsert / delete

汎用 REST だけでなく、フロントエンドが扱いやすいユースケース寄り URL を置いている点が実務的な判断です。  
厳密な REST 純度より、開発速度と API 利用体験を優先しています。

## データベース設計

### 主要エンティティ

- `User`
  email を主キー的に扱うカスタムユーザー。Stripe 関連の契約情報も保持
- `UploadSession`
  Presigned URL によるアップロード発行と確認の状態管理
- `Gallery`
  User / Guest どちらかに所属する棚
- `Exhibit`
  Gallery に紐づく展示物。`slot_index` で配置管理

### Validation と制約

モデル制約とアプリケーション側 validation を両方使っています。

- `Gallery`
  `user_style=user` なら `owner` 必須、`guest_id` は空
- `Gallery`
  `user_style=guest` なら `guest_id` 必須、`owner` は空
- `Exhibit`
  `slot_index` は 0..11 に制限
- `Exhibit`
  `user_style` は親 `Gallery` と整合する前提
- `UploadSession`
  `user` または `guest_id` のどちらか一方のみを持つ

この方針により、Serializer だけに整合性を依存せず、DB レベルでも破綻しにくい設計にしています。

### 論理削除

主要モデルは `BaseModel` を継承し、`deleted_at` を持ちます。  
削除時は物理削除ではなく論理削除を行い、ユーザー操作の取り消しや監査性、将来の復元要件に備えています。

### 部分ユニーク制約

論理削除を採用すると、通常の unique 制約だけでは再作成が難しくなります。  
そのため一部では「有効レコードだけに効く unique」を採用しています。

- `Gallery`
  `user_style='guest'` かつ `deleted_at IS NULL` の範囲で `guest_id` を一意化
- `Exhibit`
  `deleted_at IS NULL` の範囲で `(gallery, slot_index)` を一意化

これは論理削除と整合性を両立するための実務的な設計です。

## PostgreSQL を選定した理由

このプロジェクトでは SQLite ではなく PostgreSQL を前提にした方が説明しやすいです。

- 部分ユニーク制約や CheckConstraint との相性が良い
- 将来的な同時アクセス増加に対してロックや整合性の扱いが安定している
- JSONField を含む柔軟なモデリングと、RDB としての堅い制約の両立がしやすい
- 本番運用での保守性、監視性、バックアップ戦略を考えやすい

特に「整合性を DB でも担保したい」という意図に対して、PostgreSQL は素直な選択です。

## settings.py の要点

- 環境変数は `django-environ` で管理
- `APP_ENV` に応じて `DEBUG` や SSL 系設定を切り替え
- DB は `DATABASE_URL` 優先、未指定時は Docker 前提の PostgreSQL を参照
- DRF は JWT 認証を標準化
- `djangorestframework-camel-case` を使い、フロントとの命名差分を吸収
- `drf-spectacular` で OpenAPI を生成
- throttle を設定し、guest 発行や rembg API の乱打に上限を設ける
- `structlog` を使った構造化ログに対応

## rembgAPI を同居させている理由

`rembgAPI` は Django プロジェクト内に同居しています。  
完全に別サービスへ分離することもできますが、現時点では次の理由で同居構成にしています。

- API 入口を Django 側に寄せた方が開発速度が高い
- 認証、レート制限、スキーマ公開を既存基盤で揃えやすい
- PoC から本番運用へ移る途中で、過度なマイクロサービス化を避けられる

一方で、処理負荷が増えた場合は Lambda 側へさらに寄せる余地を残しています。  
つまり、同居は暫定ではなく「速度優先の段階的分離戦略」として説明できます。

## スケーラビリティとトレードオフ

- App Runner 側で API を水平スケールできる一方、DB はボトルネックになりやすいため将来的には read/write 分離やキャッシュが候補
- Gallery / Exhibit は制約を厚くしているため、書き込み性能より整合性を優先している
- Guest と User を同一 API で扱うため分岐は増えるが、プロダクト仕様を 1 つのバックエンドで保てる
- rembg を同居させることで開発速度は上がるが、高負荷時には API ノードへ影響しうる

## 将来的な方針

- 重い画像処理は Lambda へさらに寄せ、Django はオーケストレーション寄りにする
- UploadSession を起点に非同期ジョブ管理を追加し、リトライや進捗追跡を強化する
- DB 監視、クエリ最適化、必要に応じたキャッシュ導入で読み取り負荷に備える
- `tests/` README を整備し、テスト戦略を API / unit / smoke / load の観点で明文化する

## テスト

`tests/` 以下には次の種類のテストがあります。

- `tests/api/`
  エンドポイントの契約と権限分岐の確認
- `tests/unit/`
  個別ロジックの単体確認
- `tests/smoke-ci/`, `tests/smoke-staging/`
  環境に対する疎通確認
- `tests/load/`
  k6 による負荷観点の検証
