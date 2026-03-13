import { RemovalPolicy, Stack, StackProps } from "aws-cdk-lib";
import * as ecr from "aws-cdk-lib/aws-ecr";
import { Construct } from "constructs";

export interface EcrStackProps extends StackProps {
  djangoRepoName: string;
  lambdaRembgRepoName: string;
  lambdaYoloRepoName: string;
  lambdaBgRepoName: string;
}

export class EcrStack extends Stack {
  public readonly djangoRepo: ecr.Repository;
  public readonly lambdaRembgRepo: ecr.Repository;
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
            maxImageCount: 30
          }
        ],
        removalPolicy: RemovalPolicy.RETAIN,
        emptyOnDelete: false
      });

    this.djangoRepo = createRepo("DjangoRepo", props.djangoRepoName);
    this.lambdaRembgRepo = createRepo("LambdaRembgRepo", props.lambdaRembgRepoName);
    this.lambdaYoloRepo = createRepo("LambdaYoloRepo", props.lambdaYoloRepoName);
    this.lambdaBgRepo = createRepo("LambdaBgRepo", props.lambdaBgRepoName);
  }
}