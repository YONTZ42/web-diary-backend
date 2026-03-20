# Mini Museum — 監視 / Slack通知 / Structured Logging / Health Check 統合設計書

## 1. 目的

本設計書の目的は、Mini Museum の本番運用に必要な観測基盤を一枚に統合し、以下を達成することです。

- App Runner / Lambda の異常を CloudWatch Alarm で検知し、Slack に即時通知する
- Django / Lambda のログを structured logging に統一し、CloudWatch Logs Insights で障害原因を追跡できるようにする
- App Runner の liveness と deep health check を分離し、コンテナの過剰再起動を防ぎながら依存障害を見つけられるようにする
- CPU ヘビーな `api/image/rembg/*` を通常 API と切り分けて観測し、App Runner 全体への悪影響を可視化する
- Guest / User 混在運用でも `request_id` と `guest_id` を軸にリクエスト単位で追跡できるようにする

---

## 2. 背景と現状

### 2.1 インフラ現状

- App Runner は `AppRunnerStack` でデプロイされ、health check は `path=/healthz`、`interval=10s`、`timeout=5s`、`healthyThreshold=1`、`unhealthyThreshold=5` になっている
- App Runner の instance configuration は `cpu=1024`、`memory=2048`
- `MonitoringStack` には SNS Topic、Lambda Errors alarm、Lambda Duration alarm、App Runner 5xx alarm があり、通知先は現状 email subscription
- `lambda-bg` は timeout 60 秒 / memory 2048MB / Function URL 公開
- `lambda-yolo` は timeout 90 秒 / memory 3008MB / Function URL 公開

### 2.2 アプリ現状

- Guest 識別は `X-Guest-Id` ヘッダ前提
- Guest 系は `localStorage` の `guest_id` を保持し、以後の API リクエストに `X-Guest-Id` を付与する設計
- `/healthz` で 200 を返す shallow health はあるが、DB / S3 の deep health は未実装
- Django / rembg / Lambda はまだ JSON structured logging に統一されていない

### 2.3 rembg API 現状

- `image/rembg/<str:model_name>/` を Django View で受け、`RembgProcessView` が body を Lambda 風 event に詰め直して `process_event()` に渡している
- `views_rembg.py` は現状 CORS を `*` で返し、`X-Guest-Id` を許可している
- `rembg_processor.py` は `json.loads`、`base64` / `image_url` / `s3` 入力解決、`new_session()`、`remove()`、S3 保存を 1 リクエスト内で処理している
- `rembg_processor.py` は現状 `print()` と `traceback.print_exc()` が中心で、CloudWatch Logs Insights で扱いやすい構造化ログではない
- `new_session()` が毎回初期化される構成であり、DB API と同一 App Runner サービス内に CPU ヘビー処理が同居している

### 2.4 現状の本質的なリスク

この構成では、rembg の高負荷リクエストが以下を誘発しうる。

- App Runner の RequestLatency 悪化
- 画像処理以外の通常 API のレスポンス悪化
- App Runner 5xx の増加
- メモリ圧迫や CPU 飽和による sporadic failure
- DB API と rembg API の相互干渉による再現しづらい障害

そのため、`api/image/rembg/*` は通常 API と同じ扱いにせず、**App Runner 内の画像処理ワークロード**として専用ログと専用分析軸を持たせる。

---

## 3. 全体方針

監視は次の3レイヤで構成する。

1. **メトリクス監視**  
   CloudWatch Metrics / Alarm により、5xx、Errors、Duration、Latency、Throttles を検知する

2. **ログ監視**  
   JSON structured logging により、障害の原因・入力条件・再現傾向・主体を追跡する

3. **ヘルスチェック監視**  
   `/healthz` と `/health` を分離し、liveness と readiness を明確に分ける

---

## 4. 監視アーキテクチャ

```text
CloudWatch Metrics / Alarm
        ↓
      SNS Topic
        ↓
 Slack Notify Lambda
        ↓
 Slack Incoming Webhook
```

### 4.1 採用理由

Slack 通知は AWS Chatbot でも可能だが、今回は次が必要なので webhook 方式を採用する。

- alarm ごとに本文整形したい
- stage / service / severity / runbook URL を埋め込みたい
- ALARM / OK を明示したい
- 監視設計を CDK に閉じたい

