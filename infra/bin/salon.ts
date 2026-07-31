#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { SalonApiStack } from '../lib/salon-api-stack';

const app = new cdk.App();

new SalonApiStack(app, 'SalonApi', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    // architecture.md pins the project to ca-central-1.
    region: process.env.CDK_DEFAULT_REGION ?? 'ca-central-1',
  },
});
