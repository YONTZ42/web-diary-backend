import { Duration, Stack, StackProps } from "aws-cdk-lib";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as logs from "aws-cdk-lib/aws-logs";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";
import * as sns from "aws-cdk-lib/aws-sns";
import * as subs from "aws-cdk-lib/aws-sns-subscriptions";
import { Construct } from "constructs";

export interface AlertingStackProps extends StackProps {
  projectName: string;
  stage: string;
  alarmTopic: sns.ITopic;
  slackWebhookSecretArn: string;
  runbookBaseUrl?: string;
}

export class AlertingStack extends Stack {
  public readonly notifierFunction: lambda.Function;

  constructor(scope: Construct, id: string, props: AlertingStackProps) {
    super(scope, id, props);

    const slackWebhookSecret = secretsmanager.Secret.fromSecretCompleteArn(
      this,
      "SlackWebhookSecret",
      props.slackWebhookSecretArn
    );

    this.notifierFunction = new lambda.Function(this, "SlackNotifierFunction", {
      functionName: `${props.projectName}-${props.stage}-slack-notifier`.toLowerCase(),
      runtime: lambda.Runtime.NODEJS_20_X,
      handler: "index.handler",
      timeout: Duration.seconds(15),
      memorySize: 256,
      logRetention: logs.RetentionDays.ONE_MONTH,
      environment: {
        STAGE: props.stage,
        PROJECT_NAME: props.projectName,
        SLACK_WEBHOOK_SECRET_ARN: props.slackWebhookSecretArn,
        RUNBOOK_BASE_URL: props.runbookBaseUrl ?? "",
      },
      code: lambda.Code.fromInline(`
const { SecretsManagerClient, GetSecretValueCommand } = require("@aws-sdk/client-secrets-manager");

const sm = new SecretsManagerClient({});

async function getWebhookUrl(secretArn) {
  const out = await sm.send(new GetSecretValueCommand({ SecretId: secretArn }));
  const raw = out.SecretString || "";
  try {
    const parsed = JSON.parse(raw);
    return parsed.webhookUrl || parsed.url || raw;
  } catch {
    return raw;
  }
}

function buildConsoleAlarmLink(region, alarmName) {
  const encoded = encodeURIComponent(alarmName);
  return \`https://\${region}.console.aws.amazon.com/cloudwatch/home?region=\${region}#alarmsV2:alarm/\${encoded}\`;
}

function buildRunbookUrl(baseUrl, alarmName) {
  if (!baseUrl) return null;
  const safeBase = baseUrl.endsWith("/") ? baseUrl.slice(0, -1) : baseUrl;
  return \`\${safeBase}/\${encodeURIComponent(alarmName)}\`;
}

exports.handler = async (event) => {
  const secretArn = process.env.SLACK_WEBHOOK_SECRET_ARN;
  const stage = process.env.STAGE || "unknown";
  const projectName = process.env.PROJECT_NAME || "unknown";
  const runbookBaseUrl = process.env.RUNBOOK_BASE_URL || "";

  const webhookUrl = await getWebhookUrl(secretArn);

  for (const record of event.Records || []) {
    const sns = record.Sns || {};
    const rawMessage = sns.Message || "{}";

    let msg;
    try {
      msg = JSON.parse(rawMessage);
    } catch {
      msg = { AlarmName: "UnknownAlarm", NewStateValue: "UNKNOWN", NewStateReason: rawMessage };
    }

    const alarmName = msg.AlarmName || "UnknownAlarm";
    const newState = msg.NewStateValue || "UNKNOWN";
    const reason = msg.NewStateReason || "";
    const region = msg.Region || process.env.AWS_REGION || "ap-northeast-1";
    const alarmArn = msg.AlarmArn || "";
    const stateChangeTime = msg.StateChangeTime || "";
    const trigger = msg.Trigger || {};

    const metricName = trigger.MetricName || "unknown";
    const namespace = trigger.Namespace || "unknown";
    const threshold = trigger.Threshold ?? "unknown";
    const comparison = trigger.ComparisonOperator || "unknown";

    const emoji = newState === "ALARM" ? "🚨" : newState === "OK" ? "✅" : "ℹ️";
    const consoleUrl = buildConsoleAlarmLink(region, alarmName);
    const runbookUrl = buildRunbookUrl(runbookBaseUrl, alarmName);

    const payload = {
      text: \`\${emoji} [\${stage}] \${alarmName} -> \${newState}\`,
      blocks: [
        {
          type: "section",
          text: {
            type: "mrkdwn",
            text:
              \`*\${projectName} Alert*\\n\` +
              \`*Stage:* \${stage}\\n\` +
              \`*Alarm:* \${alarmName}\\n\` +
              \`*State:* \${newState}\`
          }
        },
        {
          type: "section",
          fields: [
            { type: "mrkdwn", text: \`*Metric:*\\n\${namespace} / \${metricName}\` },
            { type: "mrkdwn", text: \`*Threshold:*\\n\${comparison} \${threshold}\` },
            { type: "mrkdwn", text: \`*Time:*\\n\${stateChangeTime || "-"}\` },
            { type: "mrkdwn", text: \`*Region:*\\n\${region}\` }
          ]
        },
        {
          type: "section",
          text: {
            type: "mrkdwn",
            text: \`*Reason:*\\n\${reason || "-"}\`
          }
        },
        {
          type: "section",
          text: {
            type: "mrkdwn",
            text:
              \`*Console:* <\${consoleUrl}|Open alarm in CloudWatch>\\n\` +
              (runbookUrl ? \`*Runbook:* <\${runbookUrl}|Open runbook>\\n\` : "") +
              (alarmArn ? \`*AlarmArn:* \\\`\${alarmArn}\\\`\` : "")
          }
        }
      ]
    };

    const res = await fetch(webhookUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const text = await res.text();
      throw new Error(\`Slack webhook failed: \${res.status} \${text}\`);
    }
  }
};
      `),
    });

    slackWebhookSecret.grantRead(this.notifierFunction);

    this.notifierFunction.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ["secretsmanager:GetSecretValue"],
        resources: [props.slackWebhookSecretArn],
      })
    );

    props.alarmTopic.addSubscription(new subs.LambdaSubscription(this.notifierFunction));
  }
}