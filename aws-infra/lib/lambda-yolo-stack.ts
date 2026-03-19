import { Duration, Size, Stack, StackProps } from "aws-cdk-lib";
import * as ecr from "aws-cdk-lib/aws-ecr";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as s3 from "aws-cdk-lib/aws-s3";
import { Construct } from "constructs";

export interface LambdaYoloStackProps extends StackProps {
  projectName: string;
  stage: string;
  bucket: s3.IBucket;
  yoloRepo: ecr.IRepository;
  yoloImageTag: string;
}

export class LambdaYoloStack extends Stack {
  public readonly yoloFunction: lambda.DockerImageFunction;

  constructor(scope: Construct, id: string, props: LambdaYoloStackProps) {
    super(scope, id, props);

    const role = new iam.Role(this, "YoloRole", {
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
    });

    role.addManagedPolicy(
      iam.ManagedPolicy.fromAwsManagedPolicyName(
        "service-role/AWSLambdaBasicExecutionRole"
      )
    );

    props.bucket.grantReadWrite(role);

    this.yoloFunction = new lambda.DockerImageFunction(this, "YoloProcessor", {
      functionName: `${props.projectName}-${props.stage}-yoloprocessor`.toLowerCase(),
      code: lambda.DockerImageCode.fromEcr(props.yoloRepo, {
        tagOrDigest: props.yoloImageTag,
      }),
      role,
      timeout: Duration.seconds(90),
      memorySize: 3072,
      ephemeralStorageSize: Size.gibibytes(2),
      architecture: lambda.Architecture.X86_64,
      environment: {
        AWS_STORAGE_BUCKET_NAME: props.bucket.bucketName,
      },
    });

    this.yoloFunction.addFunctionUrl({
      authType: lambda.FunctionUrlAuthType.NONE,
      cors: {
        allowedOrigins: ["*"],
        allowedMethods: [lambda.HttpMethod.ALL],
        allowedHeaders: ["*"],
      },
    });
  }
}