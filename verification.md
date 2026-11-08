# Verification record

Date: 2026-11-08 (Asia/Kolkata)

## Local validation

The following command completed successfully:

```bash
python3 -m unittest discover -s tests -v
```

Result:

```text
Ran 12 tests in 0.001s
OK
```

The test suite covers:

- stable and context-sensitive Athena client request tokens;
- separate request identities for later intentional executions;
- result reuse request configuration and returned evidence;
- one-time cancellation after a soft scan threshold;
- terminal state and timeout behavior;
- enforced Athena workgroup configuration;
- encrypted, private, retained S3 query results;
- the `AWS/Athena` `ProcessedBytes` workgroup alarm;
- absence of hard-coded AWS account identifiers.

Additional checks completed successfully:

```bash
python3 -m py_compile \
  src/athena_guardrails.py \
  tests/test_athena_guardrails.py \
  tests/test_template.py

xmllint --noout architecture.svg

python3 -m json.tool \
  infra/athena-guardrails.template.json
```

The CLI dry run produced a valid request plan without contacting AWS:

```bash
python3 src/athena_guardrails.py \
  --query-file examples/daily_orders.sql \
  --workgroup analytics-guarded \
  --database analytics \
  --output-location s3://replace-me/athena-results/ \
  --soft-budget-mb 256
```

## Live AWS validation

The demonstration was validated on 2026-11-08 in `us-east-2` with an
explicitly approved local AWS CLI profile.

The isolated CloudFormation stack reached `CREATE_COMPLETE`. The repository's
actual Python runner, using `boto3` from a temporary local installation, then
completed these checks:

| Check | Observed result |
|---|---|
| Table-free smoke query | `SUCCEEDED`, 0 bytes scanned |
| First three-row table query | `SUCCEEDED`, 75 bytes scanned, not reused |
| Same query with a new submission key | `SUCCEEDED`, 0 bytes scanned, `reused_previous_result: true` |
| Retry using the first submission key | Returned the same query execution ID as the original submission |

This live check exposed and corrected an important design issue before
publication: the client request token now includes a per-submission request
key. The key remains stable for recovery retries but changes for a later
intentional run, allowing Athena to evaluate result reuse.

## Cleanup verification

The disposable Glue table was dropped before stack deletion. After the stack
reached delete-complete, all nine versions and delete markers in the retained
results bucket were deleted and the bucket itself was removed.

Final read-only checks returned:

- CloudFormation stack: does not exist;
- Athena workgroup: not found;
- Glue Data Catalog table: not found;
- S3 results bucket: HTTP 404 / not found.

## Publishing state

- Public GitHub repository:
  https://github.com/prabhacloud/athena-query-guardrails
- Published AWS Builder Center article:
  https://builder.aws.com/content/3LoVCXHbdopCkoozgCDpAs69Wjd/stop-expensive-athena-queries-before-they-surprise-you
- Published companion LinkedIn post:
  https://www.linkedin.com/feed/update/urn:li:activity:7525094970567835648/
- The article includes the GitHub source link. The LinkedIn post includes both
  public links and the AWS Community Builder hashtags.

