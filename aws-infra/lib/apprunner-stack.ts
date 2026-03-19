import { CfnOutput, Duration, Stack, StackProps } from "aws-cdk-lib";
import * as apprunner from "aws-cdk-lib/aws-apprunner";
import * as ecr from "aws-cdk-lib/aws-ecr";
import * as iam from "aws-cdk-lib/aws-iam";
import * as route53 from "aws-cdk-lib/aws-route53";
import * as s3 from "aws-cdk-lib/aws-s3";
import { Construct } from "constructs";
import * as cr from "aws-cdk-lib/custom-resources";

export interface AppRunnerStackProps extends StackProps {
  projectName: string;
  stage: string;
  serviceName: string;
  port: number;
  djangoRepoName: string;
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

    const djangoRepo = ecr.Repository.fromRepositoryName(
      this,
      "ImportedDjangoRepo",
      props.djangoRepoName
    );

    const accessRole = new iam.Role(this, "AppRunnerAccessRole", {
      assumedBy: new iam.ServicePrincipal("build.apprunner.amazonaws.com"),
    });

    accessRole.addManagedPolicy(
      iam.ManagedPolicy.fromAwsManagedPolicyName(
        "service-role/AWSAppRunnerServicePolicyForECRAccess"
      )
    );

    const instanceRole = new iam.Role(this, "AppRunnerInstanceRole", {
      assumedBy: new iam.ServicePrincipal("tasks.apprunner.amazonaws.com"),
    });

    props.bucket.grantReadWrite(instanceRole);

    const runtimeEnv = [
      ...Object.entries(props.djangoEnv).map(([name, value]) => ({
        name,
        value,
      })),
      {
        name: "MEDIA_BASE_URL",
        value: props.mediaBaseUrl,
      },
    ];

    this.service = new apprunner.CfnService(this, "ApiService", {
      serviceName: `${props.serviceName}-${props.stage}`,
      sourceConfiguration: {
        authenticationConfiguration: {
          accessRoleArn: accessRole.roleArn,
        },
        autoDeploymentsEnabled: false,
        imageRepository: {
          imageIdentifier: `${djangoRepo.repositoryUri}:${props.djangoImageTag}`,
          imageRepositoryType: "ECR",
          imageConfiguration: {
            port: String(props.port),
            runtimeEnvironmentVariables: runtimeEnv,
          },
        },
      },
      instanceConfiguration: {
        cpu: "1024",
        memory: "2048",
        instanceRoleArn: instanceRole.roleArn,
      },
      healthCheckConfiguration: {
        protocol: "HTTP",
        path: "/healthz",
        interval: 10,
        timeout: 5,
        healthyThreshold: 1,
        unhealthyThreshold: 5,
      },
    });

    this.serviceUrl = `https://${this.service.attrServiceUrl}`;

    if (props.domainName && props.hostedZoneDomain) {
      if (!props.domainName.endsWith(`.${props.hostedZoneDomain}`)) {
        throw new Error(
          `domainName (${props.domainName}) must be a subdomain of hostedZoneDomain (${props.hostedZoneDomain}).`
        );
      }

      const hostedZone = route53.HostedZone.fromLookup(this, "ApiHostedZone", {
        domainName: props.hostedZoneDomain,
      });

      const recordName = props.domainName.slice(
        0,
        -(props.hostedZoneDomain.length + 1)
      );

      const domainAssociation = new cr.AwsCustomResource(
        this,
        "ApiCustomDomainAssociation",
        {
          onCreate: {
            service: "AppRunner",
            action: "associateCustomDomain",
            parameters: {
              ServiceArn: this.service.attrServiceArn,
              DomainName: props.domainName,
              EnableWWWSubdomain: false,
            },
            physicalResourceId: cr.PhysicalResourceId.of(
              `${props.projectName}-${props.stage}-${props.domainName}-association`
            ),
          },
          onDelete: {
            service: "AppRunner",
            action: "disassociateCustomDomain",
            parameters: {
              ServiceArn: this.service.attrServiceArn,
              DomainName: props.domainName,
            },
          },
          policy: cr.AwsCustomResourcePolicy.fromStatements([
            new iam.PolicyStatement({
              actions: [
                "apprunner:AssociateCustomDomain",
                "apprunner:DisassociateCustomDomain",
                "apprunner:DescribeCustomDomains",
              ],
              resources: [this.service.attrServiceArn],
            }),
          ]),
        }
      );
      domainAssociation.node.addDependency(this.service);

      const domainDescription = new cr.AwsCustomResource(
        this,
        "ApiCustomDomainDescription",
        {
          onCreate: {
            service: "AppRunner",
            action: "describeCustomDomains",
            parameters: {
              ServiceArn: this.service.attrServiceArn,
              MaxResults: 5,
            },
            physicalResourceId: cr.PhysicalResourceId.of(
              `${props.projectName}-${props.stage}-${props.domainName}-describe`
            ),
          },
          onUpdate: {
            service: "AppRunner",
            action: "describeCustomDomains",
            parameters: {
              ServiceArn: this.service.attrServiceArn,
              MaxResults: 5,
            },
            physicalResourceId: cr.PhysicalResourceId.of(
              `${props.projectName}-${props.stage}-${props.domainName}-describe`
            ),
          },
          policy: cr.AwsCustomResourcePolicy.fromStatements([
            new iam.PolicyStatement({
              actions: ["apprunner:DescribeCustomDomains"],
              resources: [this.service.attrServiceArn],
            }),
          ]),
        }
      );
      domainDescription.node.addDependency(domainAssociation);

      new route53.CnameRecord(this, "ApiCustomDomainDnsRecord", {
        zone: hostedZone,
        recordName,
        domainName: domainDescription.getResponseField("DNSTarget"),
        ttl: Duration.minutes(5),
      });


      const validationRecordFullName = domainDescription.getResponseField(
        "CustomDomains.0.CertificateValidationRecords.0.Name"
      ).replace(/\.$/, "");
      const validationRecordValue = domainDescription.getResponseField(
        "CustomDomains.0.CertificateValidationRecords.0.Value"
      ).replace(/\.$/, "");
      const validationRecordName = validationRecordFullName.endsWith(
        `.${props.hostedZoneDomain}`
      )
        ? validationRecordFullName.slice(
            0,
            -(props.hostedZoneDomain.length + 1)
          )
        : validationRecordFullName;

      new route53.CnameRecord(
        this,
        "ApiCustomDomainCertificateValidationRecord",
        {
          zone: hostedZone,
          recordName: validationRecordName,
          domainName: validationRecordValue,
          ttl: Duration.minutes(5),
        }
      );

      new CfnOutput(this, "AppRunnerCustomDomain", {
        value: `https://${props.domainName}`,
      });
    }

    new CfnOutput(this, "AppRunnerServiceUrl", {
      value: this.serviceUrl,
    });
  }
}