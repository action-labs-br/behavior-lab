import * as fs from 'node:fs';
import * as path from 'node:path';
import * as cdk from 'aws-cdk-lib';
import * as acm from 'aws-cdk-lib/aws-certificatemanager';
import * as apigwv2 from 'aws-cdk-lib/aws-apigatewayv2';
import * as authorizers from 'aws-cdk-lib/aws-apigatewayv2-authorizers';
import * as integrations from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as cognito from 'aws-cdk-lib/aws-cognito';
import * as ecrAssets from 'aws-cdk-lib/aws-ecr-assets';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as eventSources from 'aws-cdk-lib/aws-lambda-event-sources';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as s3deploy from 'aws-cdk-lib/aws-s3-deployment';
import * as sqs from 'aws-cdk-lib/aws-sqs';
import { Construct } from 'constructs';

const PROJECT_ROOT = path.resolve(__dirname, '..', '..', '..');
const FRONTEND_DIST = path.join(PROJECT_ROOT, 'web', 'dist');

/**
 * Behavior Lab pilot: CloudFront + private S3 for the SPA, API Gateway HTTP API
 * with a Cognito JWT authorizer in front of a FastAPI Lambda, and an SQS-driven
 * CPU Lambda that trains models. Everything is removed by `cdk destroy`.
 *
 * Context (cdk.json or `-c key=value`):
 *   customDomainName / customCertificateId  custom domain and the ACM certificate UUID
 *                         (the certificate must live in this account, in us-east-1)
 *   serviceEnabled        "false" removes API routes and the worker trigger (pause)
 *   apiRateLimit          API Gateway steady-state requests/s (default 5)
 *   apiBurstLimit         API Gateway burst requests (default 10)
 *   workerConcurrency     concurrent training invocations (default 2)
 */
