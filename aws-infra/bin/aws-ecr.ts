#!/usr/bin/env node
import "source-map-support/register";
import * as cdk from "aws-cdk-lib";
import { config } from "../config/env";
import { EcrStack } from "../lib/ecr-stack";

const app = new cdk.App();

const env = {
  account: config.awsAccountId,
  region: config.awsRegion,
};

const prefix = `${config.projectName}-${config.stage}`;

new EcrStack(app, `${prefix}-ecr`, {
  env,
  djangoRepoName: config.djangoEcrRepoName,
  lambdaYoloRepoName: config.lambdaYoloEcrRepoName,
  lambdaBgRepoName: config.lambdaBgEcrRepoName,
});

app.synth();