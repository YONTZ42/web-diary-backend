Mini Museum — 監視 / Slack通知 / Structured Logging / Health Check 設計書 v3
1. 目的

本設計書の目的は、Mini Museum の運用監視基盤を整備し、以下を実現することです。

App Runner / Lambda の障害を CloudWatch Alarm で検知する

SNS 経由で Slack に即時通知する

Django / Lambda のログを structured logging に統一し、CloudWatch Logs 上で障害原因を追跡可能にする

App Runner の liveness と運用用 deep health check を分離する

画像処理系、とくに api/image/rembg/* の重い処理に対して、遅延・失敗・再発傾向を追えるようにする

2. 背景と現状
2.1 インフラ現状

App Runner は CDK の AppRunnerStack でデプロイされており、HTTP health check path は /healthz、interval 10 秒、timeout 5 秒、unhealthyThreshold 5 の設定です。Monitoring は MonitoringStack で管理予定で、すでに SNS Topic、Lambda Errors alarm、Lambda Duration alarm、App Runner 5xxStatusResponses alarm が入っていますが、通知先は email subscription 前提で、Slack webhook 連携と App Runner latency 監視は未整備です。

画像処理系 Lambda は lambda-bg が timeout 60 秒・memory 2048MB、lambda-yolo が timeout 90 秒・memory 3008MB で、どちらも Function URL でフロントから直接叩かれる構成です。UX に直結するため、失敗だけでなく高遅延監視も必要です。

2.2 アプリ現状

Guest は X-Guest-Id で識別する設計で、以後の API リクエストには X-Guest-Id を付与する前提です。したがって運用ログも user_id だけでなく guest_id を追跡キーとして持つ必要があります。

2.3 rembg API 現状

Django 側には image/rembg/<str:model_name>/ ルートが定義され、RembgProcessView が POST を受けて、Lambda 互換の event 形式に詰め直して process_event() を呼び出しています。CORS は X-Guest-Id を許可しています。

rembg_processor.py では、毎リクエストごとに body を JSON decode し、画像入力を base64 / image_url / S3 から取得し、new_session() で model session を生成し、その後 remove() を実行して結果を S3 に保存しています。例外時は print() と traceback.print_exc() のみで、構造化ログにはなっていません。さらに new_session() をリクエスト内で毎回生成しているため、CPU 負荷と遅延の両面で重くなりやすい構成です。

3. 重要な設計判断
3.1 api/image/rembg/* を Django のエラーログ対象に含めるか

結論として、含めるべきです。しかも通常 API と同じ粒度では足りず、専用のログ分類を持たせるべきです。理由は次の通りです。

api/image/rembg/* は Django 上で重い CPU 処理を実行しており、通常の DB API より App Runner のリソース圧迫を起こしやすい

DB 処理と同一 App Runner サービスに同居しているため、rembg の遅延や失敗が他 API のレイテンシ悪化や 5xx を誘発しうる

現状の process_event() は失敗時に標準出力へ文字列を出すだけで、CloudWatch Logs Insights で分析しづらい

画像サイズ、入力形式、model_name、処理時間、S3 書き込み失敗など、原因切り分けに必要な情報が多い

したがって api/image/rembg/* は、単なる「Django API の一つ」ではなく、App Runner 内の画像処理ワークロードとして個別監視・個別ログ設計するのが正しいです。

3.2 /healthz と /health の分離

/healthz は App Runner の liveness 用に shallow check のまま維持します。DB や S3 の deep check をここに入れると、一時的な依存断で App Runner 自体が unhealthy 判定され、不要な再起動や不安定化を招きます。deep check は別の /health に分離します。App Runner 側の /healthz 設定はこの方針と整合します。

4. 監視アーキテクチャ
CloudWatch Metrics / Alarm
        ↓
      SNS Topic
        ↓
 Slack Notify Lambda
        ↓
 Slack Incoming Webhook
4.1 採用理由

Slack 通知は AWS Chatbot でも実現可能ですが、今回の要件は Slack webhook 連携であり、通知本文を stage / service / alarm / runbook URL 付きで整形したいです。そのため、SNS → 通知専用 Lambda → Slack Incoming Webhook を採用します。

5. CloudWatch Alarm 設計
5.1 App Runner
監視対象

App Runner 5xxStatusResponses

Threshold: >= 1

Period: 5 minutes

Severity: Critical

App Runner RequestLatency

Warning: Average >= 3000 ms

Critical: Average or p95 >= 5000 ms

Period: 5 minutes

設計意図

App Runner は DB API と rembg API を同居させているため、5xx だけでは遅すぎます。高遅延 alarm を先に拾うことで、「DB はまだ落ちていないが rembg が詰まり始めている」状態を検知できます。現状 MonitoringStack に App Runner 5xx はあるが latency がないため、追加対象です。

5.2 Lambda: lambda-bg / lambda-yolo

Errors: >= 1 / 5m

Duration Warning

lambda-bg >= 15000 ms

lambda-yolo >= 25000 ms

Duration Critical

lambda-bg >= 30000 ms

lambda-yolo >= 45000 ms

Throttles: >= 1 / 5m

設計意図

これらはフロントから直接叩かれるため、UX 直結の高遅延を timeout 手前で拾う必要があります。timeout 値を見ても、警告閾値はもっと手前に置くべきです。

6. Slack 通知設計
6.1 通知方式

Slack Incoming Webhook URL は Secrets Manager に保存

CloudWatch Alarm は SNS Topic に publish

通知専用 Lambda が SNS message を受け、Slack に整形送信

6.2 通知本文に含める項目

stage

service

severity

alarm name

metric name

threshold

alarm state

event time

AWS Console への導線

runbook URL

6.3 完了条件

App Runner 5xx / latency alarm で Slack 通知

Lambda errors / duration / throttles で Slack 通知

ALARM / OK の両方が届く

7. Structured Logging 設計
7.1 基本方針

ログはすべて JSON 1行で stdout に出力し、CloudWatch Logs に集約します。text ベースの print() ログは廃止します。Django / Lambda でキー名を揃え、CloudWatch Logs Insights で横断検索できるようにします。

7.2 共通必須フィールド
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
必須キー

timestamp

level

service

stage

component

event

message

request_id

path

method

status_code

duration_ms

user_id

guest_id

Guest 利用が前提のサービスなので、guest_id は省略不可に近い扱いにします。X-Guest-Id ベースの既存仕様と合わせる必要があります。

8. Django ログ設計（改訂）
8.1 ロガー分類

Django は少なくとも以下にロガーを分けます。

django.access

django.api

django.auth

django.health

django.rembg

このうち、今回の修正ポイントは django.rembg を独立ロガーとして追加すること です。

8.2 なぜ django.rembg を分けるべきか

RembgProcessView は Django View ですが、役割は通常 CRUD API ではなく、画像前処理ワークロードです。実装上も process_event() に処理を丸投げしており、入力画像取得、モデル選択、CPU 推論、S3 書き込みまで一気に実行しています。これは DB API と性質が違います。

同じ django.api に混ぜると、以下が見えなくなります。

rembg 由来の高遅延がどれだけ発生しているか

失敗の内訳が JSON decode / image fetch / model init / inference / S3 put のどこか

image_url 経由入力か base64 経由入力か

特定 model_name だけ遅いか

画像サイズが大きい時だけ失敗しているか

なので、django.rembg を独立させ、event と追加フィールドで細分化します。

8.3 Django 全体のイベント一覧
django.access

request_started

request_finished

request_failed

django.auth

guest_header_missing

guest_authenticated

user_authenticated

django.health

healthz_ok

health_ok

health_degraded

health_dependency_failed

django.rembg

rembg_request_started

rembg_request_succeeded

rembg_request_failed

rembg_input_decode_failed

rembg_image_fetch_failed

rembg_model_init_failed

rembg_inference_failed

rembg_s3_put_failed

rembg_slow_request

9. rembg 専用ログ設計
9.1 結論

api/image/rembg/* は Django のエラーログに必ず含める。ただし、通常 API の request_failed に埋もれさせず、専用 event と追加フィールドを持つエラーログにする。

9.2 rembg ログに追加するフィールド
{
  "component": "django.rembg",
  "event": "rembg_inference_failed",
  "path": "/api/image/rembg/isnet-general-use/",
  "model_name": "isnet-general-use",
  "input_source": "image_url",
  "source_image_size_bytes": 7340032,
  "image_width": null,
  "image_height": null,
  "s3_bucket": "mini-museum-staging-assets",
  "s3_key": "removed_bg/xxxx.png",
  "alpha_matting": false,
  "duration_ms": 18234,
  "error_type": "RuntimeError",
  "error_code": "REMBG_INFERENCE_FAILED"
}
追加推奨キー

model_name

input_source

image_data

image_url

s3

source_image_size_bytes

image_width

image_height

alpha_matting

s3_bucket

s3_key

error_type

error_code

9.3 rembg の失敗分類

現状コードを見る限り、失敗ポイントは主に以下です。

body JSON decode 失敗

image_data base64 decode 失敗

image_url の外部取得失敗

S3 get_object 失敗

new_session() のモデル初期化失敗

remove() の推論失敗

S3 put_object / presigned URL 生成失敗

これらは全部 500 に丸めるのではなく、ログ上では error_code を分けるべきです。

推奨 error_code

REMBG_INVALID_JSON

REMBG_INVALID_IMAGE_DATA

REMBG_IMAGE_FETCH_FAILED

REMBG_S3_GET_FAILED

REMBG_MODEL_INIT_FAILED

REMBG_INFERENCE_FAILED

REMBG_S3_PUT_FAILED

9.4 成功ログも必要

rembg は「失敗だけ見ればよい」では足りません。成功でも重い処理は App Runner 全体に悪影響を及ぼします。よって以下を残します。

すべての失敗ログは ERROR

成功時は INFO

しきい値超え成功は WARNING

WARNING 例

duration_ms >= 5000 で rembg_slow_request

これにより「成功したが遅すぎる」ケースを拾う

9.5 rembg の代表ログ例
開始ログ
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
遅延 Warning
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
失敗 Error
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
10. request_id 設計
10.1 基本方針

X-Request-Id があれば採用

なければ Django middleware で生成

すべてのレスポンスに X-Request-Id を返す

すべてのログに request_id を入れる

10.2 rembg でも必須

RembgProcessView は View 内で event を組み立てて process_event() に渡しているため、ここで request_id を event に埋め込めるようにします。現状の event には request_id が入っていません。ここは修正対象です。

11. Health Check 設計
11.1 GET /healthz

用途:

App Runner liveness check 専用

仕様:

プロセスが起動していれば 200

DB / S3 には接続しない

App Runner health check path に使用

11.2 GET /health

用途:

運用確認 / 外形監視 / 手動確認

仕様:

DB 接続確認

S3 接続確認

status=ok/degraded

依存失敗時は 503

レスポンス例
{
  "status": "ok",
  "checks": {
    "db": "ok",
    "s3": "ok"
  },
  "service": "mini-museum-api",
  "stage": "staging"
}
12. 実装方針
12.1 Django logging 実装

ライブラリは structlog か python-json-logger のどちらでもよいですが、request 単位で文脈を bind しやすいので structlog 推奨です。

出力方針

stdout JSON 1行

print() 廃止

traceback は exception フィールドに格納

guest_id, request_id, path, component, event を統一キーにする

12.2 rembg 実装修正方針

rembg_processor.py は現状、print() と traceback.print_exc() しかなく、構造化ログとして弱いです。さらに new_session() を毎回生成しているため、遅延の主要因になりえます。

最低限、以下をログ対象にします。

リクエスト開始

body parse 完了

入力取得成功 / 失敗

model_name 決定

session 初期化開始 / 成功 / 失敗

remove() 開始 / 成功 / 失敗

S3 書き込み成功 / 失敗

総処理時間

実装時の注意

new_session() を毎回呼ぶ現在構成は、遅延とエラーの温床です。設計書としては以下を明記します。

短期: まずは構造化ログを入れて実態を可視化する

中期: model session の再利用を検討する

長期: rembg を Django/App Runner から分離し、別ワーカーや Lambda へ逃がすことを検討する

ここは設計上かなり重要です。今の構成は DB API と CPU ヘビー処理を同居させており、App Runner 全体の安定性を落としやすいです。

13. CloudWatch Logs Insights 想定クエリ
13.1 rembg の失敗だけ追う
fields @timestamp, level, event, request_id, path, model_name, input_source, duration_ms, error_code, error_type, guest_id
| filter component = "django.rembg"
| filter level = "ERROR"
| sort @timestamp desc
| limit 50
13.2 rembg の高遅延を追う
fields @timestamp, event, request_id, model_name, input_source, duration_ms, guest_id
| filter component = "django.rembg"
| filter event = "rembg_slow_request"
| sort duration_ms desc
| limit 50
13.3 request_id 単位で追う
fields @timestamp, component, event, message, request_id, status_code, duration_ms
| filter request_id = "req_123"
| sort @timestamp asc
14. 優先順位
Phase 1

Slack 通知経路の実装

App Runner latency alarm 追加

Django request_id middleware

Django structured logging 導入

django.rembg 専用ロガー追加

Phase 2

views_rembg.py で request context をログに bind

rembg_processor.py の print() 廃止

rembg の event / error_code の細分化

/health deep check 実装

Phase 3

rembg session 再利用の検討

rembg の App Runner 分離検討

Logs Insights / Dashboard 整備

15. 完了条件
監視

App Runner 5xx で Slack 通知

App Runner 高遅延で Slack 通知

Lambda errors / duration / throttles で Slack 通知

ログ

Django ログが JSON structured logging になっている

request_id, user_id, guest_id が入る

api/image/rembg/* が django.rembg として独立追跡できる

rembg の失敗が error_code で分類できる

成功でも高遅延なら Warning が出る

ヘルスチェック

/healthz は shallow

/health は DB / S3 deep check

deep check failure は 503

16. 最終結論

今回の修正で一番重要なのは次の2点です。

api/image/rembg/* は Django のエラーログ対象に必ず入れる
しかも通常 API と同列ではなく、django.rembg の専用ロガーで扱う。今の構成では rembg が App Runner 全体の不安定化要因になりうるため、ここを観測できないと運用にならない。

rembg は失敗だけでなく高遅延もログに残す
重い処理が DB API と同居している以上、「成功したが遅い」は実質障害予兆です。ERROR だけでなく WARNING の rembg_slow_request を入れるべきです。

この設計に直せば、「エラーが起きたら Slack に飛ぶ」だけでなく、「CloudWatch 上で rembg が App Runner を圧迫している兆候」まで追えるようになります。