Mini Museum 監視・通知・構造化ログ・ヘルスチェック設計書
1. 目的

本設計の目的は、Mini Museum の本番運用に必要な最低限の運用監視基盤を整備し、以下を達成すること。

App Runner / Lambda の障害を CloudWatch Alarm で検知する

障害通知を Slack に即時送信する

Django / Lambda のログを structured logging で統一し、CloudWatch Logs 上で原因追跡できるようにする

ヘルスチェック API を整理し、デプロイ時の liveness と運用時の readiness を分離する

画像処理系 Lambda の遅延・失敗を可視化し、UX 影響を早期検知する

2. 現状整理
2.1 インフラ現状

App Runner は CDK の AppRunnerStack でデプロイされ、HTTP health check は /healthz を利用している。

監視スタック MonitoringStack は SNS Topic を持ち、Lambda の Errors / Duration、App Runner の 5xxStatusResponses に Alarm を設定している。通知先は alarmEmail のみ。

lambda-bg と lambda-yolo は DockerImageFunction として構築され、Function URL で直接公開されている。処理遅延がそのままフロントUXに影響する。

2.2 アプリ現状

Guest 識別は X-Guest-Id ヘッダで行う設計で、フロントの http.ts が自動付与する。

/healthz の 200 response を返す View はすでに存在するが、DB / S3 / 外部依存の deep health check は未実装。

ログはまだ JSON structured logging に統一されていない。

3. 設計方針
3.1 基本方針

監視は次の3層で設計する。

メトリクス監視
CloudWatch Metrics / Alarm により、5xx、Lambda error、duration、latency を監視する

ログ監視
構造化 JSON ログにより、障害発生時の原因調査を CloudWatch Logs Insights で行えるようにする

ヘルスチェック監視
App Runner の liveness と、DB/S3 を含む readiness を分離する

3.2 重要判断

/healthz に DB や S3 の deep check を載せない。
理由は、App Runner の container health check は「プロセスが生きているか」を見るべきであり、依存サービスの一時的揺れでコンテナ再起動を引き起こすと逆効果だから。

そのため以下の2段構成にする。

/healthz: shallow health check。App Runner 用

/health: deep health check。監視・運用確認用

これは今の AppRunnerStack の /healthz 設定とも整合する。

4. 監視アーキテクチャ
4.1 全体構成
CloudWatch Metrics / Alarm
        ↓
      SNS Topic
        ↓
 Slack Notify Lambda
        ↓
 Slack Incoming Webhook
採用理由

Slack 通知は AWS Chatbot でもできるが、今回の要件は「Slack Webhook 連携」であり、通知本文を自由に整形したい。
そのため、SNS → 通知専用 Lambda → Slack Incoming Webhook を採用する。

これで以下ができる。

Alarm 名、メトリクス名、閾値、発生時刻を見やすく整形

stage, service, runbook URL を埋め込める

重大度ごとに通知先チャンネルを分けやすい

監視設計を CDK に閉じ込められる

5. CloudWatch Alarm 設計
5.1 App Runner

既存の 5xxStatusResponses はそのまま残す。加えて latency 系を追加する。現状 MonitoringStack には App Runner 5xx しかない。

監視対象
A. AppRunner 5xx

Metric: AWS/AppRunner / 5xxStatusResponses

Threshold: >= 1

Period: 5 minutes

EvaluationPeriods: 1

Severity: Critical

B. AppRunner latency

Metric: AWS/AppRunner / RequestLatency

Statistic: Average

Threshold: >= 3000 ms

Period: 5 minutes

EvaluationPeriods: 2

Severity: Warning

C. AppRunner high latency critical

Metric: AWS/AppRunner / RequestLatency

Statistic: p95 or Average（CDK側で扱いやすい方）

Threshold: >= 5000 ms

Period: 5 minutes

EvaluationPeriods: 2

Severity: Critical

D. AppRunner 4xx

必須ではないが推奨

認証バグやフロントとの契約ズレ検知用

初期は dashboard only でよい

5.2 Lambda: lambda-bg / lambda-yolo