### 4.2 通知ルート

- CloudWatch Alarm が SNS Topic に publish
- SNS Topic が通知専用 Lambda を呼ぶ
- Lambda が Slack Incoming Webhook に block message を POST する

### 4.3 将来拡張

- channel を `staging` / `production` で分ける
- severity に応じて mention 制御を入れる
- runbook URL、CloudWatch Console URL を動的生成する

---

# 5. メトリクス監視設計

## 5.1 監視対象一覧

### App Runner

- `5xxStatusResponses`
- `RequestLatency`
- 将来的に `4xxStatusResponses`
- 将来的に CPU / Memory の可視化ダッシュボード

### Lambda

- `Errors`
- `Duration`
- `Throttles`
- 将来的に `ConcurrentExecutions`

---

## 5.2 CloudWatch Alarm 設計

### 5.2.1 App Runner Alarm

#### A. App Runner 5xx

- Namespace: `AWS/AppRunner`
- Metric: `5xxStatusResponses`
- Dimensions: `ServiceName`
- Statistic: `sum`
- Period: `5 minutes`
- Threshold: `>= 1`
- EvaluationPeriods: `1`
- Severity: `Critical`
- 意味: すでにユーザー影響が出ている状態

#### B. App Runner Latency Warning

- Namespace: `AWS/AppRunner`
- Metric: `RequestLatency`
- Statistic: `avg`
- Period: `5 minutes`
- Threshold: `>= 3000 ms`
- EvaluationPeriods: `2`
- Severity: `Warning`
- 意味: rembg や重い DB 処理により App Runner が詰まり始めた兆候

#### C. App Runner Latency Critical

- Namespace: `AWS/AppRunner`
- Metric: `RequestLatency`
- Statistic: `avg` または `p95`
- Period: `5 minutes`
- Threshold: `>= 5000 ms`
- EvaluationPeriods: `2`
- Severity: `Critical`
- 意味: まだ 5xx が少なくても UX 的にはかなり悪化している状態

#### D. App Runner 4xx（推奨・初期は dashboard でも可）

- 認証ヘッダ欠落
- `X-Guest-Id` 未付与
- フロントと API 契約不整合

### 5.2.2 Lambda Alarm

#### A. Lambda Errors

- Namespace: `AWS/Lambda`
- Metric: `Errors`
- Statistic: `sum`
- Period: `5 minutes`
- Threshold: `>= 1`
- EvaluationPeriods: `1`
- Severity: `Critical`

#### B. Lambda Duration Warning

- `lambda-bg`: `avg >= 15000 ms`
- `lambda-yolo`: `avg >= 25000 ms`
- Period: `5 minutes`
- EvaluationPeriods: `2`
- Severity: `Warning`

#### C. Lambda Duration Critical

- `lambda-bg`: `avg >= 30000 ms`
- `lambda-yolo`: `avg >= 45000 ms`
- Period: `5 minutes`
- EvaluationPeriods: `1`
- Severity: `Critical`

#### D. Lambda Throttles

- Metric: `Throttles`
- Statistic: `sum`
- Period: `5 minutes`
- Threshold: `>= 1`
- Severity: `Critical`

### 5.2.3 閾値理由

- `lambda-bg` timeout は 60 秒、`lambda-yolo` timeout は 90 秒
- timeout 手前でしか拾えない alarm は遅い
- 画像処理 UX は 10〜20 秒超から体感悪化が大きくなる
- App Runner は DB API と rembg API 同居なので、5xx より latency を先に拾う必要がある

---

## 5.3 Slack 通知設計

### 5.3.1 通知方式

- Slack Incoming Webhook URL は Secrets Manager に保存
- CloudWatch Alarm → SNS Topic → Notify Lambda → Slack Webhook

### 5.3.2 通知本文に含める項目

- `stage`
- `service`
- `severity`
- `alarm_name`
- `metric_name`
- `threshold`
- `state`
- `timestamp`
- `resource_name`
- `runbook_url`
- `console_url`

### 5.3.3 通知メッセージ例

