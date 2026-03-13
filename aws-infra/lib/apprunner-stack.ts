import { CfnOutput, Duration, Stack, StackProps } from "aws-cdk-lib";
import * as apprunner from "aws-cdk-lib/aws-apprunner";
import * as ecr from "aws-cdk-lib/aws-ecr";
import * as iam from "aws-cdk-lib/aws-iam";
import * as route53 from "aws-cdk-lib/aws-route53";
import * as s3 from "aws-cdk-lib/aws-s3";
import { Construct } from "constructs";

export interface AppRunnerStackProps extends StackProps {
  projectName: string;
  stage: string;
  serviceName: string;
  port: number;
  djangoRepo: ecr.IRepository;
  djangoImageTag: string;
  bucket: s3.IBucket;
  mediaBaseUrl: string;
  domainName?: string;
  hostedZoneDomain?: string;
  djangoEnv: Record<string, string>;
}

export class AppRunnerStack extends Stack {
  public readonly service: apprunner.CfnService;
  public readonly serviceUrl: string;

  constructor(scope: Construct, id: string, props: AppRunnerStackProps) {
    super(scope, id, props);

    const accessRole = new iam.Role(this, "AppRunnerAccessRole", {
      assumedBy: new iam.ServicePrincipal("build.apprunner.amazonaws.com")
    });

    accessRole.addManagedPolicy(
      iam.ManagedPolicy.fromAwsManagedPolicyName("service-role/AWSAppRunnerServicePolicyForECRAccess")
    );

    const instanceRole = new iam.Role(this, "AppRunnerInstanceRole", {
      assumedBy: new iam.ServicePrincipal("tasks.apprunner.amazonaws.com")
    });

    props.bucket.grantReadWrite(instanceRole);

    const runtimeEnv = [
      ...Object.entries(props.djangoEnv).map(([name, value]) => ({
        name,
        value
      })),
      {
        name: "AWS_STORAGE_BUCKET_NAME",
        value: props.bucket.bucketName
      },
      {
        name: "MEDIA_BASE_URL",
        value: props.mediaBaseUrl
      }
    ];

    this.service = new apprunner.CfnService(this, "ApiService", {
      serviceName: `${props.projectName}-${props.stage}-${props.serviceName}`,
      sourceConfiguration: {
        authenticationConfiguration: {
          accessRoleArn: accessRole.roleArn
        },
        autoDeploymentsEnabled: false,
        imageRepository: {
          imageIdentifier: `${props.djangoRepo.repositoryUri}:${props.djangoImageTag}`,
          imageRepositoryType: "ECR",
          imageConfiguration: {
            port: String(props.port),
            runtimeEnvironmentVariables: runtimeEnv
          }
        }
      },
      instanceConfiguration: {
        cpu: "1024",
        memory: "2048",
        instanceRoleArn: instanceRole.roleArn
      },
      healthCheckConfiguration: {
        protocol: "HTTP",
        path: "/healthz",
        interval: 10,
        timeout: 5,
        healthyThreshold: 1,
        unhealthyThreshold: 5
      }
    });

    this.serviceUrl = `https://${this.service.attrServiceUrl}`;


    new CfnOutput(this, "AppRunnerServiceUrl", {
      value: this.serviceUrl
    });
  }
}