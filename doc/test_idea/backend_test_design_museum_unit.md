# DjangoAPI Museum ユニットテスト設計

更新日: 2026-03-19

## 1. 目的

Model、Serializer、軽量な View 補助ロジック、外部連携の例外変換を小さく検証する。  
DB 制約の境界、soft delete、所有者判定、時刻依存、外部依存の分岐を重点対象とする。

## 2. 使用モジュール

- `pytest`
- `pytest-django`
- `factory-boy`
- `pytest-mock`
- `freezegun`
- `moto`

## 3. 対象

### MiniatureMuseum
- `Gallery.delete()`
- `Exhibit.delete()`
- `Gallery.clean()`
- `Exhibit.clean()`
- `GallerySerializer`
- `ExhibitSerializer`
- `ExhibitUpsertSerializer`
- `_GalleryActorMixin` の所有者判定ロジック

### core
- `UserManager.create_user()`
- `UserRegistrationSerializer`
- `GuestIssueResponseSerializer`
- `UploadIssueSerializer`
- `UploadConfirmSerializer`
- `UploadView._get_uploader()`

### rembgAPI
- `RembgProcessView.post()`
- `_apply_cors()`
- `process_event` 呼び出し結果の整形

## 4. Factory / Fixture 方針

### factory-boy
- `UserFactory`
- `GalleryFactory`
- `GuestGalleryFactory`
- `ExhibitFactory`
- `UploadSessionFactory`

### fixture
- `rf`: Django `RequestFactory`
- `api_rf`: DRF `APIRequestFactory`
- `user`
- `other_user`
- `guest_id`

## 5. 主要テストケース

### Gallery / Exhibit model
- soft delete で `deleted_at` が設定される
- `freezegun` で delete 時刻を固定して比較する
- guest gallery は `guest_id` 必須、`owner` 禁止
- user gallery は `owner` 必須、`guest_id` 禁止
- exhibit は `gallery.user_style` と `user_style` が一致しないと失敗する
- `slot_index` は 0..11 の範囲外で失敗する

### Serializer
- `GallerySerializer` は `exhibits` に active exhibit のみ含める
- `ExhibitSerializer.validate_gallery` は所有者不一致を拒否する
- guest リクエストで `X-Guest-Id` が無いと失敗する
- `ExhibitUpsertSerializer` は `image_original_url` を必須とする
- `UploadIssueSerializer` は `purpose` を choice で制約する
- `UploadConfirmSerializer` は `upload_session_id` を UUID として受理する

### Upload ロジック
- `_get_uploader()` は JWT user を優先する
- guest かつ `X-Guest-Id` 無しは拒否する
- `moto` を使って presigned URL 生成と `head_object` 成功を再現する
- confirm は owner / guest_id 不一致の session を取得できない
- `freezegun` で `expires_at` を固定し、期限切れ判定を追加する場合の基準ケースを先行定義する

### rembgAPI
- `process_event` の正常戻り値を HTTP response に変換する
- `process_event` が JSON 文字列 body を返したとき `JsonResponse` に変換する
- 不正 JSON を返したとき `raw` ラップで返す
- CORS header が付与される
- `pytest-mock` で `process_event` を差し替える

## 6. 優先順位

1. `Gallery` / `Exhibit` の制約
2. Upload serializer / uploader 判定
3. rembgAPI の response 変換
4. auth serializer / user manager

## 7. 成果物イメージ

```text
tests/
  factories/
    user_factory.py
    museum_factory.py
    upload_factory.py
  unit/
    test_gallery_model.py
    test_exhibit_model.py
    test_museum_serializers.py
    test_upload_serializers.py
    test_upload_helpers.py
    test_rembg_view.py
```
