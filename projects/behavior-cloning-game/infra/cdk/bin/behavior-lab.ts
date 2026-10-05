#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { BehaviorLabStack } from '../lib/behavior-lab-stack';

const app = new cdk.App();
new BehaviorLabStack(app, 'BehaviorLabPilot', {
  description: 'Low-idle-cost Behavior Lab pilot: CloudFront, API Gateway, Lambda, SQS, and S3.',
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION,
  },
});
