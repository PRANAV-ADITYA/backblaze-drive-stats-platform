# Runbooks

Every alert sends an email through the SNS topic `dsl-dev-alerts`. Each alert's description links to one page here.

| Alert | Type | Page |
|---|---|---|
| dsl-dev-pipeline-failed | CloudWatch alarm (Step Functions ExecutionsFailed > 0 in an hour) | [pipeline-failed.md](pipeline-failed.md) |
| dsl-dev-pipeline-not-running | CloudWatch alarm (no pipeline start for 2 days) | [pipeline-not-running.md](pipeline-not-running.md) |
| dsl-dev-sensor-errors | CloudWatch alarm (sensor Lambda Errors > 0 in an hour) | [sensor-errors.md](sensor-errors.md) |
| dsl-dev-glue-job-failed | EventBridge rule (any dsl-dev Glue run FAILED, TIMEOUT or ERROR, including inside the backfill) | [glue-job-failed.md](glue-job-failed.md) |

## Receiving alerts

The email subscription is created by hand so the address never appears in this public repo:

    aws sns subscribe --topic-arn arn:aws:sns:ap-southeast-2:739871966917:dsl-dev-alerts --protocol email --notification-endpoint <your email>

Then click "Confirm subscription" in the email AWS sends.

Test the path end to end:

    aws cloudwatch set-alarm-state --alarm-name dsl-dev-sensor-errors --state-value ALARM --state-reason "Manual test"

The alarm returns to OK by itself at its next evaluation.

## Not covered by alerts

- Spend: watch the Credits page in the Billing console at the end of each phase (AWS Free plan).
- The Glue rule cannot be tested by hand (AWS does not allow fake aws.glue events); it is proven by the first real failure.
