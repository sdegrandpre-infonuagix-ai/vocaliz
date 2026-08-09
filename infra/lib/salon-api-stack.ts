import * as path from 'path';
import * as cdk from 'aws-cdk-lib';
import * as apigw from 'aws-cdk-lib/aws-apigatewayv2';
import * as integrations from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import * as acm from 'aws-cdk-lib/aws-certificatemanager';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as events from 'aws-cdk-lib/aws-events';
import * as eventTargets from 'aws-cdk-lib/aws-events-targets';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as route53 from 'aws-cdk-lib/aws-route53';
import * as targets from 'aws-cdk-lib/aws-route53-targets';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import * as servicediscovery from 'aws-cdk-lib/aws-servicediscovery';
import { Construct } from 'constructs';

const API_DIR = path.join(__dirname, '..', '..', 'api');
const ORCHESTRATOR_DIR = path.join(__dirname, '..', '..', 'orchestrator');

// Where the orchestrator answers, inside the VPC and nowhere else. A name rather than an
// address, and a name this file chooses rather than one AWS hands out — the API writes it
// into `salons.orchestrator_url`, where it outlives every task that ever serves it.
//
// `.internal` is resolvable only from within the VPC. The orchestrator holds the text of
// every live conversation, so it has no business being reachable from the internet: there
// is no listener, no certificate and no path to it from outside.
const ORCHESTRATOR_NAMESPACE = 'vocaliz.internal';
const ORCHESTRATOR_SERVICE = 'orchestrator';
const ORCHESTRATOR_PORT = 8080;
const ORCHESTRATOR_URL =
  `http://${ORCHESTRATOR_SERVICE}.${ORCHESTRATOR_NAMESPACE}:${ORCHESTRATOR_PORT}`;

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
      // 0.5, the lowest floor above zero. This used to be 0, and the reasoning behind
      // that is worth keeping because it was right at the time: scaling to zero costs
      // storage alone while nobody is talking, against roughly 44 USD a month to hold
      // a floor of 0.5 ACU around the clock. For a database "only touched during test
      // salons", paying to keep it warm bought nothing.
      //
      // What changed is what the database is for. The price of zero is a resume of
      // about fifteen seconds on the first request after a pause, and that first
      // request is now the opening of a live voice conversation. Fifteen seconds of
      // dead air while three people wait is not a slow page load — it is the product
      // failing in the one moment it has to work.
      //
      // Two more things now depend on the database being awake continuously rather
      // than on demand: the journal is read and written on every turn, and the balance
      // is debited every five seconds. Neither tolerates a cold start mid-conversation.
      serverlessV2MinCapacity: 0.5,
      serverlessV2MaxCapacity: 2,
      // No serverlessV2AutoPauseDuration: auto-pause only applies to a floor of 0, and
      // there is nothing left to pause.
      defaultDatabaseName: 'salon',
      credentials: rds.Credentials.fromGeneratedSecret('salon'),
      storageEncrypted: true,

      // This cluster stopped being a test environment. It now holds transcribed
      // conversations kept for a year, participant contact details and approximate
      // locations, and ad_broadcasts rows that are an advertiser's only evidence that
      // their ad ran. The three settings below were right for something torn down
      // between test rounds and are wrong for that.
      //
      // RETAIN rather than DESTROY: deleting the stack must not delete the data. The
      // cluster survives its stack and is removed deliberately or not at all.
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      // Blocks deletion at the RDS layer as well, so a hand-typed `aws rds
      // delete-db-cluster` fails too. RETAIN alone only binds CloudFormation.
      deletionProtection: true,
      // Thirty days, not the one-day default. One day means an accidental truncate
      // discovered on a Tuesday about work done on Sunday is unrecoverable — and the
      // retention obligation on these journals is a year, which a 24-hour restore
      // window cannot honour.
      //
      // Thirty rather than fourteen: a month covers the interval at which anything is
      // actually reconciled here — the advertiser invoicing run, the participant
      // report, a monthly look at the books. A corruption found while closing the
      // month has to be restorable from within that month, or the discovery is
      // useless. Aurora allows up to 35; the cost is backup storage beyond the
      // cluster's own size, which is negligible against a cluster that scales to zero.
      backup: { retention: cdk.Duration.days(30) },
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
      // Where the orchestrator that holds a Salon's text can be reached.
      //
      // Not a load balancer address distributing each request afresh: a Salon is stateful,
      // and every agent of one Salon must reach the instance that holds it. See the service
      // below, which runs exactly one task and replaces it rather than doubling it.
      ORCHESTRATOR_BASE_URL: ORCHESTRATOR_URL,
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

    // The per-salon cap used to be evaluated only when a heartbeat arrived, which meant
    // it was not evaluated at all in the most ordinary failure: a host closes their laptop,
    // or the agent worker dies. The salon then stayed active for good, leaking an open
    // salon, a reserved telephone code and a span of metered time never settled.
    //
    // Every minute, not every five. The interval is not a tidiness setting: a Salon past its
    // cap still has an agent in it, and that agent is a live connection to the realtime model
    // — billed by xAI for as long as it lasts. Five minutes meant an abandoned Salon could
    // burn half its own length again before anything noticed.
    //
    // The extra cost is on the side that is nearly free: 1440 invocations a day instead of
    // 288, of a Lambda that usually finds nothing and returns in milliseconds. Trading Lambda
    // invocations for realtime-model minutes is the right way round by a wide margin.
    new events.Rule(this, 'SweepExpiredSalons', {
      schedule: events.Schedule.rate(cdk.Duration.minutes(1)),
      description: 'Close salons past the per-salon cap, regardless of heartbeats',
      targets: [
        new eventTargets.LambdaFunction(migrateFn, {
          event: events.RuleTargetInput.fromObject({ action: 'sweep_salons' }),
        }),
      ],
    });

    // Is xAI answering? Every minute, because the failure is invisible from inside Vocaliz.
    //
    // A spent balance, a revoked key and a suspended team all produce the same symptom: the
    // agent joins a Salon, the room looks normal, and nobody is ever answered. Nothing in the
    // API errors, so nothing tells anybody. xAI publishes no balance endpoint — /v1/billing,
    // /v1/credits and /v1/usage all answer 404 — so this probes rather than predicts.
    //
    // One email per transition, not per probe. The state lives in service_health precisely so
    // a bad night sends one message instead of fourteen hundred.
    new events.Rule(this, 'CheckXaiHealth', {
      schedule: events.Schedule.rate(cdk.Duration.minutes(1)),
      description: 'Probe xAI and email the administrator when its answer changes',
      targets: [
        new eventTargets.LambdaFunction(migrateFn, {
          event: events.RuleTargetInput.fromObject({ action: 'check_xai' }),
        }),
      ],
    });

    // The participant table, mailed to the administrator — off, on request.
    //
    // It was hourly, on the reasoning that a report is a picture of the whole and an empty
    // hour is still information. In practice twenty-four mails a day about a platform with
    // twenty accounts is noise, and noise is what stops a report being read. It is now pulled
    // rather than pushed: /report shows the same rows on demand, behind the same code.
    //
    // Kept rather than deleted, and disabled here rather than only in the console. The rule
    // was switched off by hand the moment it was asked for; without this line the next deploy
    // would quietly turn it back on, which is the worst possible way for a setting to return.
    // Flip `enabled` to restore the schedule.
    new events.Rule(this, 'ParticipantReport', {
      enabled: false,
      schedule: events.Schedule.rate(cdk.Duration.hours(1)),
      description: 'Mail the participant table to the administrator',
      targets: [
        new eventTargets.LambdaFunction(migrateFn, {
          event: events.RuleTargetInput.fromObject({
            action: 'participant_report',
            recipient: 's.degrandpre@vocaliz.net',
          }),
        }),
      ],
    });

    // Advertising is invoiced daily rather than per broadcast. Stripe takes roughly 2.9% plus
    // thirty cents per transaction, so charging twenty-five cents individually would lose
    // money on every one — the batch is what makes the pricing viable at all.
    //
    // Daily rather than monthly: a failure is noticed within a day instead of at month end,
    // and the run is idempotent, so an extra pass that finds nothing costs one invocation.
    new events.Rule(this, 'InvoiceAdvertisers', {
      schedule: events.Schedule.rate(cdk.Duration.days(1)),
      description: 'Invoice advertisers for broadcasts not yet billed',
      targets: [
        new eventTargets.LambdaFunction(migrateFn, {
          event: events.RuleTargetInput.fromObject({ action: 'invoice_advertisers' }),
        }),
      ],
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
    //
    // Granted to the scheduled function as well as the API. The hourly participant report is
    // sent from there, and this permission living only on apiFn would have made it fail
    // silently — the report catches its own errors, so the only symptom would have been an
    // email that never arrived.
    for (const fn of [apiFn, migrateFn]) {
      fn.addToRolePolicy(
        new iam.PolicyStatement({
          actions: ['ses:SendEmail'],
          resources: [`arn:aws:ses:${this.region}:${this.account}:identity/*`],
        }),
      );
    }

    // Live captions: each turn of speech is rendered into whatever language the other
    // participants are reading. Amazon Translate has no resource to scope to — a
    // translation is a call, not an object — so '*' is the only grant it accepts.
    // TranslateText alone: nothing here creates terminologies or batch jobs.
    apiFn.addToRolePolicy(
      new iam.PolicyStatement({
        actions: [
          'translate:TranslateText',
          // Translate calls Comprehend under the hood whenever the source language is 'auto',
          // which is every caption whose language the model did not report and every corpus
          // search. Without this the call fails with an AccessDenied naming a service nobody
          // configured — and translation-by-detection was silently broken in production.
          'comprehend:DetectDominantLanguage',
        ],
        resources: ['*'],
      }),
    );

    // ── The orchestrator ──────────────────────────────────────────────────────
    //
    // The service that holds a Salon's text: the journal, every reader's position, who has
    // been introduced to whom. It is a long-running process rather than a Lambda because a
    // conversation is long-running — the state lives in memory between requests, and a
    // function that forgot it after each one would have to re-read the journal on every turn
    // of speech.
    //
    // Fargate, so there is no instance to patch. The cluster itself costs nothing; what is
    // paid for is the one task.

    const cluster = new ecs.Cluster(this, 'OrchestratorCluster', {
      clusterName: 'vocaliz-orchestrator',
      vpc,
      // The private DNS namespace the service registers itself in. Cloud Map rather than a
      // load balancer, and the trade is the same one the NAT instance above makes: an
      // internal ALB is roughly 16 USD a month to put a stable front on a single task, which
      // is most of what this whole stack costs to run. Cloud Map is about fifty cents.
      //
      // What is given up is the seconds after a task is replaced, during which the DNS
      // record still points at a task that has gone. That is survivable precisely because
      // the API treats an unreachable orchestrator as non-fatal: a Salon opened in that
      // window opens without translation instead of failing to open. Move to an ALB when
      // that window costs more than the 16 USD it saves.
      defaultCloudMapNamespace: {
        name: ORCHESTRATOR_NAMESPACE,
        type: servicediscovery.NamespaceType.DNS_PRIVATE,
        useForServiceConnect: false,
      },
    });

    const orchestratorTask = new ecs.FargateTaskDefinition(this, 'OrchestratorTask', {
      family: 'vocaliz-orchestrator',
      cpu: 512,
      memoryLimitMiB: 1024,
    });

    orchestratorTask.addContainer('orchestrator', {
      image: ecs.ContainerImage.fromAsset(ORCHESTRATOR_DIR),
      essential: true,
      portMappings: [{ containerPort: ORCHESTRATOR_PORT, protocol: ecs.Protocol.TCP }],
      environment: {
        AWS_REGION: this.region,
        ENVIRONMENT: 'production',
        LOG_LEVEL: 'INFO',
        PORT: String(ORCHESTRATOR_PORT),
        // The same secret the API reads, not a second copy. Two secrets holding the same
        // LiveKit credentials is two things to rotate and one to forget.
        ORCHESTRATOR_SECRET_ARN: appSecret.secretArn,
        // Aurora's own secret, rotated by AWS. The orchestrator assembles the URL from it at
        // startup: a static one would work until the first rotation and then fail as an
        // authentication error on a database that was fine yesterday.
        DB_SECRET_ARN: db.secret!.secretArn,
      },
      logging: ecs.LogDrivers.awsLogs({
        streamPrefix: 'orchestrator',
        logGroup: new logs.LogGroup(this, 'OrchestratorLogs', {
          logGroupName: '/ecs/vocaliz-orchestrator',
          retention: logs.RetentionDays.TWO_WEEKS,
          removalPolicy: cdk.RemovalPolicy.DESTROY,
        }),
      }),
      healthCheck: {
        // Liveness, which answers while draining too — a task finishing the Salons it holds
        // is not wedged, and killing it is exactly what the drain exists to avoid.
        command: [
          'CMD-SHELL',
          `python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${ORCHESTRATOR_PORT}/health', timeout=3)" || exit 1`,
        ],
        interval: cdk.Duration.seconds(30),
        timeout: cdk.Duration.seconds(5),
        retries: 3,
        startPeriod: cdk.Duration.seconds(20),
      },
      // Above the orchestrator's own 90-second drain, so the wait finishes on its own terms
      // rather than being cut short by SIGKILL. 120 s is Fargate's ceiling, and that ceiling
      // is what the drain timeout was chosen under.
      stopTimeout: cdk.Duration.seconds(120),
    });

    const orchestrator = new ecs.FargateService(this, 'OrchestratorService', {
      serviceName: 'vocaliz-orchestrator',
      cluster,
      taskDefinition: orchestratorTask,
      // Private subnets with egress: it calls LiveKit to provision rooms, and nothing calls
      // it from outside the VPC.
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      assignPublicIp: false,
      desiredCount: 1,

      // One task, and one task during a deploy as well. This is the setting that matters
      // most in this block, and the default would have been wrong.
      //
      // ECS defaults to 100/200, which starts the new task before stopping the old — briefly
      // running two. Two orchestrators answering for the same Salon is precisely the failure
      // `salons.orchestrator_url` exists to prevent: the second holds an empty journal, and a
      // participant routed to it would be served a conversation in which nobody has spoken.
      //
      // The price is a gap of roughly a minute during each deploy, in which a Salon opens
      // without translation. That is the right way round: a visible degradation for a minute,
      // rather than a silent wrong answer.
      minHealthyPercent: 0,
      maxHealthyPercent: 100,

      cloudMapOptions: {
        name: ORCHESTRATOR_SERVICE,
        // Ten seconds rather than the default minute. This is how long the record can keep
        // pointing at a task that has gone, so it is the length of the window the paragraph
        // above describes.
        dnsTtl: cdk.Duration.seconds(10),
      },
      // Long enough to start, connect to Aurora and read two secrets before the load
      // balancer-less health check begins counting failures against it.
      healthCheckGracePeriod: cdk.Duration.seconds(60),
      // Fargate only, and a recent platform version so `stopTimeout` is honoured.
      circuitBreaker: { rollback: true },
    });

    appSecret.grantRead(orchestratorTask.taskRole);
    db.secret!.grantRead(orchestratorTask.taskRole);
    db.connections.allowDefaultPortFrom(orchestrator, 'The orchestrator reads the journal');

    // The API opens the conversation by telling this service which Salon it holds. Nothing
    // else may reach it — not the internet, which has no route here at all, and not the
    // agents, which talk to it through the API's own network path.
    orchestrator.connections.allowFrom(
      apiFn,
      ec2.Port.tcp(ORCHESTRATOR_PORT),
      'The API hands a Salon to the orchestrator at creation',
    );

    // And the scheduled function, which carries the `probe_orchestrator` action. Left out at
    // first, and the probe answered "unreachable" — correctly, since it had no route. Worth
    // keeping as a separate grant rather than folding both into one loop: these are two
    // different reasons to be allowed through, and the day the probe is removed this rule
    // should go with it.
    orchestrator.connections.allowFrom(
      migrateFn,
      ec2.Port.tcp(ORCHESTRATOR_PORT),
      'The maintenance function probes the link the API depends on',
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

    // ── The bare domain ───────────────────────────────────────────────────────
    // vocaliz.net serves the same API as app.vocaliz.net. Somebody told "call Vocaliz" types
    // the name they were given, not a subdomain, and a browser answering nothing at the apex
    // is indistinguishable from a product that does not exist.
    //
    // A second certificate rather than a subject alternative name on the first. Adding a SAN
    // replaces the certificate, and the working domain depends on it — a rebuild of something
    // that is serving traffic, to add something that is not, is the wrong trade.
    const apexCertificate = new acm.Certificate(this, 'ApexCertificate', {
      domainName: DOMAIN_NAME,
      validation: acm.CertificateValidation.fromDns(zone),
    });

    const apexDomain = new apigw.DomainName(this, 'ApexDomain', {
      domainName: DOMAIN_NAME,
      certificate: apexCertificate,
    });

    // Mapped explicitly: defaultDomainMapping above takes one domain, and a second one has to
    // be attached to the same API rather than to a second API that would drift from it.
    new apigw.ApiMapping(this, 'ApexMapping', {
      api: httpApi,
      domainName: apexDomain,
    });

    // No recordName, so this is the zone apex. A CNAME is not allowed there at all; the alias
    // is what makes the bare domain reachable, which is the reason the app record is an A
    // record too.
    new route53.ARecord(this, 'ApexAliasRecord', {
      zone,
      target: route53.RecordTarget.fromAlias(
        new targets.ApiGatewayv2DomainProperties(
          apexDomain.regionalDomainName,
          apexDomain.regionalHostedZoneId,
        ),
      ),
    });

    new cdk.CfnOutput(this, 'SiteUrl', { value: `https://${DOMAIN_NAME}` });
    new cdk.CfnOutput(this, 'AppUrl', { value: `https://${APP_DOMAIN}` });
    new cdk.CfnOutput(this, 'ApiUrl', { value: httpApi.apiEndpoint });
    new cdk.CfnOutput(this, 'DbEndpoint', { value: db.clusterEndpoint.hostname });
    new cdk.CfnOutput(this, 'AppSecretName', { value: appSecret.secretName });
    new cdk.CfnOutput(this, 'OrchestratorUrl', { value: ORCHESTRATOR_URL });
    new cdk.CfnOutput(this, 'MigrateFunctionName', { value: migrateFn.functionName });
  }
}
