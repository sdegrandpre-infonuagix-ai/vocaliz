import * as path from 'path';
import * as cdk from 'aws-cdk-lib';
import * as apigw from 'aws-cdk-lib/aws-apigatewayv2';
import * as integrations from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import * as acm from 'aws-cdk-lib/aws-certificatemanager';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as route53 from 'aws-cdk-lib/aws-route53';
import * as targets from 'aws-cdk-lib/aws-route53-targets';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import { Construct } from 'constructs';

const API_DIR = path.join(__dirname, '..', '..', 'api');

// The zone is referenced, never created here. Creating it in this stack would tie its
// lifetime to the stack: a teardown would delete the zone, AWS would hand out different
// name servers on the next create, and the delegation would have to be set up again at
// the registrar by hand. Registered at GoDaddy, delegated to these Route 53 servers.
const DOMAIN_NAME = 'vocaliz.net';
const HOSTED_ZONE_ID = 'Z0537891WMC5L13KI88P';

// The application answers on a subdomain, leaving the apex free for a marketing site
// later. Guest join links are built from this, so it ends up printed in emails.
const APP_DOMAIN = `app.${DOMAIN_NAME}`;

/**
 * Salon REST API: Aurora Serverless v2 + a container-image Lambda behind an HTTP API,
 * per architecture.md (Lambda + API Gateway for the API, Aurora for persistence).
 *
 * The Lambda sits in private subnets with egress because it calls LiveKit, Stripe and
 * SNS — hence the single NAT, which is the main fixed cost of this stack and is served by
 * an instance rather than a managed gateway (see the comment on natProvider below).
 */