```json
{
  "text": "🚨 [staging] AppRunner latency critical",
  "blocks": [
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*Mini Museum Alert*\n*Severity:* Critical\n*Alarm:* AppRunnerLatencyCritical\n*Stage:* staging\n*Service:* mini-museum-api-staging"
      }
    },
    {
      "type": "section",
      "fields": [
        { "type": "mrkdwn", "text": "*Metric:*\nAWS/AppRunner RequestLatency" },
        { "type": "mrkdwn", "text": "*Threshold:*\n>= 5000 ms / 5m" },
        { "type": "mrkdwn", "text": "*State:*\nALARM" },
        { "type": "mrkdwn", "text": "*Time:*\n2026-03-20T10:00:00+09:00" }
      ]
    }
  ]
}
```

### 5.3.4 完了条件

- App Runner 5xx / latency が Slack に飛ぶ
- Lambda errors / duration / throttles が Slack に飛ぶ
- ALARM / OK の両方を送れる

---

# 6. ログ監視設計

## 6.1 Structured Logging 設計

### 6.1.1 基本方針

- すべてのログは JSON 1 行で stdout に出力する
- text log や `print()` に依存しない
- Django / Lambda / rembg でキー名を統一する
- CloudWatch Logs Insights で検索可能な平坦な key 構造を優先する

### 6.1.2 共通必須フィールド

```json
{
  "timestamp": "2026-03-20T10:00:00.000+09:00",
  "level": "ERROR",
  "service": "mini-museum-api",
  "stage": "staging",
  "component": "django.api",
  "event": "request_failed",
  "message": "request failed",
  "request_id": "req_xxx",
  "path": "/api/...",
  "method": "POST",
  "status_code": 500,
  "duration_ms": 1234,
  "user_id": null,
  "guest_id": "guest_xxx"
}
```

### 6.1.3 共通推奨フィールド

- `trace_id`
- `error_type`
- `error_code`
- `exception`
- `client_ip`
- `user_agent`
- `gallery_id`
- `exhibit_id`
- `slot_index`

### 6.1.4 ログレベル方針

- `DEBUG`: ローカルのみ
- `INFO`: 正常開始 / 正常終了 / 主要イベント
- `WARNING`: 遅延、再試行、依存の一時不安定
- `ERROR`: リクエスト失敗、例外
- `CRITICAL`: サービス継続性に関わる障害

---

## 6.2 request_id 設計

### 6.2.1 基本方針

- すべてのログに `request_id` を付与する
- Django / Lambda でキー名は `request_id` に統一する

### 6.2.2 Django

- `X-Request-Id` があれば採用
- なければ middleware で生成する
- `request.request_id` に保存する
- レスポンスヘッダ `X-Request-Id` として返す
- logging context に bind する

### 6.2.3 Lambda

- request header に `X-Request-Id` があれば採用
- なければ関数側で生成する
- AWS 由来の `aws_request_id` は別フィールドで保持する

### 6.2.4 Guest 識別

- `guest_id` は必須級の追跡キー
- User ログイン時は `user_id`、Guest 時は `guest_id` を必ず埋める
- Guest 系障害は `user_id` だけでは追えないため、`guest_id` を省略しない

---

## 6.3 Django ログ設計

### 6.3.1 ロガー分類

Django は少なくとも以下に分ける。

- `django.access`
- `django.api`
- `django.auth`
- `django.health`
- `django.rembg`

### 6.3.2 なぜ rembg を分けるか

`api/image/rembg/*` は Django View だが、実態は通常 CRUD API ではなく画像前処理ワークロードである。DB API と同じ `django.api` に混ぜると以下が見えなくなる。

- rembg 起因の高遅延
- rembg 特有の失敗点
- 入力形式ごとの失敗傾向
- model ごとの遅延差
- App Runner 圧迫要因の特定

そのため、`django.rembg` を独立ロガーとして扱う。

### 6.3.3 Django 全体イベント一覧

#### `django.access`

- `request_started`
- `request_finished`
- `request_failed`

#### `django.auth`

- `guest_header_missing`
- `guest_authenticated`
- `user_authenticated`
- `permission_denied`

#### `django.api`

