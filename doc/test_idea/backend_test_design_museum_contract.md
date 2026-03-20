# DjangoAPI Museum 契約テスト設計

更新日: 2026-03-19

## 1. 目的

`DjangoAPI/schema.yml` と実装のズレを早期に検知する。  
特に camelCase 変換、必須 path、公開 serializer の露出項目、uploads の request/response を重点監視する。

## 2. 使用モジュール

- `pytest`
- `pytest-django`
- `coverage`

## 3. 対象

- `DjangoAPI/schema.yml`
- museum 関連 path
- guest issue response
- gallery public schema
- upload issue / confirm schema

## 4. 主要チェック

### path 存在
- `/api/auth/guest/`
- `/api/guest/gallery/`
- `/api/galleries/g/{slug}/`
- `/api/galleries/{gallery_id}/exhibits/`
- `/api/galleries/{gallery_id}/exhibits/{slot_index}/`
- `/api/uploads/{action}/`
- `/api/image/rembg/{model_name}/`

### schema 項目
- `GuestIssueResponse` が `guestId` を返す
- `GalleryPublic` が `exhibits` を配列で持つ
- public schema に `owner` `guestId` が含まれない
- upload confirm request が `uploadSessionId` を要求する
- exhibit upsert 系で `imageOriginalUrl` を要求する

### 命名整合
- response の camelCase が維持される
- serializer 実装が snake_case のまま露出していないことを確認する

## 5. 補足

- contract test は schema の存在確認に留め、業務振る舞いの正否は API テストで担保する
- `coverage` は contract test 単体ではなく CI 全体の計測対象として扱う

## 6. 成果物イメージ

```text
tests/
  contract/
    test_schema_paths.py
    test_schema_components.py
```
