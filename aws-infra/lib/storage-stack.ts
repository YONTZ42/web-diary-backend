import {
  CfnOutput,
  Duration,
  RemovalPolicy,
  Stack,
  StackProps
} from "aws-cdk-lib";
import * as acm from "aws-cdk-lib/aws-certificatemanager";
import * as cloudfront from "aws-cdk-lib/aws-cloudfront";
import * as origins from "aws-cdk-lib/aws-cloudfront-origins";
import * as route53 from "aws-cdk-lib/aws-route53";
import * as s3 from "aws-cdk-lib/aws-s3";
import { Construct } from "constructs";

export interface StorageStackProps extends StackProps {
  bucketName: string;
  enableCloudFront: boolean;
  mediaDomainName?: string;
  hostedZoneDomain?: string;
}

export class StorageStack extends Stack {
  public readonly mediaBucket: s3.Bucket;
  public readonly distribution?: cloudfront.Distribution;
  public readonly distributionDomainName?: string;
  public readonly mediaCertificate?: acm.ICertificate;
  public readonly hostedZone?: route53.IHostedZone;

  constructor(scope: Construct, id: string, props: StorageStackProps) {
    super(scope, id, props);

    this.mediaBucket = new s3.Bucket(this, "MediaBucket", {
      bucketName: props.bucketName,
      versioned: true,
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      cors: [
        {
          allowedMethods: [
            s3.HttpMethods.GET,
            s3.HttpMethods.PUT,
            s3.HttpMethods.POST,
            s3.HttpMethods.HEAD
          ],
          allowedOrigins: ["*"],
          allowedHeaders: ["*"],
          exposedHeaders: ["ETag"],
          maxAge: 3000
        }
      ],
      lifecycleRules: [
        {
          enabled: true,
          abortIncompleteMultipartUploadAfter: Duration.days(7),
          noncurrentVersionExpiration: Duration.days(30)
        }
      ],
      removalPolicy: RemovalPolicy.RETAIN,
      autoDeleteObjects: false
    });

    if (props.enableCloudFront) {
      if (props.mediaDomainName && props.hostedZoneDomain) {
        this.hostedZone = route53.HostedZone.fromLookup(this, "HostedZone", {
          domainName: props.hostedZoneDomain
        });

        this.mediaCertificate = new acm.DnsValidatedCertificate(this, "MediaCertificate", {
          domainName: props.mediaDomainName,
          hostedZone: this.hostedZone,
          region: "us-east-1"
        });
      }

      const originAccessControl = new cloudfront.S3OriginAccessControl(this, "MediaOac", {
        description: "OAC for media bucket"
      });

      this.distribution = new cloudfront.Distribution(this, "MediaDistribution", {
        defaultBehavior: {
          origin: origins.S3BucketOrigin.withOriginAccessControl(this.mediaBucket, {
            originAccessControl
          }),
          viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          cachePolicy: cloudfront.CachePolicy.CACHING_OPTIMIZED
        },
        defaultRootObject: "",
        domainNames:
          props.mediaDomainName && this.mediaCertificate ? [props.mediaDomainName] : undefined,
        certificate: this.mediaCertificate
      });

      this.distributionDomainName = this.distribution.distributionDomainName;
    }

    new CfnOutput(this, "MediaBucketName", {
      value: this.mediaBucket.bucketName
    });

    if (this.distributionDomainName) {
      new CfnOutput(this, "MediaDistributionDomainName", {
        value: this.distributionDomainName
      });
    }
  }
}