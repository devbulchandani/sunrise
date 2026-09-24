---
name: sunrise-bedrock-integration
description: Integrate, configure, troubleshoot, or migrate Amazon Bedrock model calls in Sunrise or a related application. Use for Bedrock Runtime, Bedrock Mantle, model selection, credentials, deployment, and cost-aware inference changes.
---

# Sunrise Bedrock integration

Use this skill when implementing Bedrock in Sunrise or carrying the project's Bedrock setup into another application. Read current AWS documentation for the exact model, endpoint, Region, API, authentication, request schema, quotas, and price because these change. Use the AWS `amazon-bedrock` skill and language-specific AWS SDK skill when available. For Python boto3 work, read the AWS SDK Python skill and the Bedrock model-invocation reference before writing code.

## Understand the integration choice

- Distinguish **Bedrock Runtime** from **Bedrock Mantle**. Runtime uses APIs such as Converse/InvokeModel and normally the AWS credential chain or a supported Bedrock bearer key. Mantle provides compatible APIs and has its own endpoint, model IDs, auth expectations, and request compatibility. Confirm each combination from current AWS docs; do not mix identifiers or payloads across APIs.
- In Sunrise, `LLM_PROVIDER=openai` selects the OpenAI-compatible HTTP client; a Mantle configuration also sets `LLM_MODEL`, `LLM_BASE_URL`, and `LLM_API_KEY`. `LLM_PROVIDER=bedrock` selects boto3 Bedrock Runtime Converse and should use the EC2 instance role in production. Do not confuse a Mantle model identifier with a Runtime foundation-model ID.
- Existing production historically used Mantle at `https://bedrock-mantle.us-east-1.api.aws/v1` with `openai.gpt-oss-20b`. Verify current availability and price in the user's selected AWS Region before reusing this context. Do not assume `us-east-1` is valid for another AWS project.
- Never ask users to paste secrets into chat. Read secret names/configuration when needed, never print values, and keep provider credentials out of source control, frontend builds, logs, and command output. In AWS production prefer Secrets Manager and a workload role scoped to the needed secret; prefer temporary AWS credentials over static keys when supported by the chosen API.

## Project workflow

1. Inspect the existing LLM abstraction, call sites, provider selection, schemas, retries, deployment configuration, and secret source before changing architecture. Preserve the application's structured-output contract.
2. Establish the AWS project and selected Region from project guidance and local AWS configuration. Respect project-specific Region and service-access constraints. Verify model/API availability and account access before changing production configuration.
3. Read current official AWS documentation for the exact API and model. Set output-token limits explicitly, use bounded retries for transient errors, handle malformed/empty outputs, redact credentials, and avoid logging prompts or secrets unnecessarily.
4. Keep inference separate from consequential actions. Validate structured output against application schemas and deterministic policy. Generated text must never grant permissions, alter infrastructure, spend money, or place financial orders without independent authorization and server-side checks.
5. Estimate cost from observed input/output tokens when possible; otherwise state token-volume assumptions and use current regional prices. Separate Bedrock inference from compute, storage, and other AWS costs.
6. Validate configuration, invocation, failure handling, tests, and deployment health at the level requested. Do not deploy or rotate production credentials without authorization for that external change.

## Project-specific lessons

- A successful dashboard score alone does not prove a model produced it. Verify inference with an invocation trace or controlled fresh analysis.
- Do not silently switch between Mantle bearer-key authentication and Runtime IAM-role authentication. Move endpoint, model ID, credentials, SDK path, and payload format together.
- Production secrets have been kept in AWS Secrets Manager. Never export, echo, or commit secret values while inspecting configuration.

## Primary references

- [Amazon Bedrock APIs](https://docs.aws.amazon.com/bedrock/latest/userguide/apis.html)
- [Bedrock endpoints](https://docs.aws.amazon.com/bedrock/latest/userguide/endpoints.html)
- [Bedrock supported models](https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html)
- [Bedrock security](https://docs.aws.amazon.com/bedrock/latest/userguide/security.html)
- [Bedrock pricing](https://aws.amazon.com/bedrock/pricing/)
- [AWS Secrets Manager access control](https://docs.aws.amazon.com/secretsmanager/latest/userguide/auth-and-access_overview.html)