- `gallery_get_succeeded`
- `gallery_create_succeeded`
- `gallery_create_conflict`
- `gallery_delete_soft_succeeded`
- `gallery_delete_soft_failed`
- `exhibit_upsert_succeeded`
- `exhibit_upsert_failed`
- `exhibit_delete_soft_succeeded`
- `exhibit_delete_soft_failed`
- `upload_issue_succeeded`
- `upload_issue_failed`
- `upload_confirm_succeeded`
- `upload_confirm_failed`

#### `django.health`

- `healthz_ok`
- `health_ok`
- `health_degraded`
- `health_dependency_failed`

#### `django.rembg`

- `rembg_request_started`
- `rembg_request_succeeded`
- `rembg_request_failed`
- `rembg_invalid_json`
- `rembg_invalid_image_data`
- `rembg_image_fetch_started`
- `rembg_image_fetch_failed`
- `rembg_s3_get_started`
- `rembg_s3_get_failed`
- `rembg_model_init_started`
- `rembg_model_init_failed`
- `rembg_inference_started`
- `rembg_inference_failed`
- `rembg_s3_put_started`
- `rembg_s3_put_failed`
- `rembg_presigned_url_failed`
- `rembg_slow_request`

### 6.3.4 Django access log 例

```json
{
  "timestamp": "2026-03-20T10:10:00.000+09:00",
  "level": "INFO",
  "service": "mini-museum-api",
  "stage": "staging",
  "component": "django.access",
  "event": "request_finished",
  "message": "request completed",
  "request_id": "req_123",
  "path": "/api/guest/gallery/",
  "method": "POST",
  "status_code": 200,
  "duration_ms": 124,
  "user_id": null,
  "guest_id": "guest_123"
}
```

### 6.3.5 Django API error 例

```json
{
  "timestamp": "2026-03-20T10:11:00.000+09:00",
  "level": "ERROR",
  "service": "mini-museum-api",
  "stage": "staging",
  "component": "django.api",
  "event": "exhibit_upsert_failed",
  "message": "failed to process exhibit update",
  "request_id": "req_456",
  "path": "/api/galleries/123/exhibits/4/",
  "method": "PUT",
  "status_code": 500,
  "gallery_id": "123",
  "slot_index": 4,
  "guest_id": "guest_123",
  "error_type": "ValidationError",
  "error_code": "EXHIBIT_UPSERT_FAILED"
}
```

---

## 6.4 rembg 専用ログ設計

## 6.4.1 結論

`api/image/rembg/*` は Django のエラーログに必ず含める。しかも通常 API の `request_failed` に埋もれさせず、**専用 event と追加フィールド**を持つ `django.rembg` ロガーで扱う。

## 6.4.2 rembg に追加する必須フィールド

```json
{
  "component": "django.rembg",
  "event": "rembg_inference_failed",
  "path": "/api/image/rembg/isnet-general-use/",
  "model_name": "isnet-general-use",
  "input_source": "image_url",
  "source_image_size_bytes": 7340032,
  "image_width": null,
  "image_height": null,
  "alpha_matting": false,
  "s3_bucket": "mini-museum-staging-assets",
  "s3_key": "removed_bg/xxxx.png",
  "duration_ms": 18234,
  "error_type": "RuntimeError",
  "error_code": "REMBG_INFERENCE_FAILED"
}
```

## 6.4.3 rembg 失敗ポイントを網羅した event / error_code 設計

### 入力前段

1. **body JSON decode 失敗**
   - event: `rembg_invalid_json`
   - error_code: `REMBG_INVALID_JSON`

2. **body は JSON だが必要パラメータ不足**
   - event: `rembg_invalid_params`
   - error_code: `REMBG_INVALID_PARAMS`

3. **`image_data` base64 decode 失敗**
   - event: `rembg_invalid_image_data`
   - error_code: `REMBG_INVALID_IMAGE_DATA`

4. **`image_url` 取得失敗**
   - event: `rembg_image_fetch_failed`
   - error_code: `REMBG_IMAGE_FETCH_FAILED`
   - 追加項目: `source_url`, `http_status`, `timeout_ms`

5. **S3 から元画像取得失敗**
   - event: `rembg_s3_get_failed`
   - error_code: `REMBG_S3_GET_FAILED`
   - 追加項目: `s3_bucket`, `s3_key`

### モデル / 推論