この2つはフロントから直接叩かれるため、duration と error の両方を厳しめに見る。現状でも Errors と Duration alarm は入っている。

共通 Alarm
A. Lambda Errors

Metric: AWS/Lambda / Errors

Threshold: >= 1

Period: 5 minutes

EvaluationPeriods: 1

Severity: Critical

B. Lambda Duration Warning

lambda-bg: average duration >= 15000 ms

lambda-yolo: average duration >= 25000 ms

Period: 5 minutes

EvaluationPeriods: 2

Severity: Warning

C. Lambda Duration Critical

lambda-bg: average duration >= 30000 ms

lambda-yolo: average duration >= 45000 ms

Period: 5 minutes

EvaluationPeriods: 1

Severity: Critical

D. Lambda Throttles

Metric: AWS/Lambda / Throttles

Threshold: >= 1

Period: 5 minutes

Severity: Critical

E. Lambda ConcurrentExecutions

dashboard 監視

後で急増時 alarm を追加

閾値の理由

lambda-bg は timeout 60 秒、lambda-yolo は 90 秒なので、timeout に張り付く前の劣化を検知したい。いきなり 50〜80 秒閾値だと遅すぎる。UX 悪化を拾うため、warning は timeout の半分以下に寄せる。

6. Slack 通知設計
6.1 通知方式

Slack Incoming Webhook URL は Secrets Manager に保存

SNS Topic から通知専用 Lambda を subscribe

Lambda が SNS message を解釈して Slack に POST

6.2 通知メッセージ例
{
  "text": "🚨 [staging] AppRunner 5xx alarm",
  "blocks": [
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*Mini Museum Alert*\n*Severity:* Critical\n*Alarm:* AppRunner5xxAlarm\n*Stage:* staging\n*Service:* mini-museum-api-staging"
      }
    },
    {
      "type": "section",
      "fields": [
        { "type": "mrkdwn", "text": "*Metric:*\nAWS/AppRunner 5xxStatusResponses" },
        { "type": "mrkdwn", "text": "*Threshold:*\n>= 1 / 5m" },
        { "type": "mrkdwn", "text": "*Time:*\n2026-03-20T08:10:00+09:00" }
      ]
    }
  ]
}
6.3 通知先

#mini-museum-alerts: 本番・ステージング共通

将来的に

#mini-museum-prod-alerts

#mini-museum-dev-alerts
に分離可能

6.4 完了条件

CloudWatch Alarm 発火時に Slack 通知が届く

通知本文に stage / resource / metric / threshold / console link が含まれる

OK -> ALARM / ALARM -> OK の両方を通知できる

7. 構造化ログ設計
7.1 ログの目的

エラー調査を CloudWatch Logs Insights で実施できること

App Runner と Lambda でフォーマットを統一すること

guest/user 混在運用でも追跡可能であること

request 単位でログを束ねられること

7.2 必須フィールド

全ログにできるだけ共通で持たせる。

{
  "timestamp": "2026-03-20T08:15:12.123+09:00",
  "level": "ERROR",
  "service": "mini-museum-api",
  "stage": "staging",
  "component": "django.api",
  "event": "image_process_failed",
  "message": "failed to process image",
  "request_id": "req_01HXXX",
  "trace_id": null,
  "path": "/api/galleries/123/exhibits/4/",
  "method": "PUT",
  "status_code": 500,
  "user_id": null,
  "guest_id": "guest_abc123",
  "gallery_id": "123",
  "exhibit_id": null,
  "slot_index": 4,
  "lambda_function": null,
  "duration_ms": 1823,
  "error_type": "ValueError",
  "error_code": "IMAGE_PROCESS_FAILED",
  "exception": "stacktrace or shortened traceback"
}
7.3 Django のログフィールド
共通

timestamp

level

service

stage

component="django"

event

message

request_id

path

method

status_code

duration_ms

認証・主体

user_id

guest_id

is_authenticated

ドメイン

gallery_id

exhibit_id

slot_index

エラー時

error_type

error_code

