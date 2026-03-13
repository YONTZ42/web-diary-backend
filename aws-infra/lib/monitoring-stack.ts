import { Duration, Stack, StackProps } from "aws-cdk-lib";
import * as apprunner from "aws-cdk-lib/aws-apprunner";
import * as cloudwatch from "aws-cdk-lib/aws-cloudwatch";
import * as cwActions from "aws-cdk-lib/aws-cloudwatch-actions";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as sns from "aws-cdk-lib/aws-sns";
import * as subs from "aws-cdk-lib/aws-sns-subscriptions";
import { Construct } from "constructs";

export interface MonitoringStackProps extends StackProps {
  alarmEmail?: string;
  appRunnerService?: apprunner.CfnService;
  lambdaFunctions: lambda.IFunction[];
}

export class MonitoringStack extends Stack {
  constructor(scope: Construct, id: string, props: MonitoringStackProps) {
    super(scope, id, props);

    const topic = new sns.Topic(this, "AlarmTopic", {
      displayName: "Mini Museum Infra Alarm Topic"
    });

    if (props.alarmEmail) {
      topic.addSubscription(new subs.EmailSubscription(props.alarmEmail));
    }

    const alarmAction = new cwActions.SnsAction(topic);

    for (const fn of props.lambdaFunctions) {
      const errorAlarm = new cloudwatch.Alarm(this, `${fn.node.id}ErrorsAlarm`, {
        metric: fn.metricErrors({
          period: Duration.minutes(5),
          statistic: "sum"
        }),
        threshold: 1,
        evaluationPeriods: 1,
        alarmDescription: `${fn.functionName} Lambda errors`
      });
      errorAlarm.addAlarmAction(alarmAction);

      const durationAlarm = new cloudwatch.Alarm(this, `${fn.node.id}DurationAlarm`, {
        metric: fn.metricDuration({
          period: Duration.minutes(5),
          statistic: "avg"
        }),
        threshold: 20000,
        evaluationPeriods: 1,
        alarmDescription: `${fn.functionName} Lambda duration too high`
      });
      durationAlarm.addAlarmAction(alarmAction);
    }

    if (props.appRunnerService) {
      const serviceArn = props.appRunnerService.attrServiceArn;
      const serviceName = serviceArn.split("/").pop() ?? serviceArn;

      const appRunner5xxAlarm = new cloudwatch.Alarm(this, "AppRunner5xxAlarm", {
        metric: new cloudwatch.Metric({
          namespace: "AWS/AppRunner",
          metricName: "5xxStatusResponses",
          dimensionsMap: {
            ServiceName: serviceName
          },
          period: Duration.minutes(5),
          statistic: "sum"
        }),
        threshold: 1,
        evaluationPeriods: 1
      });
      appRunner5xxAlarm.addAlarmAction(alarmAction);
    }
  }
}