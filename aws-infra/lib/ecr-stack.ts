import { CfnOutput, RemovalPolicy, Stack, StackProps } from "aws-cdk-lib";
import * as ecr from "aws-cdk-lib/aws-ecr";
import { Construct } from "constructs";

export interface EcrStackProps extends StackProps {
  djangoRepoName: string;
  lambdaYoloRepoName: string;
  lambdaBgRepoName: string;
}

export class EcrStack extends Stack {
  public readonly djangoRepo: ecr.Repository;
  public readonly lambdaYoloRepo: ecr.Repository;
  public readonly lambdaBgRepo: ecr.Repository;

  constructor(scope: Construct, id: string, props: EcrStackProps) {
    super(scope, id, props);

    const createRepo = (logicalId: string, repositoryName: string) =>
      new ecr.Repository(this, logicalId, {
        repositoryName,
        imageScanOnPush: true,
        imageTagMutability: ecr.TagMutability.IMMUTABLE,
        lifecycleRules: [
          {
            maxImageCount: 5,
          },
        ],
        removalPolicy: RemovalPolicy.RETAIN,
        emptyOnDelete: false,
      });

    this.djangoRepo = createRepo("DjangoRepo", props.djangoRepoName);
    this.lambdaYoloRepo = createRepo("LambdaYoloRepo", props.lambdaYoloRepoName);
    this.lambdaBgRepo = createRepo("LambdaBgRepo", props.lambdaBgRepoName);

    new CfnOutput(this, "DjangoRepoName", {
      value: this.djangoRepo.repositoryName,
    });
    new CfnOutput(this, "DjangoRepoUri", {
      value: this.djangoRepo.repositoryUri,
    });

    new CfnOutput(this, "LambdaYoloRepoName", {
      value: this.lambdaYoloRepo.repositoryName,
    });
    new CfnOutput(this, "LambdaYoloRepoUri", {
      value: this.lambdaYoloRepo.repositoryUri,
    });

    new CfnOutput(this, "LambdaBgRepoName", {
      value: this.lambdaBgRepo.repositoryName,
    });
    new CfnOutput(this, "LambdaBgRepoUri", {
      value: this.lambdaBgRepo.repositoryUri,
    });
  }
}