exception

7.4 Lambda のログフィールド

画像処理系ではこちらを追加する。

{
  "timestamp": "2026-03-20T08:16:45.001+09:00",
  "level": "ERROR",
  "service": "mini-museum-image",
  "stage": "staging",
  "component": "lambda-yolo",
  "event": "yolo_inference_failed",
  "message": "yolo segmentation failed",
  "request_id": "req_01HYYY",
  "aws_request_id": "5f7c...",
  "function_name": "mini-museum-staging-yoloprocessor",
  "path": "/",
  "method": "POST",
  "status_code": 500,
  "user_id": null,
  "guest_id": "guest_abc123",
  "source_image_size_bytes": 7340032,
  "image_width": 3024,
  "image_height": 4032,
  "memory_limit_mb": 3008,
  "duration_ms": 28432,
  "model_name": "yolo-seg",
  "s3_bucket": "xxx",
  "error_type": "RuntimeError",
  "error_code": "YOLO_INFERENCE_FAILED",
  "exception": "..."
}
Lambda で特に重要な追加項目

aws_request_id

function_name

source_image_size_bytes

image_width

image_height

memory_limit_mb

duration_ms

model_name

output_count

s3_key

ここは UX 影響の中心なので、画像サイズと実行時間の相関が見えるようにする。

7.5 ログレベル運用

DEBUG: ローカルのみ

INFO: request 完了、主要イベント

WARNING: リトライ、外部依存の一時失敗、遅延

ERROR: リクエスト失敗、例外

CRITICAL: サービス継続困難、依存断

8. request_id 設計
8.1 方針

request_id は必須。
Django と Lambda で共通キー名を request_id に固定する。

8.2 Django

middleware で X-Request-Id を受け取り、なければサーバー側で生成

request.request_id に保存

response header に X-Request-Id を付与

すべてのログに埋め込む

8.3 Lambda

Function URL で叩かれるため、以下順で採用する。

header X-Request-Id があればそれを使用

なければアプリ側で生成

aws_request_id は別フィールドで保持

8.4 フロント

将来的には shared/api/http.ts で X-Request-Id を付与してもいいが、初期は backend / lambda 側生成でも十分。
ただし Guest 設計上 X-Guest-Id は必須で漏れないようにする前提。

9. Django ログ設計
9.1 出力形式

stdout に JSON 1行

CloudWatch Logs 取り込み前提

text log は禁止

9.2 実装方針

python-json-logger か structlog を採用

個人的には structlog 推奨

context bind がしやすい

request_id / guest_id / user_id を processor で付けやすい

9.3 推奨イベント一覧

request_started

request_finished

request_failed

auth_guest_missing

auth_user_authenticated

gallery_created

gallery_deleted_soft

exhibit_upserted

exhibit_deleted_soft

image_upload_started

image_upload_failed

external_s3_check_failed

