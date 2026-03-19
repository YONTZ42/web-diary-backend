# DjangoAPI Museum Smokeテスト設計

更新日: 2026-03-19

## 1. 目的

主要ユースケースが壊れていないことを、少数ケースで高速に検証する。  
Smoke は詳細な境界値検証ではなく、正常系の縦断確認を優先する。

## 2. 使用モジュール

- `pytest`
- `pytest-django`
- `rest_framework.test.APIClient`
- `factory-boy`
- `pytest-mock`
- `moto`

## 3. 前提

- 現行コードには `healthz` / `readyz` が無いため、health endpoint smoke は設計対象外
- smoke はローカル CI では DB + モック S3 ベース、staging では実環境URLベースで再利用できる形にする

## 4. Smoke シナリオ

### Guest happy path

1. `POST /api/auth/guest/`
2. `POST /api/guest/gallery/`
3. `POST /api/uploads/issue/`
4. `POST /api/uploads/confirm/`
5. `PUT /api/galleries/{gallery_id}/exhibits/{slot_index}/`
6. `PATCH /api/guest/gallery/` で `isPublic=true`
7. `GET /api/galleries/g/{slug}/`

確認:
- gallery が作成される
- upload session が confirm される
- exhibit が slot に配置される
- public gallery から exhibit が見える

### User happy path

1. factory で user 作成
2. `POST /api/token/`
3. `POST /api/galleries/`
4. `POST /api/uploads/issue/`
5. `POST /api/uploads/confirm/`
6. `PUT /api/galleries/{gallery_id}/exhibits/{slot_index}/`
7. `GET /api/me/`
8. `GET /api/galleries/{id}/`

確認:
- JWT 経路で museum 作成から取得まで通る
- 自分の gallery / exhibit のみ見える

### Public read path

1. public gallery と active exhibit を fixture で準備
2. `GET /api/galleries/g/{slug}/`

確認:
- 200 を返す
- private field を含まない
- slot 順で exhibits が返る

### rembg path

1. `POST /api/image/rembg/u2net/`

確認:
- service 戻り値が 200 で透過される
- CORS header が付く

## 5. 不採用シナリオ

- CloudWatch、App Runner、Alarm の監視確認
- 本物の S3 へのアップロード
- 高負荷時の性能検証

## 6. 成果物イメージ

```text
tests/
  smoke/
    test_guest_happy_path.py
    test_user_happy_path.py
    test_public_gallery_path.py
    test_rembg_smoke.py
```