6. **許可外 model_name**
   - event: `rembg_invalid_model`
   - error_code: `REMBG_INVALID_MODEL`

7. **`new_session()` 初期化失敗**
   - event: `rembg_model_init_failed`
   - error_code: `REMBG_MODEL_INIT_FAILED`

8. **`remove()` 実行失敗**
   - event: `rembg_inference_failed`
   - error_code: `REMBG_INFERENCE_FAILED`

9. **極端な遅延だが成功**
   - event: `rembg_slow_request`
   - level: `WARNING`
   - error_code: なし

### 出力 / 保存

10. **S3 保存失敗**
    - event: `rembg_s3_put_failed`
    - error_code: `REMBG_S3_PUT_FAILED`

11. **presigned URL 生成失敗**
    - event: `rembg_presigned_url_failed`
    - error_code: `REMBG_PRESIGNED_URL_FAILED`

12. **最終レスポンス整形失敗**
    - event: `rembg_response_build_failed`
    - error_code: `REMBG_RESPONSE_BUILD_FAILED`

## 6.4.4 rembg 成功ログも必須にする理由

rembg は失敗だけ見れば足りない。成功でも遅ければ App Runner 全体に悪影響を与える。よって次のルールにする。

- 成功: `INFO`
- 失敗: `ERROR`
- 閾値超え成功: `WARNING`

### rembg 遅延判定案

- `duration_ms >= 5000` → `rembg_slow_request`
- `duration_ms >= 10000` → 追加で `severity=high` を付与してもよい

## 6.4.5 rembg 代表ログ例

### 開始ログ

```json
{
  "level": "INFO",
  "component": "django.rembg",
  "event": "rembg_request_started",
  "message": "rembg request started",
  "request_id": "req_123",
  "path": "/api/image/rembg/isnet-general-use/",
  "method": "POST",
  "guest_id": "guest_123",
  "model_name": "isnet-general-use",
  "input_source": "image_url"
}
```

### 遅延 WARNING

```json
{
  "level": "WARNING",
  "component": "django.rembg",
  "event": "rembg_slow_request",
  "message": "rembg request is slow",
  "request_id": "req_123",
  "path": "/api/image/rembg/isnet-general-use/",
  "duration_ms": 8123,
  "model_name": "isnet-general-use",
  "input_source": "image_url",
  "guest_id": "guest_123"
}
```

### 失敗 ERROR

```json
{
  "level": "ERROR",
  "component": "django.rembg",
  "event": "rembg_inference_failed",
  "message": "rembg inference failed",
  "request_id": "req_123",
  "path": "/api/image/rembg/isnet-general-use/",
  "method": "POST",
  "status_code": 500,
  "duration_ms": 11234,
  "guest_id": "guest_123",
  "model_name": "isnet-general-use",
  "input_source": "image_data",
  "error_type": "RuntimeError",
  "error_code": "REMBG_INFERENCE_FAILED"
}
```

---

## 6.5 Lambda ログ設計

### 6.5.1 方針

Lambda はフロントから直接叩かれるため、「失敗した」だけでは弱い。最低限、**入力サイズ・処理時間・モデル・出力数・失敗理由**を出す。

### 6.5.2 共通必須フィールド

```json
{
  "timestamp": "2026-03-20T10:20:00.000+09:00",
  "level": "ERROR",
  "service": "mini-museum-image",
  "stage": "staging",
  "component": "lambda-yolo",
  "event": "yolo_inference_failed",
  "message": "yolo segmentation failed",
  "request_id": "req_yyy",
  "aws_request_id": "aws_yyy",
  "function_name": "mini-museum-staging-yoloprocessor",
  "path": "/",
  "method": "POST",
  "status_code": 500,
  "guest_id": "guest_123",
  "source_image_size_bytes": 7340032,
  "image_width": 3024,
  "image_height": 4032,
  "memory_limit_mb": 3008,
  "duration_ms": 28432,
  "model_name": "yolo-seg",
  "output_count": 0,
  "s3_bucket": "xxx",
  "s3_key": "yyy",
  "error_type": "RuntimeError",
  "error_code": "YOLO_INFERENCE_FAILED"
}
```

### 6.5.3 Lambda イベント一覧

#### `lambda-bg`

