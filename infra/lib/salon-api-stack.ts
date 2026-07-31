import * as path from 'path';
import * as cdk from 'aws-cdk-lib';
import * as apigw from 'aws-cdk-lib/aws-apigatewayv2';
import * as integrations from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import { Construct } from 'constructs';

const API_DIR = path.join(__dirname, '..', '..', 'api');

/**
 * Salon REST API: Aurora Serverless v2 + a container-image Lambda behind an HTTP API,
 * per architecture.md (Lambda + API Gateway for the API, Aurora for persistence).
 *
 * The Lambda sits in private subnets with egress because it calls LiveKit, Stripe and
 * SNS — hence the single NAT gateway, which is the main fixed cost of this stack.
 */
export class SalonApiStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const vpc = new ec2.Vpc(this, 'Vpc', {
      maxAzs: 2,
      natGateways: 1,
      subnetConfiguration: [
        { name: 'public', subnetType: ec2.SubnetType.PUBLIC, cidrMask: 24 },
        { name: 'app', subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS, cidrMask: 24 },
        { name: 'data', subnetType: ec2.SubnetType.PRIVATE_ISOLATED, cidrMask: 24 },
      ],
    });

    // ── Database ──────────────────────────────────────────────────────────────
    const db = new rds.DatabaseCluster(this, 'Db', {
      engine: rds.DatabaseClusterEngine.auroraPostgres({
        // Pinned via of() rather than the CDK enum: the enum lags behind what RDS
        // actually offers, and unavailable versions only fail at deploy time.
        // Verify with: aws rds describe-db-engine-versions --engine aurora-postgresql
        version: rds.AuroraPostgresEngineVersion.of('16.14', '16'),
      }),
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      writer: rds.ClusterInstance.serverlessV2('writer'),
      serverlessV2MinCapacity: 0.5,
      serverlessV2MaxCapacity: 2,
      defaultDatabaseName: 'salon',
      credentials: rds.Credentials.fromGeneratedSecret('salon'),
      storageEncrypted: true,
      // Test environment: the cluster is meant to be torn down between test rounds.
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // ── Application secrets ───────────────────────────────────────────────────
    // JWT_SECRET is generated here so it never exists in the repo. The LiveKit and
    // Stripe values start empty and are filled in after deploy; config.py skips
    // empty entries, so a half-filled secret fails loudly rather than silently.
    const appSecret = new secretsmanager.Secret(this, 'AppConfig', {
      secretName: 'salon/app-config',
      description: 'LiveKit, Stripe and JWT credentials read by the Salon API Lambda',
      generateSecretString: {
        secretStringTemplate: JSON.stringify({
          LIVEKIT_URL: '',
          LIVEKIT_API_KEY: '',
          LIVEKIT_API_SECRET: '',
          STRIPE_SECRET_KEY: '',
          SALON_WEB_BASE_URL: '',
          SALON_INSTALL_URL: '',
        }),
        generateStringKey: 'JWT_SECRET',
        passwordLength: 48,
        excludePunctuation: true,
      },
    });

    // ── Functions ─────────────────────────────────────────────────────────────
    const commonEnv = {
      APP_SECRET_ARN: appSecret.secretArn,
      DB_SECRET_ARN: db.secret!.secretArn,
      DB_HOST: db.clusterEndpoint.hostname,
      DB_NAME: 'salon',
      // OTP codes are read from CloudWatch instead of being texted, so no SNS
      // origination number is needed to start testing. Flip to 'false' once an
      // origination identity is approved — nobody but a CloudWatch reader can log in
      // while this is 'true', which is fine for a private two-device test.
      DEV_MODE: 'true',
    };

    const apiFn = new lambda.DockerImageFunction(this, 'ApiFn', {
      functionName: 'salon-api',
      code: lambda.DockerImageCode.fromImageAsset(API_DIR, { file: 'Dockerfile.lambda' }),
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      memorySize: 1024,
      // API Gateway caps a request at 29s, so a longer function timeout cannot help.
      timeout: cdk.Duration.seconds(29),
      environment: commonEnv,
      logGroup: new logs.LogGroup(this, 'ApiLogs', {
        // Named explicitly: OTP codes are read from here in DEV_MODE, and a generated
        // name makes `aws logs tail` guesswork.
        logGroupName: '/aws/lambda/salon-api',
        retention: logs.RetentionDays.TWO_WEEKS,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
      }),
    });

    const migrateFn = new lambda.DockerImageFunction(this, 'MigrateFn', {
      functionName: 'salon-api-migrate',
      code: lambda.DockerImageCode.fromImageAsset(API_DIR, {
        file: 'Dockerfile.lambda',
        cmd: ['src.migrate_handler.handler'],
      }),
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      memorySize: 512,
      timeout: cdk.Duration.minutes(5),
      environment: commonEnv,
      logGroup: new logs.LogGroup(this, 'MigrateLogs', {
        logGroupName: '/aws/lambda/salon-api-migrate',
        retention: logs.RetentionDays.TWO_WEEKS,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
      }),
    });

    for (const fn of [apiFn, migrateFn]) {
      appSecret.grantRead(fn);
      db.secret!.grantRead(fn);
      db.connections.allowDefaultPortFrom(fn);
    }

    // SNS SMS to arbitrary phone numbers cannot be scoped to a resource ARN.
    apiFn.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ['sns:Publish'],
        resources: ['*'],
        conditions: { Null: { 'sns:TopicArn': 'true' } },
      }),
    );

    // ── HTTP API ──────────────────────────────────────────────────────────────
    const httpApi = new apigw.HttpApi(this, 'HttpApi', {
      apiName: 'salon-api',
      defaultIntegration: new integrations.HttpLambdaIntegration('ApiIntegration', apiFn),
    });

    new cdk.CfnOutput(this, 'ApiUrl', { value: httpApi.apiEndpoint });
    new cdk.CfnOutput(this, 'DbEndpoint', { value: db.clusterEndpoint.hostname });
    new cdk.CfnOutput(this, 'AppSecretName', { value: appSecret.secretName });
    new cdk.CfnOutput(this, 'MigrateFunctionName', { value: migrateFn.functionName });
  }
}
