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
  public readonly dashboard: cloudwatch.Dashboard;

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
    const allAlarms: cloudwatch.IAlarm[] = [];
    const lambdaAlarms: cloudwatch.IAlarm[] = [];
    const appRunnerAlarms: cloudwatch.IAlarm[] = [];

    this.dashboard = new cloudwatch.Dashboard(this, "ObservabilityDashboard", {
      dashboardName: `${props.projectName}-${props.stage}-observability`,
      defaultInterval: Duration.hours(6),
    });

    // ----------------------------
    // Header
    // ----------------------------
    this.dashboard.addWidgets(
      new cloudwatch.TextWidget({
        width: 24,
        height: 2,
        markdown: `# ${props.projectName} / ${props.stage} Observability Dashboard

最小構成:
- App Runner: CPU / Memory / Latency / 4xx / 5xx / Concurrency / ActiveInstances
- Lambda: Duration / Errors / Throttles / ConcurrentExecutions
- Alarm status
`,
      })
    );

    // ----------------------------
    // Lambda alarms + widgets
    // ----------------------------
    const lambdaDurationMetrics: cloudwatch.IMetric[] = [];
    const lambdaErrorMetrics: cloudwatch.IMetric[] = [];
    const lambdaThrottleMetrics: cloudwatch.IMetric[] = [];
    const lambdaConcurrencyMetrics: cloudwatch.IMetric[] = [];

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
      allAlarms.push(errorAlarm);
      lambdaAlarms.push(errorAlarm);

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
      allAlarms.push(durationWarningAlarm);
      lambdaAlarms.push(durationWarningAlarm);

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
      allAlarms.push(durationCriticalAlarm);
      lambdaAlarms.push(durationCriticalAlarm);

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
      allAlarms.push(throttleAlarm);
      lambdaAlarms.push(throttleAlarm);

      lambdaDurationMetrics.push(
        fn.metricDuration({
          period: Duration.minutes(5),
          statistic: "avg",
          label: `${fn.functionName} avg`,
        }),
        fn.metricDuration({
          period: Duration.minutes(5),
          statistic: "p95",
          label: `${fn.functionName} p95`,
        })
      );

      lambdaErrorMetrics.push(
        fn.metricErrors({
          period: Duration.minutes(5),
          statistic: "sum",
          label: `${fn.functionName} errors`,
        })
      );

      lambdaThrottleMetrics.push(
        fn.metricThrottles({
          period: Duration.minutes(5),
          statistic: "sum",
          label: `${fn.functionName} throttles`,
        })
      );

      lambdaConcurrencyMetrics.push(
        fn.metric("ConcurrentExecutions", {
          period: Duration.minutes(5),
          statistic: "max",
          label: `${fn.functionName} concurrency max`,
        })
      );
    }
    const lambdaWidgets: cloudwatch.IWidget[] = [
      new cloudwatch.TextWidget({
        width: 24,
        height: 1,
        markdown: "## Lambda",
      }),
      new cloudwatch.GraphWidget({
        title: "Lambda Duration (avg / p95)",
        width: 12,
        height: 6,
        left: lambdaDurationMetrics,
        leftYAxis: {
          label: "ms",
          min: 0,
        },
      }),
      new cloudwatch.GraphWidget({
        title: "Lambda Errors / Throttles",
        width: 12,
        height: 6,
        left: [...lambdaErrorMetrics, ...lambdaThrottleMetrics],
        leftYAxis: {
          label: "count",
          min: 0,
        },
      }),
      new cloudwatch.GraphWidget({
        title: "Lambda Concurrent Executions (max)",
        width: 12,
        height: 6,
        left: lambdaConcurrencyMetrics,
        leftYAxis: {
          label: "count",
          min: 0,
        },
      }),
    ];

    if (lambdaAlarms.length > 0) {
      lambdaWidgets.push(
        new cloudwatch.AlarmStatusWidget({
          title: "Lambda Alarm Status",
          width: 12,
          height: 6,
          alarms: lambdaAlarms,
        })
      );
    }

    this.dashboard.addWidgets(...lambdaWidgets);


    // ----------------------------
    // App Runner alarms + widgets
    // ----------------------------
    if (props.appRunnerService) {
      const serviceArn = props.appRunnerService.attrServiceArn;
      const serviceName = serviceArn.split("/").pop() ?? serviceArn;

      const appRunner5xxMetric = new cloudwatch.Metric({
        namespace: "AWS/AppRunner",
        metricName: "5xxStatusResponses",
        dimensionsMap: { ServiceName: serviceName },
        period: Duration.minutes(5),
        statistic: "sum",
        label: "5xx",
      });

      const appRunner4xxMetric = new cloudwatch.Metric({
        namespace: "AWS/AppRunner",
        metricName: "4xxStatusResponses",
        dimensionsMap: { ServiceName: serviceName },
        period: Duration.minutes(5),
        statistic: "sum",
        label: "4xx",
      });

      const appRunnerRequestsMetric = new cloudwatch.Metric({
        namespace: "AWS/AppRunner",
        metricName: "Requests",
        dimensionsMap: { ServiceName: serviceName },
        period: Duration.minutes(5),
        statistic: "sum",
        label: "requests",
      });

      const appRunnerLatencyAvgMetric = new cloudwatch.Metric({
        namespace: "AWS/AppRunner",
        metricName: "RequestLatency",
        dimensionsMap: { ServiceName: serviceName },
        period: Duration.minutes(5),
        statistic: "avg",
        label: "latency avg",
      });

      const appRunnerLatencyP95Metric = new cloudwatch.Metric({
        namespace: "AWS/AppRunner",
        metricName: "RequestLatency",
        dimensionsMap: { ServiceName: serviceName },
        period: Duration.minutes(5),
        statistic: "p95",
        label: "latency p95",
      });

      const appRunnerCpuMetric = new cloudwatch.Metric({
        namespace: "AWS/AppRunner",
        metricName: "CPUUtilization",
        dimensionsMap: { ServiceName: serviceName },
        period: Duration.minutes(1),
        statistic: "avg",
        label: "cpu %",
      });

      const appRunnerMemoryMetric = new cloudwatch.Metric({
        namespace: "AWS/AppRunner",
        metricName: "MemoryUtilization",
        dimensionsMap: { ServiceName: serviceName },
        period: Duration.minutes(1),
        statistic: "avg",
        label: "memory %",
      });

      const appRunnerConcurrencyMetric = new cloudwatch.Metric({
        namespace: "AWS/AppRunner",
        metricName: "Concurrency",
        dimensionsMap: { ServiceName: serviceName },
        period: Duration.minutes(1),
        statistic: "avg",
        label: "concurrency",
      });

      const appRunnerActiveInstancesMetric = new cloudwatch.Metric({
        namespace: "AWS/AppRunner",
        metricName: "ActiveInstances",
        dimensionsMap: { ServiceName: serviceName },
        period: Duration.minutes(1),
        statistic: "avg",
        label: "active instances",
      });

      const appRunner5xxAlarm = new cloudwatch.Alarm(this, "AppRunner5xxAlarm", {
        alarmName: `${props.projectName}-${props.stage}-apprunner-5xx`,
        metric: appRunner5xxMetric,
        threshold: 1,
        evaluationPeriods: 1,
        datapointsToAlarm: 1,
        alarmDescription: `${serviceName} App Runner 5xx >= 1 in 5 minutes`,
        treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
      });
      appRunner5xxAlarm.addAlarmAction(alarmAction);
      appRunner5xxAlarm.addOkAction(alarmAction);
      allAlarms.push(appRunner5xxAlarm);
      appRunnerAlarms.push(appRunner5xxAlarm);

      const appRunnerLatencyWarning = new cloudwatch.Alarm(this, "AppRunnerLatencyWarningAlarm", {
        alarmName: `${props.projectName}-${props.stage}-apprunner-latency-warning`,
        metric: appRunnerLatencyAvgMetric,
        threshold: 3000,
        evaluationPeriods: 2,
        datapointsToAlarm: 2,
        alarmDescription: `${serviceName} App Runner avg latency >= 3000 ms`,
        treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
      });
      appRunnerLatencyWarning.addAlarmAction(alarmAction);
      appRunnerLatencyWarning.addOkAction(alarmAction);
      allAlarms.push(appRunnerLatencyWarning);
      appRunnerAlarms.push(appRunnerLatencyWarning);

      const appRunnerLatencyCritical = new cloudwatch.Alarm(this, "AppRunnerLatencyCriticalAlarm", {
        alarmName: `${props.projectName}-${props.stage}-apprunner-latency-critical`,
        metric: appRunnerLatencyAvgMetric,
        threshold: 5000,
        evaluationPeriods: 2,
        datapointsToAlarm: 2,
        alarmDescription: `${serviceName} App Runner avg latency >= 5000 ms`,
        treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
      });
      appRunnerLatencyCritical.addAlarmAction(alarmAction);
      appRunnerLatencyCritical.addOkAction(alarmAction);
      allAlarms.push(appRunnerLatencyCritical);
      appRunnerAlarms.push(appRunnerLatencyCritical);

      const appRunnerWidgets: cloudwatch.IWidget[] = [
        new cloudwatch.TextWidget({
          width: 24,
          height: 1,
          markdown: "## App Runner",
        }),
        new cloudwatch.GraphWidget({
          title: "App Runner CPU / Memory Utilization",
          width: 12,
          height: 6,
          left: [appRunnerCpuMetric, appRunnerMemoryMetric],
          leftYAxis: {
            label: "%",
            min: 0,
            max: 100,
          },
        }),
        new cloudwatch.GraphWidget({
          title: "App Runner Request Latency (avg / p95)",
          width: 12,
          height: 6,
          left: [appRunnerLatencyAvgMetric, appRunnerLatencyP95Metric],
          leftYAxis: {
            label: "ms",
            min: 0,
          },
        }),
        new cloudwatch.GraphWidget({
          title: "App Runner Requests / 4xx / 5xx",
          width: 12,
          height: 6,
          left: [appRunnerRequestsMetric, appRunner4xxMetric, appRunner5xxMetric],
          leftYAxis: {
            label: "count",
            min: 0,
          },
        }),
        new cloudwatch.GraphWidget({
          title: "App Runner Concurrency / Active Instances",
          width: 12,
          height: 6,
          left: [appRunnerConcurrencyMetric, appRunnerActiveInstancesMetric],
          leftYAxis: {
            label: "count",
            min: 0,
          },
        }),
      ];

      if (appRunnerAlarms.length > 0) {
        appRunnerWidgets.push(
          new cloudwatch.AlarmStatusWidget({
            title: "App Runner Alarm Status",
            width: 24,
            height: 4,
            alarms: appRunnerAlarms,
          })
        );
      }

      this.dashboard.addWidgets(...appRunnerWidgets);
    }


    if (allAlarms.length > 0) {
      this.dashboard.addWidgets(
        new cloudwatch.TextWidget({
          width: 24,
          height: 1,
          markdown: "## All Alarm Status",
        }),
        new cloudwatch.AlarmStatusWidget({
          title: "All Alarm Status",
          width: 24,
          height: 8,
          alarms: allAlarms,
        })
      );
    }
   }
 }