- `background_remove_started`
- `background_remove_succeeded`
- `background_remove_failed`
- `background_remove_slow`
- `background_s3_put_failed`

#### `lambda-yolo`

- `yolo_inference_started`
- `yolo_inference_succeeded`
- `yolo_inference_failed`
- `yolo_inference_slow`
- `yolo_s3_put_failed`

### 6.5.4 Lambda で網羅すべき失敗フロー

1. request body parse 失敗
2. input image 欠落
3. input image decode 失敗
4. model load / session init 失敗
5. inference 失敗
6. output 0 件想定外
7. S3 upload 失敗
8. timeout 手前の遅延
9. メモリ不足相当の失敗

### 6.5.5 Lambda 成功ログ例

```json
{
  "timestamp": "2026-03-20T10:21:00.000+09:00",
  "level": "INFO",
  "service": "mini-museum-image",
  "stage": "staging",
  "component": "lambda-bg",
  "event": "background_remove_succeeded",
  "message": "background removal completed",
  "request_id": "req_789",
  "aws_request_id": "aws_123",
  "function_name": "mini-museum-staging-backgroundgenerator",
  "guest_id": "guest_123",
  "source_image_size_bytes": 5242880,
  "image_width": 2048,
  "image_height": 2048,
  "duration_ms": 8420,
  "status_code": 200,
  "s3_key": "removed_bg/xxx.png"
}
```

---

## 6.6 実装指針

### 6.6.1 Django logging ライブラリ

- 第一候補: `structlog`
- 第二候補: `python-json-logger`

`structlog` 推奨理由:

- request context bind がしやすい
- `request_id`, `guest_id`, `user_id`, `path`, `component` を共通 processor で差し込める
- rembg の途中イベントを段階的に出しやすい

### 6.6.2 Django logging 実装方針

- stdout JSON 1 行
- `print()` 禁止
- 例外は `exception` フィールドに格納
- `guest_id`, `request_id`, `path`, `component`, `event` を必須キーにする

### 6.6.3 rembg 実装修正方針

`rembg_processor.py` で最低限ログを出すポイント:

1. request 開始
2. body parse 完了 / 失敗
3. input source 判定
4. image fetch / decode 開始 / 成功 / 失敗
5. model_name 決定
6. session 初期化開始 / 成功 / 失敗
7. inference 開始 / 成功 / 失敗
8. S3 書き込み開始 / 成功 / 失敗
9. presigned URL 生成開始 / 成功 / 失敗
10. total duration

### 6.6.4 今の rembg 構成に関する設計上の警告

- `new_session()` を毎回呼ぶ構成は遅延と不安定化の温床
- App Runner に DB API と CPU ヘビー処理を同居させるのは運用リスクが高い

### 6.6.5 今後の改善優先順位

- 短期: structured logging で実態可視化
- 中期: session 再利用検討
- 長期: rembg を App Runner から分離する検討

---

## 6.7 CloudWatch Logs Insights 前提のクエリ設計

### 6.7.1 Django エラー全体

```sql
fields @timestamp, level, component, event, message, request_id, path, method, status_code, guest_id, user_id, error_type, error_code
| filter level = "ERROR"
| sort @timestamp desc
| limit 100
```

### 6.7.2 rembg の失敗だけ追う

```sql
fields @timestamp, level, event, request_id, path, model_name, input_source, duration_ms, error_code, error_type, guest_id
| filter component = "django.rembg"
| filter level = "ERROR"
| sort @timestamp desc
| limit 50
```

### 6.7.3 rembg の高遅延だけ追う

```sql
fields @timestamp, event, request_id, model_name, input_source, duration_ms, guest_id
| filter component = "django.rembg"
| filter event = "rembg_slow_request"
| sort duration_ms desc
| limit 50
```

### 6.7.4 特定 request_id の追跡

```sql
fields @timestamp, component, event, message, request_id, path, status_code, duration_ms
| filter request_id = "req_123"
| sort @timestamp asc
```

### 6.7.5 Guest 単位の障害追跡

```sql
fields @timestamp, component, event, message, guest_id, request_id, status_code
| filter guest_id = "guest_123"
| sort @timestamp desc
| limit 100
```

### 6.7.6 Lambda 高遅延分析

