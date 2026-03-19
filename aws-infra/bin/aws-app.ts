#!/usr/bin/env node
import "source-map-support/register";
import * as cdk from "aws-cdk-lib";
import * as ecr from "aws-cdk-lib/aws-ecr";
import { config } from "../config/env";
import { AppRunnerStack } from "../lib/apprunner-stack";
import { LambdaBgStack } from "../lib/lambda-bg-stack";
import { LambdaYoloStack } from "../lib/lambda-yolo-stack";
import { StorageStack } from "../lib/storage-stack";

const app = new cdk.App();

const env = {
  account: config.awsAccountId,
  region: config.awsRegion,
};

const prefix = `${config.projectName}-${config.stage}`;

const djangoRepo = ecr.Repository.fromRepositoryName(
  app,
  "ImportedDjangoRepo",
  config.djangoEcrRepoName
);

const yoloRepo = ecr.Repository.fromRepositoryName(
  app,
  "ImportedYoloRepo",
  config.lambdaYoloEcrRepoName
);

const bgRepo = ecr.Repository.fromRepositoryName(
  app,
  "ImportedBgRepo",
  config.lambdaBgEcrRepoName
);

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
  yoloRepo,
  yoloImageTag: config.lambdaYoloImageTag,
});
lambdaYoloStack.addDependency(storageStack);

const lambdaBgStack = new LambdaBgStack(app, `${prefix}-lambda-bg`, {
  env,
  projectName: config.projectName,
  stage: config.stage,
  bucket: storageStack.mediaBucket,
  bgRepo,
  bgImageTag: config.lambdaBgImageTag,
});
lambdaBgStack.addDependency(storageStack);

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
  djangoRepo,
  djangoImageTag: config.djangoImageTag,
  bucket: storageStack.mediaBucket,
  mediaBaseUrl,
  domainName: apiDomainName,
  hostedZoneDomain: config.hostedZoneDomain || undefined,
  djangoEnv: config.djangoEnv,
});
appRunnerStack.addDependency(storageStack);

app.synth();