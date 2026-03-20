import { Duration, Stack, StackProps } from "aws-cdk-lib";
import * as apprunner from "aws-cdk-lib/aws-apprunner";
import * as cloudwatch from "aws-cdk-lib/aws-cloudwatch";
import * as cwActions from "aws-cdk-lib/aws-cloudwatch-actions";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as sns from "aws-cdk-lib/aws-sns";
import * as subs from "aws-cdk-lib/aws-sns-subscriptions";
import { Construct } from "constructs";

export interface MonitoredLambdaConfig {
  fn: lambda.IFunction;
  durationWarningMs: number;
  durationCriticalMs: number;
  errorThreshold?: number;
  throttleThreshold?: number;
}

export interface MonitoringStackProps extends StackProps {
  projectName: string;
  stage: string;
  alarmEmail?: string;
  appRunnerService?: apprunner.CfnService;
  lambdaConfigs: MonitoredLambdaConfig[];
}

export class MonitoringStack extends Stack {
  public readonly alarmTopic: sns.Topic;

  constructor(scope: Construct, id: string, props: MonitoringStackProps) {
    super(scope, id, props);

    this.alarmTopic = new sns.Topic(this, "AlarmTopic", {
      topicName: `${props.projectName}-${props.stage}-alarm-topic`,
      displayName: `${props.projectName} ${props.stage} Alarm Topic`,
    });

    if (props.alarmEmail) {
      this.alarmTopic.addSubscription(new subs.EmailSubscription(props.alarmEmail));
    }

    const alarmAction = new cwActions.SnsAction(this.alarmTopic);

    for (const cfg of props.lambdaConfigs) {
      const fn = cfg.fn;
      const errorThreshold = cfg.errorThreshold ?? 1;
      const throttleThreshold = cfg.throttleThreshold ?? 1;

      const errorAlarm = new cloudwatch.Alarm(this, `${fn.node.id}ErrorsAlarm`, {
        alarmName: `${props.projectName}-${props.stage}-${fn.functionName}-errors`,
        metric: fn.metricErrors({
          period: Duration.minutes(5),
          statistic: "sum",
        }),
        threshold: errorThreshold,
        evaluationPeriods: 1,
        datapointsToAlarm: 1,
        alarmDescription: `${fn.functionName} Lambda errors >= ${errorThreshold} in 5 minutes`,
        treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
      });
      errorAlarm.addAlarmAction(alarmAction);
      errorAlarm.addOkAction(alarmAction);

      const durationWarningAlarm = new cloudwatch.Alarm(this, `${fn.node.id}DurationWarningAlarm`, {
        alarmName: `${props.projectName}-${props.stage}-${fn.functionName}-duration-warning`,
        metric: fn.metricDuration({
          period: Duration.minutes(5),
          statistic: "avg",
        }),
        threshold: cfg.durationWarningMs,
        evaluationPeriods: 2,
        datapointsToAlarm: 2,
        alarmDescription: `${fn.functionName} avg duration >= ${cfg.durationWarningMs} ms`,
        treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
      });
      durationWarningAlarm.addAlarmAction(alarmAction);
      durationWarningAlarm.addOkAction(alarmAction);

      const durationCriticalAlarm = new cloudwatch.Alarm(this, `${fn.node.id}DurationCriticalAlarm`, {
        alarmName: `${props.projectName}-${props.stage}-${fn.functionName}-duration-critical`,
        metric: fn.metricDuration({
          period: Duration.minutes(5),
          statistic: "avg",
        }),
        threshold: cfg.durationCriticalMs,
        evaluationPeriods: 1,
        datapointsToAlarm: 1,
        alarmDescription: `${fn.functionName} avg duration >= ${cfg.durationCriticalMs} ms`,
        treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
      });
      durationCriticalAlarm.addAlarmAction(alarmAction);
      durationCriticalAlarm.addOkAction(alarmAction);

      const throttleAlarm = new cloudwatch.Alarm(this, `${fn.node.id}ThrottlesAlarm`, {
        alarmName: `${props.projectName}-${props.stage}-${fn.functionName}-throttles`,
        metric: fn.metricThrottles({
          period: Duration.minutes(5),
          statistic: "sum",
        }),
        threshold: throttleThreshold,
        evaluationPeriods: 1,
        datapointsToAlarm: 1,
        alarmDescription: `${fn.functionName} throttles >= ${throttleThreshold} in 5 minutes`,
        treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
      });
      throttleAlarm.addAlarmAction(alarmAction);
      throttleAlarm.addOkAction(alarmAction);
    }

    if (props.appRunnerService) {
      const serviceArn = props.appRunnerService.attrServiceArn;
      const serviceName = serviceArn.split("/").pop() ?? serviceArn;

      const appRunner5xxAlarm = new cloudwatch.Alarm(this, "AppRunner5xxAlarm", {
        alarmName: `${props.projectName}-${props.stage}-apprunner-5xx`,
        metric: new cloudwatch.Metric({
          namespace: "AWS/AppRunner",
          metricName: "5xxStatusResponses",
          dimensionsMap: {
            ServiceName: serviceName,
          },
          period: Duration.minutes(5),
          statistic: "sum",
        }),
        threshold: 1,
        evaluationPeriods: 1,
        datapointsToAlarm: 1,
        alarmDescription: `${serviceName} App Runner 5xx >= 1 in 5 minutes`,
        treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
      });
      appRunner5xxAlarm.addAlarmAction(alarmAction);
      appRunner5xxAlarm.addOkAction(alarmAction);

      const appRunnerLatencyWarning = new cloudwatch.Alarm(this, "AppRunnerLatencyWarningAlarm", {
        alarmName: `${props.projectName}-${props.stage}-apprunner-latency-warning`,
        metric: new cloudwatch.Metric({
          namespace: "AWS/AppRunner",
          metricName: "RequestLatency",
          dimensionsMap: {
            ServiceName: serviceName,
          },
          period: Duration.minutes(5),
          statistic: "avg",
        }),
        threshold: 3000,
        evaluationPeriods: 2,
        datapointsToAlarm: 2,
        alarmDescription: `${serviceName} App Runner avg latency >= 3000 ms`,
        treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
      });
      appRunnerLatencyWarning.addAlarmAction(alarmAction);
      appRunnerLatencyWarning.addOkAction(alarmAction);

      const appRunnerLatencyCritical = new cloudwatch.Alarm(this, "AppRunnerLatencyCriticalAlarm", {
        alarmName: `${props.projectName}-${props.stage}-apprunner-latency-critical`,
        metric: new cloudwatch.Metric({
          namespace: "AWS/AppRunner",
          metricName: "RequestLatency",
          dimensionsMap: {
            ServiceName: serviceName,
          },
          period: Duration.minutes(5),
          statistic: "avg",
        }),
        threshold: 5000,
        evaluationPeriods: 2,
        datapointsToAlarm: 2,
        alarmDescription: `${serviceName} App Runner avg latency >= 5000 ms`,
        treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
      });
      appRunnerLatencyCritical.addAlarmAction(alarmAction);
      appRunnerLatencyCritical.addOkAction(alarmAction);
    }
  }
}