export class BehaviorLabStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const ctx = (key: string): string | undefined => {
      const value = this.node.tryGetContext(key);
      return value === undefined || value === null || value === '' ? undefined : String(value);
    };
    const customDomainName = ctx('customDomainName');
    const customCertificateId = ctx('customCertificateId');
    const serviceEnabled = (ctx('serviceEnabled') ?? 'true').toLowerCase() !== 'false';
    const apiRateLimit = Number(ctx('apiRateLimit') ?? 5);
    const apiBurstLimit = Number(ctx('apiBurstLimit') ?? 10);
    const workerConcurrency = Number(ctx('workerConcurrency') ?? 2);

    if ((customDomainName === undefined) !== (customCertificateId === undefined)) {
      throw new Error('Set customDomainName and customCertificateId together, or neither.');
    }
    if (!fs.existsSync(path.join(FRONTEND_DIST, 'index.html'))) {
      throw new Error(`Frontend build not found at ${FRONTEND_DIST}. Run "npm --prefix web ci && npm --prefix web run build" first.`);
    }

    const artifactsBucket = new s3.Bucket(this, 'ArtifactsBucket', {
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      lifecycleRules: [{ abortIncompleteMultipartUploadAfter: cdk.Duration.days(7) }],
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    const frontendBucket = new s3.Bucket(this, 'FrontendBucket', {
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    const loggingBucket = new s3.Bucket(this, 'DistributionLoggingBucket', {
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      objectOwnership: s3.ObjectOwnership.OBJECT_WRITER,
      lifecycleRules: [{ expiration: cdk.Duration.days(30) }],
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    const deadLetterQueue = new sqs.Queue(this, 'TrainingDeadLetterQueue', {
      retentionPeriod: cdk.Duration.days(14),
      enforceSSL: true,
    });
    const trainingQueue = new sqs.Queue(this, 'TrainingQueue', {
      // Must exceed the worker timeout (900 s) so a run is not redelivered mid-training.
      visibilityTimeout: cdk.Duration.seconds(5400),
      enforceSSL: true,
      deadLetterQueue: { queue: deadLetterQueue, maxReceiveCount: 5 },
    });

    const userPool = new cognito.UserPool(this, 'UserPool', {
      featurePlan: cognito.FeaturePlan.LITE,
      selfSignUpEnabled: false,
      signInAliases: { email: true },
      autoVerify: { email: true },
      accountRecovery: cognito.AccountRecovery.EMAIL_ONLY,
      passwordPolicy: {
        minLength: 12,
        requireLowercase: true,
        requireUppercase: true,
        requireDigits: true,
        requireSymbols: true,
      },
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });
    const loginDomain = userPool.addDomain('LoginDomain', {
      cognitoDomain: { domainPrefix: `behavior-lab-${this.account}-${this.region}` },
      managedLoginVersion: cognito.ManagedLoginVersion.CLASSIC_HOSTED_UI,
    });
    const cognitoDomainName = `${loginDomain.domainName}.auth.${this.region}.amazoncognito.com`;

    // Both functions run the same CPU-only PyTorch image; only the handler differs.
    const imageCode = (cmd: string) =>
      lambda.DockerImageCode.fromImageAsset(PROJECT_ROOT, {
        file: path.join('infra', 'lambda.Dockerfile'),
        platform: ecrAssets.Platform.LINUX_AMD64,
        cmd: [cmd],
      });

    const apiLogs = new logs.LogGroup(this, 'ApiFunctionLogs', {
      retention: logs.RetentionDays.ONE_WEEK,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });
    const workerLogs = new logs.LogGroup(this, 'TrainingWorkerLogs', {
      retention: logs.RetentionDays.ONE_WEEK,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    const apiFunction = new lambda.DockerImageFunction(this, 'ApiFunction', {
      code: imageCode('web.api.lambda_handler.handler'),
      memorySize: 1024,
      timeout: cdk.Duration.seconds(28),
      logGroup: apiLogs,
      environment: {
        BEHAVIOR_LAB_S3_BUCKET: artifactsBucket.bucketName,
        BEHAVIOR_LAB_TRAINING_QUEUE_URL: trainingQueue.queueUrl,
        BEHAVIOR_LAB_SERVICE_ENABLED: String(serviceEnabled),
        BEHAVIOR_LAB_COGNITO_USER_POOL_ID: userPool.userPoolId,
        // Filled in below once the web client exists.
      },
    });
    artifactsBucket.grantReadWrite(apiFunction);
    trainingQueue.grantSendMessages(apiFunction);

    const trainingWorker = new lambda.DockerImageFunction(this, 'TrainingWorker', {
      code: imageCode('web.api.worker.handler'),
      memorySize: 4096,
      timeout: cdk.Duration.seconds(900),
      reservedConcurrentExecutions: workerConcurrency,
      logGroup: workerLogs,
      environment: {
        BEHAVIOR_LAB_S3_BUCKET: artifactsBucket.bucketName,
        BEHAVIOR_LAB_TRAINING_QUEUE_URL: trainingQueue.queueUrl,
      },
    });
    artifactsBucket.grantReadWrite(trainingWorker);
    if (serviceEnabled) {
      trainingWorker.addEventSource(
        new eventSources.SqsEventSource(trainingQueue, {
          batchSize: 1,
          maxConcurrency: Math.max(2, workerConcurrency),
          reportBatchItemFailures: true,
        }),
      );
    }

    const httpApi = new apigwv2.HttpApi(this, 'HttpApi', { apiName: 'behavior-lab-pilot' });
    const apiIntegration = new integrations.HttpLambdaIntegration('ApiIntegration', apiFunction);
    httpApi.addRoutes({ path: '/health', methods: [apigwv2.HttpMethod.GET], integration: apiIntegration });
    httpApi.addRoutes({
      path: '/api/v1/auth/config',
      methods: [apigwv2.HttpMethod.GET],
      integration: apiIntegration,
    });

    const apiAccessLogs = new logs.LogGroup(this, 'ApiAccessLogs', {
      retention: logs.RetentionDays.ONE_WEEK,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });
    const defaultStage = httpApi.defaultStage?.node.defaultChild as apigwv2.CfnStage;
    defaultStage.accessLogSettings = {
      destinationArn: apiAccessLogs.logGroupArn,
      format: JSON.stringify({
        requestId: '$context.requestId',
        routeKey: '$context.routeKey',
        status: '$context.status',
        sourceIp: '$context.identity.sourceIp',
        integrationError: '$context.integrationErrorMessage',
      }),
    };
    defaultStage.defaultRouteSettings = {
      throttlingRateLimit: apiRateLimit,
      throttlingBurstLimit: apiBurstLimit,
    };

    const apiOrigin = new origins.HttpOrigin(`${httpApi.apiId}.execute-api.${this.region}.${this.urlSuffix}`);
    const siteAliases = customDomainName ? [customDomainName] : undefined;
    // Built from the stack account so no account ID is committed to the repository.
    const certificate = customCertificateId
      ? acm.Certificate.fromCertificateArn(
          this,
          'SiteCertificate',
          this.formatArn({
            service: 'acm',
            region: 'us-east-1',
            resource: 'certificate',
            resourceName: customCertificateId,
            arnFormat: cdk.ArnFormat.SLASH_RESOURCE_NAME,
          }),
        )
      : undefined;

    const spaRewrite = new cloudfront.Function(this, 'SpaRewrite', {
      runtime: cloudfront.FunctionRuntime.JS_1_0,
      code: cloudfront.FunctionCode.fromInline(
        'function handler(event) { var request = event.request; ' +
          'if (request.uri.indexOf("/api/") === 0 || request.uri === "/health") return request; ' +
          'if (request.uri !== "/" && request.uri.indexOf(".") === -1) request.uri = "/index.html"; ' +
          'return request; }',
      ),
    });

    const apiBehavior: cloudfront.BehaviorOptions = {
      origin: apiOrigin,
      allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
      cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
      originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
      viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
      compress: true,
    };

    const distribution = new cloudfront.Distribution(this, 'Distribution', {
      defaultRootObject: 'index.html',
      domainNames: siteAliases,
      certificate,
      minimumProtocolVersion: cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
      httpVersion: cloudfront.HttpVersion.HTTP2,
      enableIpv6: true,
      enableLogging: true,
      logBucket: loggingBucket,
      defaultBehavior: {
        origin: origins.S3BucketOrigin.withOriginAccessControl(frontendBucket),
        cachePolicy: cloudfront.CachePolicy.CACHING_OPTIMIZED,
        responseHeadersPolicy: cloudfront.ResponseHeadersPolicy.SECURITY_HEADERS,
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        compress: true,
        functionAssociations: [
          { function: spaRewrite, eventType: cloudfront.FunctionEventType.VIEWER_REQUEST },
        ],
      },
      additionalBehaviors: {
        '/api/*': apiBehavior,
        '/health': apiBehavior,
      },
    });

    const siteUrls = [`https://${distribution.distributionDomainName}/`];
    if (customDomainName) siteUrls.push(`https://${customDomainName}/`);

    const webClient = userPool.addClient('WebClient', {
      generateSecret: false,
      preventUserExistenceErrors: true,
      enableTokenRevocation: true,
      supportedIdentityProviders: [cognito.UserPoolClientIdentityProvider.COGNITO],
      oAuth: {
        flows: { authorizationCodeGrant: true },
        scopes: [cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL],
        callbackUrls: siteUrls,
        logoutUrls: siteUrls,
      },
      accessTokenValidity: cdk.Duration.minutes(15),
      idTokenValidity: cdk.Duration.minutes(15),
      refreshTokenValidity: cdk.Duration.minutes(10080),
    });
    apiFunction.addEnvironment('BEHAVIOR_LAB_COGNITO_CLIENT_ID', webClient.userPoolClientId);
    apiFunction.addEnvironment('BEHAVIOR_LAB_COGNITO_DOMAIN', cognitoDomainName);

    if (serviceEnabled) {
      const jwtAuthorizer = new authorizers.HttpUserPoolAuthorizer('CognitoJwtAuthorizer', userPool, {
        userPoolClients: [webClient],
      });
      httpApi.addRoutes({ path: '/', methods: [apigwv2.HttpMethod.ANY], integration: apiIntegration, authorizer: jwtAuthorizer });
      httpApi.addRoutes({ path: '/{proxy+}', methods: [apigwv2.HttpMethod.ANY], integration: apiIntegration, authorizer: jwtAuthorizer });
    }

    new s3deploy.BucketDeployment(this, 'DeployFrontend', {
      sources: [s3deploy.Source.asset(FRONTEND_DIST)],
      destinationBucket: frontendBucket,
      distribution,
      distributionPaths: ['/index.html', '/assets/*'],
      prune: true,
      waitForDistributionInvalidation: true,
    });

    new cdk.CfnOutput(this, 'FrontendUrl', {
      value: `https://${distribution.distributionDomainName}`,
      description: 'Behavior Lab pilot URL',
    });
    if (customDomainName) {
      new cdk.CfnOutput(this, 'CustomDomainUrl', {
        value: `https://${customDomainName}`,
        description: 'Custom domain for the Behavior Lab pilot',
      });
      new cdk.CfnOutput(this, 'CloudFrontDomainForDns', {
        value: distribution.distributionDomainName,
        description: 'Create a DNS-only CNAME from the custom domain to this value',
      });
    }
    new cdk.CfnOutput(this, 'ArtifactsBucketName', {
      value: artifactsBucket.bucketName,
      description: 'Private S3 bucket holding datasets and model artifacts (deleted on destroy)',
    });
    new cdk.CfnOutput(this, 'CognitoUserPoolId', {
      value: userPool.userPoolId,
      description: 'Create invited pilot users in this Cognito user pool',
    });
    new cdk.CfnOutput(this, 'CognitoWebClientId', {
      value: webClient.userPoolClientId,
      description: 'Public SPA client ID; it contains no client secret',
    });
    new cdk.CfnOutput(this, 'CognitoLoginDomain', { value: cognitoDomainName });
  }
}