```sql
fields @timestamp, component, event, duration_ms, source_image_size_bytes, image_width, image_height, request_id, error_code
| filter component in ["lambda-bg", "lambda-yolo"]
| sort duration_ms desc
| limit 100
```

### 6.7.7 Gallery / Exhibit 系競合検知

```sql
fields @timestamp, component, event, request_id, gallery_id, slot_index, error_code, status_code, guest_id
| filter event like /gallery_|exhibit_/
| filter level = "ERROR"
| sort @timestamp desc
| limit 100
```

---

# 7. ヘルスチェック監視設計

## 7.1 基本方針

- `/healthz` は App Runner の liveness 用
- `/health` は運用用 deep check
- deep check を `/healthz` に載せない

### 理由

App Runner health check は「アプリプロセスが生きているか」を見るべきであり、DB / S3 の一時揺れでコンテナ自体を unhealthy 扱いにすると逆効果だから。

---

## 7.2 ヘルスチェック設計

### 7.2.1 `GET /healthz`

用途:

- App Runner container health check 専用
- shallow check

仕様:

- アプリが起動していれば 200
- DB / S3 / 外部 HTTP には接続しない
- 軽量レスポンスのみ返す

レスポンス例:

```json
{
  "status": "ok",
  "service": "mini-museum-api",
  "stage": "staging"
}
```

### 7.2.2 `GET /health`

用途:

- 外形監視
- 手動確認
- 運用ダッシュボード

仕様:

- DB 接続確認
- S3 接続確認
- app version / stage を返す
- 依存失敗時は 503

レスポンス例:

```json
{
  "status": "ok",
  "checks": {
    "db": "ok",
    "s3": "ok"
  },
  "service": "mini-museum-api",
  "stage": "staging"
}
```

degraded 例:

```json
{
  "status": "degraded",
  "checks": {
    "db": "ok",
    "s3": "error"
  },
  "service": "mini-museum-api",
  "stage": "staging"
}
```

### 7.2.3 DB チェック

- `SELECT 1`
- 短い timeout を設定
- ORM の重いクエリは使わない

### 7.2.4 S3 チェック

- `head_bucket` または `list_objects_v2(MaxKeys=1)`
- 書き込みチェックはしない
- `/health` でのみ実行

---

## 7.3 ヘルスチェック監視ログ

### `django.health` で出すログ

- `/healthz` 正常: `healthz_ok`
- `/health` 正常: `health_ok`
- `/health` degraded: `health_degraded`
- DB 失敗: `health_dependency_failed`, `dependency=db`
- S3 失敗: `health_dependency_failed`, `dependency=s3`

### ログ例

```json
{
  "level": "ERROR",
  "component": "django.health",
  "event": "health_dependency_failed",
  "message": "health dependency failed",
  "dependency": "s3",
  "request_id": "req_health_123",
  "path": "/health",
  "status_code": 503,
  "error_code": "HEALTH_S3_FAILED"
}
```

---

# 8. 障害フロー網羅表

## 8.1 App Runner / Django API

| フロー | 想定異常 | ログ | メトリクス / 監視 |
|---|---|---|---|
| Guest API 呼び出し | `X-Guest-Id` 欠落 | `guest_header_missing` | 4xx dashboard |
| Guest gallery POST | 一意制約衝突 / 再作成競合 | `gallery_create_conflict` | ERROR logs |
| Exhibit PUT | validation 失敗 | `exhibit_upsert_failed` | ERROR logs |
| Upload issue | presign 生成失敗 | `upload_issue_failed` | ERROR logs |
| Upload confirm | S3 object 未整合 | `upload_confirm_failed` | ERROR logs |
| Public gallery GET | slug 不整合 | `public_gallery_not_found` | 404 dashboard |

## 8.2 rembg

