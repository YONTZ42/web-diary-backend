#!/usr/bin/env node
import "source-map-support/register";
import * as cdk from "aws-cdk-lib";
import * as ecr from "aws-cdk-lib/aws-ecr";
import { config } from "../config/env";
import { AppRunnerStack } from "../lib/apprunner-stack";
import { LambdaBgStack } from "../lib/lambda-bg-stack";
import { LambdaYoloStack } from "../lib/lambda-yolo-stack";
import { StorageStack } from "../lib/storage-stack";

import { AlertingStack } from "../lib/alerting-stack";
import { MonitoringStack } from "../lib/monitoring-stack";


const app = new cdk.App();

const env = {
  account: config.awsAccountId,
  region: config.awsRegion,
};

const prefix = `${config.projectName}-${config.stage}`;


const mediaDomainName =
  config.domainName && config.mediaSubdomain
    ? `${config.mediaSubdomain}.${config.domainName}`
    : undefined;

    
const storageStack = new StorageStack(app, `${prefix}-storage`, {
  env,
  bucketName: config.mediaBucketName,
  enableCloudFront: config.enableCloudFront,
  mediaDomainName,
  hostedZoneDomain: config.hostedZoneDomain || undefined,
});

const lambdaYoloStack = new LambdaYoloStack(app, `${prefix}-lambda-yolo`, {
  env,
  projectName: config.projectName,
  stage: config.stage,
  bucket: storageStack.mediaBucket,
  yoloRepoName: config.lambdaYoloEcrRepoName,
  yoloImageTag: config.lambdaYoloImageTag,
});
lambdaYoloStack.addDependency(storageStack);

const lambdaBgStack = new LambdaBgStack(app, `${prefix}-lambda-bg`, {
  env,
  projectName: config.projectName,
  stage: config.stage,
  bucket: storageStack.mediaBucket,
  bgRepoName: config.lambdaBgEcrRepoName,
  bgImageTag: config.lambdaBgImageTag,
});
lambdaBgStack.addDependency(storageStack);

const apiDomainName =
  config.domainName && config.apiSubdomain
    ? `${config.apiSubdomain}.${config.domainName}`
    : undefined;

const mediaBaseUrl = config.enableCloudFront
  ? `https://${storageStack.distributionDomainName}`
  : `https://${storageStack.mediaBucket.bucketRegionalDomainName}`;

const appRunnerStack = new AppRunnerStack(app, `${prefix}-apprunner`, {
  env,
  projectName: config.projectName,
  stage: config.stage,
  serviceName: config.apprunnerServiceName,
  port: config.apprunnerPort,
  djangoRepoName: config.djangoEcrRepoName,
  djangoImageTag: config.djangoImageTag,
  bucket: storageStack.mediaBucket,
  mediaBaseUrl,
  domainName: apiDomainName,
  hostedZoneDomain: config.hostedZoneDomain || undefined,
  djangoEnv: config.djangoEnv,
});
appRunnerStack.addDependency(storageStack);

// ... 既存 stack 作成後

const monitoringStack = new MonitoringStack(app, `${prefix}-monitoring`, {
  env,
  projectName: config.projectName,
  stage: config.stage,
  alarmEmail: config.alarmEmail || undefined,
  appRunnerService: appRunnerStack.service,
  lambdaConfigs: [
    {
      fn: lambdaBgStack.bgFunction,
      durationWarningMs: 15000,
      durationCriticalMs: 30000,
    },
    {
      fn: lambdaYoloStack.yoloFunction,
      durationWarningMs: 25000,
      durationCriticalMs: 45000,
    },
  ],
});
monitoringStack.addDependency(appRunnerStack);
monitoringStack.addDependency(lambdaBgStack);
monitoringStack.addDependency(lambdaYoloStack);

const alertingStack = new AlertingStack(app, `${prefix}-alerting`, {
  env,
  projectName: config.projectName,
  stage: config.stage,
  alarmTopic: monitoringStack.alarmTopic,
  slackWebhookSecretArn: config.slackWebhookSecretArn,
  runbookBaseUrl: config.runbookBaseUrl || undefined,
});
alertingStack.addDependency(monitoringStack);


app.synth();