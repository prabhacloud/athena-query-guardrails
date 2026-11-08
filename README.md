# Practical Athena Query Guardrails

This repository accompanies the AWS Builder Center article
[Stop Expensive Athena Queries Before They Surprise You](https://builder.aws.com/content/3LoVCXHbdopCkoozgCDpAs69Wjd/stop-expensive-athena-queries-before-they-surprise-you).

It demonstrates four layers of protection:

1. deterministic client request tokens for retry safety;
2. result reuse for repeated queries;
3. a client-side soft scan budget that requests cancellation;
4. an Athena workgroup hard cutoff and a CloudWatch usage alarm.

The demo is safe by default. It only prints the request that it would send unless
`--execute` is supplied.

## Repository layout

```text
.
├── architecture.svg
├── article.md
├── examples/
│   └── daily_orders.sql
├── infra/
│   └── athena-guardrails.template.json
├── publishing-checklist.md
├── src/
│   └── athena_guardrails.py
├── tests/
    ├── test_athena_guardrails.py
    └── test_template.py
└── verification.md
```

## Run the tests

No third-party packages are required.

```bash
python3 -m unittest discover -s tests -v
```

## Preview a guarded Athena request

This command does not contact AWS:

```bash
python3 src/athena_guardrails.py \
  --query-file examples/daily_orders.sql \
  --workgroup analytics-guarded \
  --database analytics \
  --output-location s3://replace-me/athena-results/ \
  --soft-budget-mb 256 \
  --request-key daily-orders-2026-11-08
```

The output is the exact `StartQueryExecution` request that would be submitted.
Reuse the same request key only when recovering the same logical submission.
Omit it—or use a new key—for a new intentional run so Athena can evaluate
result reuse.

## Execute against AWS

Execution requires `boto3`, AWS credentials, an existing Athena workgroup, and
an S3 result location:

```bash
python3 -m pip install boto3

python3 src/athena_guardrails.py \
  --query-file examples/daily_orders.sql \
  --workgroup analytics-guarded \
  --database analytics \
  --output-location s3://your-results-bucket/athena-results/ \
  --soft-budget-mb 256 \
  --request-key daily-orders-2026-11-08 \
  --execute
```

The client-side soft budget is a best-effort cancellation threshold. The
workgroup's `BytesScannedCutoffPerQuery` is the authoritative hard limit.

## Optional infrastructure deployment

Review the generated change set before execution:

```bash
aws cloudformation deploy \
  --stack-name athena-query-guardrails \
  --template-file infra/athena-guardrails.template.json \
  --parameter-overrides \
    WorkGroupName=analytics-guarded \
    NotificationEmail=you@example.com \
  --no-execute-changeset
```

When you are ready, repeat the deployment without `--no-execute-changeset`.
The stack creates an encrypted results bucket, an Athena workgroup, an SNS
topic, and a CloudWatch alarm. Confirm the email subscription before expecting
notifications.

## Cleanup

The results bucket is retained deliberately. Empty and remove it only after
confirming that its query results are no longer needed.

```bash
aws cloudformation delete-stack --stack-name athena-query-guardrails
```

The repository was live-validated with a disposable stack in `us-east-2`.
After validation, the temporary catalog table, stack, workgroup, alarm, SNS
topic, all query-result object versions, and the retained results bucket were
deleted and verified absent. See `verification.md` for sanitized evidence.