| フロー | 想定異常 | ログ | 監視 |
|---|---|---|---|
| body parse | JSON 不正 | `rembg_invalid_json` | ERROR logs |
| image_data decode | base64 不正 | `rembg_invalid_image_data` | ERROR logs |
| image_url fetch | 取得不能 / timeout | `rembg_image_fetch_failed` | ERROR logs |
| S3 input fetch | object なし | `rembg_s3_get_failed` | ERROR logs |
| model 判定 | 許可外 model | `rembg_invalid_model` | ERROR logs |
| session init | `new_session()` 失敗 | `rembg_model_init_failed` | ERROR logs |
| remove | 推論失敗 | `rembg_inference_failed` | ERROR logs |
| S3 output put | 保存失敗 | `rembg_s3_put_failed` | ERROR logs |
| presigned URL | URL 生成失敗 | `rembg_presigned_url_failed` | ERROR logs |
| 成功だが重い | 5秒超 | `rembg_slow_request` | WARNING logs / App Runner latency |

## 8.3 Lambda

| フロー | 想定異常 | ログ | 監視 |
|---|---|---|---|
| body parse | JSON 不正 | `*_invalid_json` | ERROR logs |
| input decode | 入力壊れ | `*_invalid_input` | ERROR logs |
| model load | モデルロード失敗 | `*_model_init_failed` | ERROR logs |
| inference | 推論失敗 | `*_inference_failed` | Errors alarm |
| S3 upload | 保存失敗 | `*_s3_put_failed` | ERROR logs |
| 高遅延 | timeout 手前 | `*_slow` | Duration alarm |
| 同時実行 | throttle | `*_throttled` | Throttles alarm |

---

# 9. CDK 実装方針

## 9.1 MonitoringStack の拡張

追加するもの:

- `slackWebhookSecretArn`
- `notificationLambda`
- `LambdaSubscription(notificationLambda)`
- App Runner latency alarm
- Lambda throttles alarm
- 将来的に composite alarm

## 9.2 スタック分割案

### 案A: `MonitoringStack` に集約

- alarms
- topic
- notify lambda
- secret 参照

### 案B: `AlertingStack` を分離

- `MonitoringStack`: metrics / alarms / topic
- `AlertingStack`: Slack notify lambda / secret / subscription

現時点では規模上、`MonitoringStack` にまとめてもよい。

---

# 10. 実装優先順位

## Phase 1

1. SNS → Slack notify Lambda
2. App Runner 5xx / latency alarm
3. Lambda errors / duration / throttles alarm
4. request_id middleware
5. Django structured logging 導入
6. `django.rembg` 専用ロガー追加
7. 通知テスト

## Phase 2

8. `views_rembg.py` で request context bind
9. `rembg_processor.py` の `print()` 廃止
10. rembg event / error_code 細分化
11. Lambda structured logging helper 導入
12. `/health` deep health 実装

## Phase 3

13. Logs Insights / Dashboard 整備
14. rembg session 再利用検討
15. rembg 分離検討

---

# 11. 完了条件

## 11.1 メトリクス監視

- App Runner 5xx で Slack 通知
- App Runner 高遅延で Slack 通知
- Lambda errors / duration / throttles で Slack 通知

## 11.2 ログ監視

- Django ログが JSON structured logging になっている
- `request_id`, `user_id`, `guest_id` が含まれる
- `api/image/rembg/*` が `django.rembg` として独立追跡できる
- rembg の失敗が `error_code` 単位で分類できる
- rembg 成功でも高遅延なら `WARNING` が出る
- Lambda ログに画像サイズ・duration・error_type が含まれる
- CloudWatch Logs Insights で `request_id` 単位追跡ができる

## 11.3 ヘルスチェック監視

- `/healthz` は shallow check
- `/health` は DB / S3 deep check
- deep check failure は 503
- `django.health` で依存失敗理由がログに出る

---

# 12. 最重要ポイント

1. **`/healthz` を deep check にしない**  
   App Runner の health check は liveness に限定する。DB / S3 依存は `/health` に切り分ける。

2. **`request_id` と `guest_id` を追跡の主キーにする**  
   Guest 前提の利用が強いので、`user_id` だけでは障害追跡が成立しない。

3. **`api/image/rembg/*` は Django エラーログ対象に必ず含める**  
   しかも `django.api` に混ぜず、`django.rembg` の専用ロガーで扱う。

4. **rembg は失敗だけでなく高遅延も記録する**  
   DB API と同居する以上、「成功したが重い」は障害予兆そのもの。

5. **Lambda も成功・失敗・高遅延の3系統で観測する**  
   画像処理 UX は timeout 直前よりはるか手前で悪化する。