export class SalonApiStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // A NAT instance rather than a managed gateway. The gateway was this stack's largest
    // fixed cost — roughly 33 USD a month before data charges — and it exists only so the
    // Lambda can reach LiveKit, Stripe and SES. A t4g.nano does the same work for about a
    // tenth of that.
    //
    // What is traded away is availability, and the trade is real: a managed gateway is
    // redundant and self-healing, this is one instance in one availability zone. If it
    // dies, every outbound call from the API fails until it is replaced — no rooms, no
    // invitations, no billing. That is acceptable while Salon is being tested; switch back
    // to NatProvider.gateway() once an outage costs more than the 30 USD it saves.
    const natProvider = ec2.NatProvider.instanceV2({
      instanceType: ec2.InstanceType.of(ec2.InstanceClass.T4G, ec2.InstanceSize.NANO),
      // Not the default. NatInstanceProviderV2 defaults to INBOUND_AND_OUTBOUND, which
      // attaches a security group allowing every port from 0.0.0.0/0 — the whole internet
      // reaching a host that only ever needs to serve traffic already inside the VPC.
      defaultAllowedTraffic: ec2.NatTrafficDirection.OUTBOUND_ONLY,
    });

    const vpc = new ec2.Vpc(this, 'Vpc', {
      maxAzs: 2,
      natGateways: 1,
      natGatewayProvider: natProvider,
      subnetConfiguration: [
        { name: 'public', subnetType: ec2.SubnetType.PUBLIC, cidrMask: 24 },
        { name: 'app', subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS, cidrMask: 24 },
        { name: 'data', subnetType: ec2.SubnetType.PRIVATE_ISOLATED, cidrMask: 24 },
      ],
    });

    // OUTBOUND_ONLY leaves the instance with no inbound rule whatsoever, which would also
    // turn away the private subnets it exists to serve. This puts back exactly one thing:
    // traffic that is already inside the VPC. Written after the Vpc because the CIDR is
    // only known once it is constructed.
    natProvider.connections.allowFrom(
      ec2.Peer.ipv4(vpc.vpcCidrBlock),
      ec2.Port.allTraffic(),
      'Egress for the private subnets routed through this NAT instance',
    );

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
      // 0, not 0.5: a floor of 0.5 ACU bills around the clock for a database that is
      // only touched during test sessions — roughly 50 USD a month to keep an idle
      // cluster warm. PostgreSQL 16.14 supports scaling to zero, so it now costs
      // storage alone while nobody is talking.
      //
      // The price is a resume of about fifteen seconds on the first request after a
      // pause. That fits inside the API Lambda's 29 s ceiling below, but it is real:
      // the first call after an idle night will be visibly slow.
      serverlessV2MinCapacity: 0,
      serverlessV2MaxCapacity: 2,
      // Ten minutes rather than the five-minute default: sessions come in bursts, and
      // this keeps consecutive tests from each paying for a resume, while still leaving
      // an idle evening at zero.
      serverlessV2AutoPauseDuration: cdk.Duration.minutes(10),
      defaultDatabaseName: 'salon',
      credentials: rds.Credentials.fromGeneratedSecret('salon'),
      storageEncrypted: true,
      // Test environment: the cluster is meant to be torn down between test rounds.
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // ── Application secrets ───────────────────────────────────────────────────
    // JWT_SECRET is generated here so it never exists in the repo. The other values
    // start empty and are filled in after deploy; config.py skips empty entries, so a
    // half-filled secret fails loudly rather than silently.
    //
    // DO NOT edit generateSecretString to add or rename keys: any change to it makes
    // CloudFormation regenerate the whole secret, silently wiping every hand-filled
    // value (this cost us the LiveKit credentials once already). config.py merges
    // whatever keys the secret happens to hold, so new keys can simply be added with
    // `aws secretsmanager put-secret-value` — they do not belong in this template.
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
      // Real OTP delivery through SES. Set back to 'true' to log the code to
      // CloudWatch instead — useful when the recipient address is not a verified SES
      // identity, which the SES sandbox still requires.
      DEV_MODE: 'false',
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
    // Still needed for guest invitation and install-link texts, not for sign-in.
    apiFn.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ['sns:Publish'],
        resources: ['*'],
        conditions: { Null: { 'sns:TopicArn': 'true' } },
      }),
    );

    // OTP emails go out through SES. Scoped to identities in this account/region;
    // the sender itself must be verified in the SES console before DEV_MODE is off.
    apiFn.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ['ses:SendEmail'],
        resources: [`arn:aws:ses:${this.region}:${this.account}:identity/*`],
      }),
    );

    // Live captions: each turn of speech is rendered into whatever language the other
    // participants are reading. Amazon Translate has no resource to scope to — a
    // translation is a call, not an object — so '*' is the only grant it accepts.
    // TranslateText alone: nothing here creates terminologies or batch jobs.
    apiFn.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ['translate:TranslateText'],
        resources: ['*'],
      }),
    );

    // ── Custom domain ─────────────────────────────────────────────────────────
    const zone = route53.HostedZone.fromHostedZoneAttributes(this, 'Zone', {
      hostedZoneId: HOSTED_ZONE_ID,
      zoneName: DOMAIN_NAME,
    });

    // Regional, in this stack's region, because an HTTP API custom domain terminates TLS
    // regionally — unlike CloudFront, which would require the certificate in us-east-1.
    //
    // DNS validation against the zone above: ACM writes the proof record itself and
    // renews the same way, so nothing has to be maintained by hand at the registrar. This
    // only works once the domain is actually delegated to Route 53 — otherwise the
    // certificate sits in PENDING_VALIDATION and the deployment waits on it for hours.
    const certificate = new acm.Certificate(this, 'AppCertificate', {
      domainName: APP_DOMAIN,
      validation: acm.CertificateValidation.fromDns(zone),
    });

    const domain = new apigw.DomainName(this, 'AppDomain', {
      domainName: APP_DOMAIN,
      certificate,
    });

    // ── HTTP API ──────────────────────────────────────────────────────────────
    const httpApi = new apigw.HttpApi(this, 'HttpApi', {
      apiName: 'salon-api',
      defaultIntegration: new integrations.HttpLambdaIntegration('ApiIntegration', apiFn),
      defaultDomainMapping: { domainName: domain },
    });

    // An A record, not a CNAME: API Gateway's regional endpoint is reached through an
    // alias, which Route 53 resolves without an extra lookup and which would also work at
    // a zone apex if the application ever moves there.
    new route53.ARecord(this, 'AppAliasRecord', {
      zone,
      recordName: 'app',
      target: route53.RecordTarget.fromAlias(
        new targets.ApiGatewayv2DomainProperties(
          domain.regionalDomainName,
          domain.regionalHostedZoneId,
        ),
      ),
    });

    new cdk.CfnOutput(this, 'AppUrl', { value: `https://${APP_DOMAIN}` });
    new cdk.CfnOutput(this, 'ApiUrl', { value: httpApi.apiEndpoint });
    new cdk.CfnOutput(this, 'DbEndpoint', { value: db.clusterEndpoint.hostname });
    new cdk.CfnOutput(this, 'AppSecretName', { value: appSecret.secretName });
    new cdk.CfnOutput(this, 'MigrateFunctionName', { value: migrateFn.functionName });
  }
}
