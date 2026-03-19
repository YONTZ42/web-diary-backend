# Digital Miniature Museum — 仕様書 v5（Guest分離 + 論理削除 + 部分ユニーク制約）

> 本版は、あなたが追記した **9〜13** の更新内容（認証・論理削除・DB制約・Guest専用API）を取り込み、既存の「LP表示で `POST /api/auth/guest/` を呼び、`guest_id` を localStorage に保存し、以後 `X-Guest-Id` を付与する」仕様と整合させた正式版です。fileciteturn1file0L41-L48

---

## 1. 目的 / スコープ

- 写真を「ミニチュア展示室」に展示し、WebGPU空間で鑑賞できるデジタルギャラリーアプリ
- フロントは SPA（`/app`） + 公開Viewer（`/g/{slug}`） + LP（`/`）構成 fileciteturn1file0L30-L37
- 認証は **User（ログイン）** と **Guest（ヘッダ識別）** を **APIとして分離（B方式）** する

---

## 2. ルーティング（フロント）

| ルート | 内容 |
|---|---|
| `/` | LP（ゲスト自動発行） |
| `/login` | ログイン選択 |
| `/app` | アプリ本体（2タブ） |
| `/g/{slug}` | 公開Viewer（閲覧専用） |

### 2.1 LPでのゲスト自動発行（最重要）
LP表示時に以下を同時に実行する：fileciteturn1file0L43-L48

1) `POST /api/auth/guest/`（未発行の場合）  
2) 取得した `guest_id` を localStorage に保存  
3) 以後の全APIリクエストに `X-Guest-Id: <string>` を付与  

---

## 3. 認証・認可（更新：v5）

## 9. 認証仕様（更新）

### 9.1 User認証（ログインユーザー）
- Django標準の **`IsAuthenticated`**
- 所有者はモデルの `owner`（例：`Gallery.owner`, `Exhibit.owner`）で管理
- 認可は View 層で実施（例：対象オブジェクトの `owner == request.user` を必須）

### 9.2 Guest認証（新設）
Guest は以下ヘッダで識別する：

- `X-Guest-Id: <string>`

ルール：
- **Cookie は使用しない**（Guest識別に cookie/session を使わない）
- サーバ側で `user.is_authenticated == False` の場合に `X-Guest-Id` を参照
- **DBに恒久ユーザー（User行）は作成しない**
- 認証と認可は **View 側**で行う  
  - 例：`guest_id = request.headers.get("X-Guest-Id")` を必須化  
  - 例：`Gallery.user_style == "guest" && Gallery.guest_id == guest_id` を必須化

> 既存の「`request.user` があれば優先、なければ `X-Guest-Id`」の考え方は残しつつ、**API自体を分離**して、誤混入（GuestがUser APIを叩く等）を設計で防ぐ。fileciteturn1file0L73-L76

---

## 4. データモデル（要点）

### 4.1 Gallery（更新：論理削除）
- `deleted_at: datetime | null` を追加（論理削除）
- **物理削除は禁止**
- 有効データは `deleted_at IS NULL` のみ

### 4.2 Exhibit（更新：論理削除）
- `deleted_at: datetime | null` を追加（論理削除）
- 有効データは `deleted_at IS NULL` のみ

---

## 10. Gallery仕様（更新）

### 10.1 Galleryの削除方式
- Gallery は **論理削除（deleted_at）**
- **物理削除は禁止**
- **すべてのクエリは `deleted_at__isnull=True` を含める**
  - Djangoでは `Gallery.objects.filter(deleted_at__isnull=True)` を基本
  - Public API も同様（削除済は返さない）

### 10.2 Guestは1つまでGalleryを保持可能
- Guest は有効な（`deleted_at IS NULL`）Gallery を **1つのみ**保持可能
- 削除後は再作成可能

### 10.3 DB制約（部分ユニーク）
```py
UniqueConstraint(
    fields=["guest_id"],
    condition=Q(user_style="guest", deleted_at__isnull=True),
    name="uq_guest_active_gallery",
)
```

