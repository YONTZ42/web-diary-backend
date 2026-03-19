# DjangoAPI Museum 負荷テスト設計

更新日: 2026-03-19

## 1. 目的

主要 museum API の read / write / upload 系ボトルネックを把握する。  
負荷テストは `k6` を使用し、機能テストの代替ではなく性能の基準取得として扱う。

## 2. 使用モジュール

- `k6`

## 3. 対象シナリオ

### Read
- `GET /api/galleries/g/{slug}/`
- `GET /api/guest/gallery/`
- `GET /api/galleries/{id}/`

### Write
- `PUT /api/galleries/{gallery_id}/exhibits/{slot_index}/`
- `PATCH /api/guest/gallery/`

### Upload
- `POST /api/uploads/issue/`
- `POST /api/uploads/confirm/`

## 4. 前提データ

- public gallery 用 slug
- user token
- guest id
- 既存 gallery id
- exhibit upsert 用 slot 値

## 5. テストファイル

```text
load-tests/
  k6/
    smoke-read.js
    galleries-read.js
    exhibits-upsert.js
    uploads-issue-confirm.js
```

## 6. しきい値

- `http_req_failed < 0.01`
- read API: `p(95) < 500ms`
- exhibit upsert: `p(95) < 800ms`
- uploads issue/confirm: `p(95) < 1200ms`

## 7. 実行段階

### smoke
- 1-5 VUs
- deploy 後の疎通確認

### baseline
- 10-30 VUs
- 継続的な比較用

### stress
- 50 VUs 以上
- ボトルネック把握用

## 8. 注意点

- 本物の S3 upload は負荷テスト対象から外し、API 自体の応答時間を主に測る
- upload confirm は事前にアップロード済みオブジェクトか、専用テストデータを使う
- staging での実施を基本とし、ローカル実行は参考値に留める
