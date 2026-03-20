# DjangoAPI Museum APIテスト設計

更新日: 2026-03-19

## 1. 目的

HTTP レイヤで、認証、認可、request/response 形式、DB 更新結果、soft delete の振る舞いを検証する。  
テストは `pytest` + `pytest-django` + `rest_framework.test.APIClient` を前提とする。

## 2. 使用モジュール

- `pytest`
- `pytest-django`
- `factory-boy`
- `rest_framework.test.APIClient`
- `pytest-mock`
- `moto`

## 3. 共通方針

- user 系 API は JWT 認証で検証する
- guest 系 API は `X-Guest-Id` ヘッダで検証する
- response は camelCase を正とし、request は camelCase / snake_case の差異を契約テストでも監視する
- DB 検証は active row と soft-deleted row の両方を確認する

## 4. 主要 API とケース

### Auth API

対象:
- `POST /api/auth/guest/`
- `POST /api/token/`
- `POST /api/token/refresh/`
- `GET /api/me/`

ケース:
- guest issue が 200 と `guestId` を返す
- token 発行が有効 user で成功する
- 無効 credential は 400 または 401
- `me` は JWT ありで成功、無しで 401

### Guest Gallery API

対象:
- `GET /api/guest/gallery/`
- `POST /api/guest/gallery/`
- `PATCH /api/guest/gallery/`
- `DELETE /api/guest/gallery/`

ケース:
- `X-Guest-Id` 無しは拒否
- 初回 POST は 201、再POST は既存 gallery を 200 で返す
- GET は active gallery のみ返す
- PATCH は許可フィールドのみ更新する
- DELETE は soft delete になる
- delete 後の GET は 404

### User Gallery API

対象:
- `GET /api/galleries/`
- `POST /api/galleries/`
- `GET /api/galleries/{id}/`
- `PATCH /api/galleries/{id}/`
- `DELETE /api/galleries/{id}/`

ケース:
- 自分の gallery のみ取得できる
- 他人の gallery は参照・更新・削除できない
- DELETE は soft delete され、一覧から消える

### Exhibit API

対象:
- `POST /api/galleries/{gallery_id}/exhibits/`
- `PUT /api/galleries/{gallery_id}/exhibits/{slot_index}/`
- `DELETE /api/galleries/{gallery_id}/exhibits/{slot_index}/`

ケース:
- owner / guest_id が一致する gallery にのみ操作できる
- occupied slot への POST は 409
- PUT は新規で 201、更新で 200
- DELETE は 204、削除済み slot は 404
- request payload に `owner` や `guestId` を入れても上書きされない

### Public Gallery API

対象:
- `GET /api/galleries/g/{slug}/`

ケース:
- public かつ active gallery のみ返す
- deleted exhibit を `exhibits` に含めない
- `owner` `guestId` を露出しない
- private gallery は 404

### Upload API

対象:
- `POST /api/uploads/issue/`
- `POST /api/uploads/confirm/`

ケース:
- user / guest の両経路で issue が成功する
- `purpose=exhibit_image` を許可する
- 不正 purpose は拒否する
- `moto` で `head_object` 成功時のみ confirm 成功を確認する
- owner 不一致 session の confirm は 404
- S3 にファイルが無い場合は 400

### rembg API

対象:
- `POST /api/image/rembg/{model_name}/`

ケース:
- request body が `process_event` に正しく渡る
- 正常応答が JSON として返る
- 例外系は service 側の戻り値に応じて status code が反映される

## 5. データ設計

### factory-boy
- `UserFactory`
- `GalleryFactory(user_style="user")`
- `GalleryFactory(user_style="guest")`
- `ExhibitFactory`
- `UploadSessionFactory`

### fixture
- `api_client`: `APIClient`
- `user_client`
- `guest_client`
- `user_token`
- `guest_headers`

## 6. 優先度

1. Guest Gallery API
2. Exhibit API
3. Upload API
4. Public Gallery API
5. Auth API
6. rembg API

## 7. 成果物イメージ

```text
tests/
  api/
    test_auth_api.py
    test_guest_gallery_api.py
    test_user_gallery_api.py
    test_exhibit_api.py
    test_public_gallery_api.py
    test_upload_api.py
    test_rembg_api.py
```
