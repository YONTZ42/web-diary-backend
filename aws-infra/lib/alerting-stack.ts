import { Stack, StackProps } from "aws-cdk-lib";
import * as chatbot from "aws-cdk-lib/aws-chatbot";
import * as iam from "aws-cdk-lib/aws-iam";
import * as sns from "aws-cdk-lib/aws-sns";
import { Construct } from "constructs";

export interface AlertingStackProps extends StackProps {
  projectName: string;
  stage: string;
  alarmTopic: sns.ITopic;
  slackWorkspaceId: string;
  slackChannelId: string;
  slackChannelConfigurationName?: string;
}

export class AlertingStack extends Stack {
  public readonly slackChannelConfiguration: chatbot.SlackChannelConfiguration;

  constructor(scope: Construct, id: string, props: AlertingStackProps) {
    super(scope, id, props);

    this.slackChannelConfiguration = new chatbot.SlackChannelConfiguration(
      this,
      "SlackAlerts",
      {
        slackChannelConfigurationName:
          props.slackChannelConfigurationName ??
          `${props.projectName}-${props.stage}-alerts`,
        slackWorkspaceId: props.slackWorkspaceId,
        slackChannelId: props.slackChannelId,
        notificationTopics: [props.alarmTopic],
        loggingLevel: chatbot.LoggingLevel.ERROR,
        guardrailPolicies: [
          iam.ManagedPolicy.fromAwsManagedPolicyName("ReadOnlyAccess"),
        ],
        userRoleRequired: false,
      }
    );
  }
}