---

## 11. Exhibit仕様（更新）

### 11.1 削除方式
- Exhibit も論理削除（`deleted_at`）
- 有効データは `deleted_at IS NULL` のみ

### 11.2 slot_indexの一意性（重要）
1つの Gallery 内で：
- 同じ `slot_index` に有効な Exhibit は **1つのみ**

DB制約（部分ユニーク）：
```py
UniqueConstraint(
    fields=["gallery", "slot_index"],
    condition=Q(deleted_at__isnull=True),
    name="uq_active_exhibit_per_slot",
)
```

---

## 12. API構成（更新）

### 12.1 Guest専用エンドポイント（新設）
| Method | Path | 動作 |
|---|---|---|
| GET | `/api/guest/gallery/` | 自分のGallery取得 |
| POST | `/api/guest/gallery/` | 無ければ作成、あれば既存返却（idempotent-ish） |
| PATCH | `/api/guest/gallery/` | `title` / `layout` 等の更新 |
| DELETE | `/api/guest/gallery/` | 論理削除（`deleted_at` をセット） |

認証：
- `X-Guest-Id` 必須（未指定は 401/400）

重要挙動（Guest 1 Gallery制約）：
- POST は「作る」ではなく **「確保する」**  
  - 既存があればそれを返す  
  - 無ければ新規作成して返す  
- DELETE で `deleted_at` を入れると、次の POST で新規作成可能

### 12.2 Exhibit API（明文化）
| Method | Path | 動作 |
|---|---|---|
| POST | `/api/galleries/{gallery_id}/exhibits/` | 追加（slot_index を指定して作成） |
| PUT | `/api/galleries/{gallery_id}/exhibits/{slot_index}/` | そのslotを上書き（upsert運用） |
| DELETE | `/api/galleries/{gallery_id}/exhibits/{slot_index}/` | 論理削除（そのslotの有効Exhibitを削除扱い） |

認証方式：
- User → `IsAuthenticated`
- Guest → `X-Guest-Id`

認可（例）：
- Gallery が User 所有なら `owner == request.user`
- Gallery が Guest 所有なら `guest_id == X-Guest-Id`
- Exhibit は必ず所属 Gallery の所有ルールに従う

---

## 13. 設計原則（追記）

- ビジネスルールは **DB制約で保証**する
- 論理削除前提で **部分ユニーク制約**を使う
- Guest と User の API は **分離（B方式）**
- Public API は削除済みデータを返さない

---

## 14. 実装ガイド（Django / DRF）

### 14.1 Queryset の基本フィルタ
- `deleted_at IS NULL` を基本にする
- ViewSet / APIView の `get_queryset()` で必ず適用  
- 可能なら `ActiveQuerySet` / `ActiveManager` を用意して取りこぼしを防ぐ

### 14.2 論理削除の実装
- `destroy()` は `deleted_at = timezone.now()` に差し替える
- 物理削除は使わない（`delete()` は呼ばない）

### 14.3 409 / 400 の扱い（おすすめ）
- DB制約違反（Guestが2つ目を作ろうとした等）は **409 Conflict** が扱いやすい
- `X-Guest-Id` 未指定は **401 Unauthorized**（または 400）で統一

---

## 15. フロントへの影響点（差分だけ）

- Cookieを使わない方針になったので、Guest識別は **localStorageの guest_id + `X-Guest-Id` 自動付与**に一本化 fileciteturn1file0L45-L48
- Guestの Gallery 操作は **`/api/guest/gallery/`** に集約（従来の `/api/galleries/` を Guest で叩かない）
- Exhibit は引き続き `/api/galleries/{gallery_id}/exhibits/...` を使用（ただし認可は owner/guest_id で厳密に）

---

## 付録：この版で確定した「やらないこと」

- Guest を Django User として永続化（作らない）
- Gallery / Exhibit の物理削除
- 削除済みデータの Public 返却
