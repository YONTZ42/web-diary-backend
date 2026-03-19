import { Duration, Size, Stack, StackProps } from "aws-cdk-lib";
import * as ecr from "aws-cdk-lib/aws-ecr";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as s3 from "aws-cdk-lib/aws-s3";
import { Construct } from "constructs";

export interface LambdaBgStackProps extends StackProps {
  projectName: string;
  stage: string;
  bucket: s3.IBucket;
  bgRepoName: string;
  bgImageTag: string;
}

export class LambdaBgStack extends Stack {
  public readonly bgFunction: lambda.DockerImageFunction;


  constructor(scope: Construct, id: string, props: LambdaBgStackProps) {
    super(scope, id, props);
    const bgRepo = ecr.Repository.fromRepositoryName(
      this,
      "ImportedBgRepo",
      props.bgRepoName
    );
    const role = new iam.Role(this, "BgRole", {
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
    });

    role.addManagedPolicy(
      iam.ManagedPolicy.fromAwsManagedPolicyName(
        "service-role/AWSLambdaBasicExecutionRole"
      )
    );

    props.bucket.grantReadWrite(role);

    this.bgFunction = new lambda.DockerImageFunction(this, "BackgroundGenerator", {
      functionName: `${props.projectName}-${props.stage}-backgroundgenerator`.toLowerCase(),
      code: lambda.DockerImageCode.fromEcr(bgRepo, {
        tagOrDigest: props.bgImageTag,
      }),
      role,
      timeout: Duration.seconds(60),
      memorySize: 2048,
      ephemeralStorageSize: Size.gibibytes(2),
      architecture: lambda.Architecture.X86_64,
      environment: {
        AWS_STORAGE_BUCKET_NAME: props.bucket.bucketName,
      },
    });

    this.bgFunction.addFunctionUrl({
      authType: lambda.FunctionUrlAuthType.NONE,
      cors: {
        allowedOrigins: ["*"],
        allowedMethods: [lambda.HttpMethod.ALL],
        allowedHeaders: ["*"],
      },
    });
  }
}