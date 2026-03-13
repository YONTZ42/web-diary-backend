import { Duration, Stack, StackProps,Size } from "aws-cdk-lib";
import * as ecr from "aws-cdk-lib/aws-ecr";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as s3 from "aws-cdk-lib/aws-s3";
import { Construct } from "constructs";

export interface LambdaStackProps extends StackProps {
  projectName: string;
  stage: string;
  bucket: s3.IBucket;
  rembgRepo: ecr.IRepository;
  yoloRepo: ecr.IRepository;
  bgRepo: ecr.IRepository;
  rembgImageTag: string;
  yoloImageTag: string;
  bgImageTag: string;
}

export class LambdaStack extends Stack {
  public readonly rembgFunction: lambda.DockerImageFunction;
  public readonly yoloFunction: lambda.DockerImageFunction;
  public readonly bgFunction: lambda.DockerImageFunction;

  constructor(scope: Construct, id: string, props: LambdaStackProps) {
    super(scope, id, props);

    const createRole = (name: string) => {
      const role = new iam.Role(this, `${name}Role`, {
        assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com")
      });

      role.addManagedPolicy(
        iam.ManagedPolicy.fromAwsManagedPolicyName("service-role/AWSLambdaBasicExecutionRole")
      );

      props.bucket.grantReadWrite(role);
      return role;
    };

    const createFunction = (
      logicalId: string,
      repo: ecr.IRepository,
      tagOrDigest: string,
      role: iam.IRole,
      memorySize: number,
      timeoutSeconds: number
    ) =>
      new lambda.DockerImageFunction(this, logicalId, {
        functionName: `${props.projectName}-${props.stage}-${logicalId}`.toLowerCase(),
        code: lambda.DockerImageCode.fromEcr(repo, {
          tagOrDigest
        }),
        role,
        timeout: Duration.seconds(timeoutSeconds),
        memorySize,
        ephemeralStorageSize: Size.gibibytes(2),
        architecture: lambda.Architecture.X86_64,
        environment: {
          AWS_STORAGE_BUCKET_NAME: props.bucket.bucketName
        }
      });

    const rembgRole = createRole("Rembg");
    const yoloRole = createRole("Yolo");
    const bgRole = createRole("Bg");

    this.rembgFunction = createFunction(
      "RembgProcessor",
      props.rembgRepo,
      props.rembgImageTag,
      rembgRole,
      2048,
      60
    );

    this.yoloFunction = createFunction(
      "YoloProcessor",
      props.yoloRepo,
      props.yoloImageTag,
      yoloRole,
      3072,
      90
    );

    this.bgFunction = createFunction(
      "BackgroundGenerator",
      props.bgRepo,
      props.bgImageTag,
      bgRole,
      2048,
      60
    );

    const addFunctionUrl = (fn: lambda.Function) => {
      fn.addFunctionUrl({
        authType: lambda.FunctionUrlAuthType.NONE,
        cors: {
          allowedOrigins: ["*"],
          allowedMethods: [lambda.HttpMethod.ALL],
          allowedHeaders: ["*"]
        }
      });
    };

    addFunctionUrl(this.rembgFunction);
    addFunctionUrl(this.yoloFunction);
    addFunctionUrl(this.bgFunction);
  }
}