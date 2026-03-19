import * as dotenv from "dotenv";

dotenv.config();

function required(name: string, fallback?: string): string {
  const value = process.env[name] ?? fallback;
  if (!value) {
    console.error(`FATAL: Missing environment variable [${name}]`);
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}


function optionalBool(name: string, fallback = false): boolean {
  const raw = process.env[name];
  if (raw == null) return fallback;
  return ["1", "true", "yes", "on"].includes(raw.toLowerCase());
}

/**
 * STAGEに応じてサフィックスを付与するロジック
 * 例: projectName -> "mini-museum-staging"
 */
function withStage(baseName: string): string {
  const stage = process.env.STAGE ?? "staging";
  return `${baseName}-${stage}`;
}

const stage = required("STAGE", "staging");
const s3BucketName=withStage(required("MEDIA_BUCKET_NAME", "mini-museum-media"));
const mediaSubdomain=withStage(required("MEDIA_SUBDOMAIN", "media"));
const domainName= process.env.DOMAIN_NAME ?? "";

export const config = {
  awsAccountId: required("CDK_DEFAULT_ACCOUNT", process.env.AWS_ACCOUNT_ID),
  awsRegion: required("CDK_DEFAULT_REGION", process.env.AWS_REGION ?? "ap-northeast-1"),
  projectName: required("PROJECT_NAME", "mini-museum"),
  stage: stage,

  domainName: domainName,
  apiSubdomain: withStage(required("API_SUBDOMAIN", "api")),
  mediaSubdomain: mediaSubdomain,
  hostedZoneDomain: process.env.HOSTED_ZONE_DOMAIN ?? "",

  djangoEcrRepoName: withStage(required("DJANGO_ECR_REPO", "mini-museum-api")),
  lambdaYoloEcrRepoName: withStage(required("LAMBDA_YOLO_ECR_REPO", "mini-museum-lambda-yolo")),
  lambdaBgEcrRepoName: withStage(required("LAMBDA_BG_ECR_REPO", "mini-museum-lambda-bg")),

  mediaBucketName: s3BucketName,
  enableCloudFront: optionalBool("ENABLE_CLOUDFRONT", true),

  apprunnerServiceName: withStage(required("APP_RUNNER_SERVICE_NAME", "mini-museum-api")),
  apprunnerPort: Number(process.env.APP_RUNNER_PORT ?? "8080"),

  djangoImageTag: process.env.DJANGO_IMAGE_TAG ?? "initial",
  lambdaYoloImageTag: process.env.LAMBDA_YOLO_IMAGE_TAG ?? "initial",
  lambdaBgImageTag: process.env.LAMBDA_BG_IMAGE_TAG ?? "initial",

  djangoCpu: Number(process.env.APP_RUNNER_CPU ?? "1024"),
  djangoMemory: Number(process.env.APP_RUNNER_MEMORY ?? "2048"),

  alarmEmail: process.env.ALARM_EMAIL ?? "",

  djangoEnv: {
    APP_ENV: process.env.APP_ENV ??"staging",
    DEBUG: process.env.DEBUG ?? "True",
    DATABASE_URL: process.env.DATABASE_URL ?? "",
    SECRET_KEY: process.env.SECRET_KEY ?? "",
    ALLOWED_HOSTS: process.env.ALLOWED_HOSTS ?? "",
    CORS_ALLOWED_ORIGINS: process.env.CORS_ALLOWED_ORIGINS ?? "",
    GOOGLE_OAUTH_CLIENT_ID: process.env.GOOGLE_OAUTH_CLIENT_ID ?? "",
    AWS_STORAGE_BUCKET_NAME: s3BucketName,
    AWS_S3_REGION: "ap-northeast-1",
    CLOUDFRONT_DOMAIN: `${mediaSubdomain}.${domainName}`,
    CLOUDFRONT_PUBLIC_KEY_ID: process.env.CLOUDFRONT_PUBLIC_KEY_ID ?? ""
  }
};