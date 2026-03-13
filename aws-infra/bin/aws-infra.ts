#!/usr/bin/env node
import "source-map-support/register";
import * as cdk from "aws-cdk-lib";
import { config } from "../config/env";
import { AppRunnerStack } from "../lib/apprunner-stack";
import { EcrStack } from "../lib/ecr-stack";
import { LambdaStack } from "../lib/lambda-stack";
import { MonitoringStack } from "../lib/monitoring-stack";
import { StorageStack } from "../lib/storage-stack";

const app = new cdk.App();

const env = {
  account: config.awsAccountId,
  region: config.awsRegion
};

const prefix = `${config.projectName}-${config.stage}`;

const ecrStack = new EcrStack(app, `${prefix}-ecr`, {
  env,
  djangoRepoName: config.djangoEcrRepoName,
  lambdaRembgRepoName: config.lambdaRembgEcrRepoName,
  lambdaYoloRepoName: config.lambdaYoloEcrRepoName,
  lambdaBgRepoName: config.lambdaBgEcrRepoName
});

const mediaDomainName =
  config.domainName && config.mediaSubdomain
    ? `${config.mediaSubdomain}.${config.domainName}`
    : undefined;

const storageStack = new StorageStack(app, `${prefix}-storage`, {
  env,
  bucketName: config.mediaBucketName,
  enableCloudFront: config.enableCloudFront,
  mediaDomainName,
  hostedZoneDomain: config.hostedZoneDomain || undefined
});

const lambdaStack = new LambdaStack(app, `${prefix}-lambda`, {
  env,
  projectName: config.projectName,
  stage: config.stage,
  bucket: storageStack.mediaBucket,
  rembgRepo: ecrStack.lambdaRembgRepo,
  yoloRepo: ecrStack.lambdaYoloRepo,
  bgRepo: ecrStack.lambdaBgRepo,
  rembgImageTag: config.lambdaRembgImageTag,
  yoloImageTag: config.lambdaYoloImageTag,
  bgImageTag: config.lambdaBgImageTag
});
lambdaStack.addDependency(ecrStack);
lambdaStack.addDependency(storageStack);

const apiDomainName =
  config.domainName && config.apiSubdomain
    ? `${config.apiSubdomain}.${config.domainName}`
    : undefined;

const mediaBaseUrl = storageStack.distributionDomainName
  ? `https://${storageStack.distributionDomainName}`
  : `https://${storageStack.mediaBucket.bucketRegionalDomainName}`;

const appRunnerStack = new AppRunnerStack(app, `${prefix}-apprunner`, {
  env,
  projectName: config.projectName,
  stage: config.stage,
  serviceName: config.apprunnerServiceName,
  port: config.apprunnerPort,
  djangoRepo: ecrStack.djangoRepo,
  djangoImageTag: config.djangoImageTag,
  bucket: storageStack.mediaBucket,
  mediaBaseUrl,
  domainName: apiDomainName,
  hostedZoneDomain: config.hostedZoneDomain || undefined,
  djangoEnv: config.djangoEnv
});
appRunnerStack.addDependency(ecrStack);
appRunnerStack.addDependency(storageStack);

const monitoringStack = new MonitoringStack(app, `${prefix}-monitoring`, {
  env,
  alarmEmail: config.alarmEmail || undefined,
  appRunnerService: appRunnerStack.service,
  lambdaFunctions: [
    lambdaStack.rembgFunction,
    lambdaStack.yoloFunction,
    lambdaStack.bgFunction
  ]
});
monitoringStack.addDependency(lambdaStack);
monitoringStack.addDependency(appRunnerStack);

app.synth();