9.4 アクセスログ例
{
  "timestamp": "2026-03-20T08:20:00.000+09:00",
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
9.5 エラーログ例
{
  "timestamp": "2026-03-20T08:21:00.000+09:00",
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
  "user_id": null,
  "guest_id": "guest_123",
  "gallery_id": "123",
  "slot_index": 4,
  "error_type": "ValidationError",
  "error_code": "EXHIBIT_UPSERT_FAILED"
}
10. Lambda ログ設計
10.1 方針

Lambda はフロントから直接叩かれるため、「失敗した」だけでは弱い。
最低限、入力サイズ・処理時間・出力結果・失敗理由 が必要。

10.2 イベント一覧
lambda-bg

background_remove_started

background_remove_succeeded

background_remove_failed

lambda-yolo

yolo_inference_started

yolo_inference_succeeded

yolo_inference_failed

10.3 成功ログ例
{
  "timestamp": "2026-03-20T08:22:00.000+09:00",
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
11. ヘルスチェック設計
11.1 エンドポイント設計
A. GET /healthz

用途:

App Runner container health check 専用

shallow check

仕様:

アプリプロセスが起動していれば 200

DB / S3 には接続しない

body は最小限

レスポンス例:

{
  "status": "ok",
  "service": "mini-museum-api",
  "stage": "staging"
}
B. GET /health

用途:

CloudWatch Synthetics / 手動確認 / 外形監視

deep check

チェック内容:

DB connection

S3 access

app version / stage

optional: migration state

レスポンス例:

{
  "status": "ok",
  "checks": {
    "db": "ok",
    "s3": "ok"
  },
  "service": "mini-museum-api",
  "stage": "staging"
}

異常時:

依存のどれかが落ちていれば 503

どの check が失敗したかを body に含める

{
  "status": "degraded",
  "checks": {
    "db": "ok",
    "s3": "error"
  }
}
11.2 DB チェック

SELECT 1

timeout を短くする

ORM で重いクエリは禁止

11.3 S3 チェック

head_bucket か、軽い list_objects_v2(MaxKeys=1) 相当

書き込みチェックはしない

deep health でのみ実施

11.4 なぜ /healthz と /health を分けるか

いま App Runner は /healthz を health check path にしている。これを deep health に変えると、S3 や DB の瞬断でコンテナが unhealthy 判定される。運用上かなり悪い。だから shallow/deep は分離が正解。

12. CloudWatch Logs Insights 前提のクエリ設計
12.1 Django エラー調査
fields @timestamp, level, event, message, request_id, path, method, status_code, guest_id, user_id, error_type
| filter level = "ERROR"
| sort @timestamp desc
| limit 50
12.2 特定 request_id の追跡
fields @timestamp, component, event, message, request_id, path, status_code
| filter request_id = "req_123"
| sort @timestamp asc
12.3 Lambda 遅延分析
fields @timestamp, component, event, duration_ms, source_image_size_bytes, image_width, image_height, request_id
| filter component in ["lambda-bg", "lambda-yolo"]
| filter event like /succeeded|failed/
| sort duration_ms desc
| limit 50
13. CDK 実装方針
13.1 MonitoringStack の拡張

現状 MonitoringStack は email subscription しか持たないので、以下を追加する。

追加項目

slackWebhookSecretArn

notificationLambda

topic.addSubscription(new LambdaSubscription(notificationLambda))

App Runner latency alarm

Lambda throttles alarm

必要なら composite alarm

13.2 新規スタック候補

MonitoringStack にまとめてもいいが、責務が重くなりすぎるなら以下でもよい。

MonitoringStack: alarms / topic

AlertingStack: slack notify lambda / secret / subscription

ただ、今は規模的に MonitoringStack に閉じて問題ない。

14. 実装優先順位
Phase 1: 最優先

SNS -> Slack notify Lambda

App Runner 5xx / latency alarm

Lambda error / duration / throttle alarm 整備

通知テスト

Phase 2

Django structured logging

request_id middleware

Lambda structured logging 共通 helper

Phase 3

/health deep health 実装

外形監視導入

Logs Insights クエリ / dashboard 整備

15. 完了条件
監視

App Runner 5xx 発生で Slack 通知

App Runner 高遅延で Slack 通知

lambda-bg / lambda-yolo の error で Slack 通知

lambda-bg / lambda-yolo の高遅延で Slack 通知

ログ

Django の request / error ログが JSON で出る

request_id, user_id, guest_id が含まれる

Lambda の画像処理ログに画像サイズ・duration・error_type が含まれる

CloudWatch Logs Insights で request_id 単位の追跡ができる

ヘルスチェック

/healthz は App Runner 用 shallow check

/health は DB / S3 deep check

deep health 失敗時は 503

16. この設計での重要ポイント

一番大事なのはこれ。

/healthz を deep check にしないこと。
今の App Runner health check 設定は正しい。そこを壊さず、運用用に /health を足す。

次に大事なのはこれ。

ログの主キーは request_id で、主体識別は user_id と guest_id の両方を持つこと。
このサービスは Guest 流入が強い設計なので、user_id だけのログ設計だと半分以上の障害が追えなくなる。X-Guest-Id 前提の既存仕様と必ず揃える。