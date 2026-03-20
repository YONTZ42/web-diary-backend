# MiniMuseum backend test scaffold

この雛形は、以下の仕様に合わせて作っています。

- API テスト設計の基準: `backend_test_design_museum_api.md`
- Guest / User 分離と soft delete の仕様: `specification_v5_guest_softdelete.md`

## 追加した補足ケース

設計書に加えて、次を足しています。

- Guest Gallery: soft delete 後に再作成できる
- User Gallery: soft-deleted row が一覧に出ない
- Public Gallery: soft-deleted gallery は 404
- Upload: guest confirm 成功パス
- Auth: token refresh 成功
- Smoke: `/api/galleries/` は認証つきで 200 を確認

## 先に直す場所

このままだと import path があなたの実プロジェクトと一致しない可能性があります。
まず `tests/support/_app.py` の環境変数か既定値を合わせてください。

- `MUSEUM_APP_LABEL`
- `VIEWS_MODULE`
- `VIEWS_UPLOAD_MODULE`
- `REMBG_PROCESSOR_MODULE`

## 想定コマンド

```bash
pytest tests/unit -q
pytest tests/api -q
pytest tests/smoke -q
pytest --maxfail=1 --disable-warnings -q
```

## 依存追加

```bash
pip install pytest pytest-django pytest-mock factory-boy moto boto3 djangorestframework-simplejwt
```

## 注意

- `tests/unit/test_auth_branching.py` は `views.py` にある認証分岐 helper 名を仮で `resolve_gallery_owner` / `assert_guest_gallery_access` としています。実名に合わせて変更が必要です。
- `tests/api/test_rembg_api.py` の patch 先は仮で `museum.views.process_event` です。実際の view module に合わせて修正してください。
- Upload confirm の request body key は `uploadSessionId` を使っています。実実装が `upload_session_id` なら置き換えてください。
