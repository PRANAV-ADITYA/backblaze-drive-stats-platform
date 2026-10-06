#!/usr/bin/env bash
# Service check: create and immediately delete one throwaway resource per AWS service
# the design needs, to prove the account's SCPs allow it. Safe to re-run.
set -u
export AWS_REGION=ap-southeast-2

ACCT=$(aws sts get-caller-identity --query Account --output text)
BUCKET="dsl-dev-artifacts-$ACCT"
RESULTS=()

check() {
  local name="$1"; shift
  local out
  if out=$("$@" 2>&1); then
    RESULTS+=("PASS  $name")
  else
    RESULTS+=("FAIL  $name :: $(echo "$out" | tail -n 1)")
  fi
}

t_ecr()     { aws ecr create-repository --repository-name dsl-test >/dev/null && aws ecr delete-repository --repository-name dsl-test --force >/dev/null; }
t_ecs()     { aws ecs create-cluster --cluster-name dsl-test >/dev/null && aws ecs delete-cluster --cluster dsl-test >/dev/null; }
t_logs()    { aws logs create-log-group --log-group-name /dsl/test && aws logs delete-log-group --log-group-name /dsl/test; }
t_sns()     { local arn; arn=$(aws sns create-topic --name dsl-test --query TopicArn --output text) && aws sns delete-topic --topic-arn "$arn"; }
t_sched()   { aws scheduler create-schedule-group --name dsl-test >/dev/null && aws scheduler delete-schedule-group --name dsl-test; }
t_gluedb()  { aws glue create-database --database-input Name=dsl_test && aws glue delete-database --name dsl_test; }
t_glacier() { echo test | aws s3 cp - "s3://$BUCKET/service-check/glacier-ir.txt" --storage-class GLACIER_IR \
                && aws s3 rm "s3://$BUCKET/service-check/glacier-ir.txt" >/dev/null; }
t_vpc()     { local v; v=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text) || return 1
              if [ -z "$v" ] || [ "$v" = "None" ]; then echo "no default VPC"; return 1; fi; }

t_athena() {
  local id state
  id=$(aws athena start-query-execution --query-string "SELECT 1" \
       --result-configuration "OutputLocation=s3://$BUCKET/service-check/athena/" \
       --query QueryExecutionId --output text) || return 1
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    state=$(aws athena get-query-execution --query-execution-id "$id" --query QueryExecution.Status.State --output text)
    case "$state" in
      SUCCEEDED) aws s3 rm "s3://$BUCKET/service-check/athena/" --recursive >/dev/null; return 0 ;;
      FAILED|CANCELLED) echo "query $state"; return 1 ;;
    esac
    sleep 2
  done
  echo "query timed out"; return 1
}

# Glue jobs and Step Functions need a role to run as. Create a throwaway one.
TRUST='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":["glue.amazonaws.com","states.amazonaws.com"]},"Action":"sts:AssumeRole"}]}'
ROLE_ARN=$(aws iam create-role --role-name dsl-service-check --assume-role-policy-document "$TRUST" --query Role.Arn --output text)
sleep 15   # new IAM roles take a few seconds to become usable

t_gluejob() { aws glue create-job --name dsl-test --role "$ROLE_ARN" --glue-version 5.0 \
                --command "Name=glueetl,ScriptLocation=s3://$BUCKET/service-check/none.py,PythonVersion=3" >/dev/null \
                && aws glue delete-job --job-name dsl-test >/dev/null; }
t_sfn()     { local arn; arn=$(aws stepfunctions create-state-machine --name dsl-test --role-arn "$ROLE_ARN" \
                --definition '{"StartAt":"P","States":{"P":{"Type":"Pass","End":true}}}' \
                --query stateMachineArn --output text) && aws stepfunctions delete-state-machine --state-machine-arn "$arn"; }

check "ECR: create/delete repository"            t_ecr
check "ECS: create/delete cluster"               t_ecs
check "VPC: default VPC exists (for Fargate)"    t_vpc
check "CloudWatch Logs: create/delete group"     t_logs
check "SNS: create/delete topic"                 t_sns
check "EventBridge Scheduler: create/delete group" t_sched
check "Glue: create/delete database"             t_gluedb
check "Glue: create/delete job"                  t_gluejob
check "Athena: run SELECT 1"                     t_athena
check "Step Functions: create/delete machine"    t_sfn
check "S3: store object as Glacier Instant Retrieval" t_glacier

aws iam delete-role --role-name dsl-service-check

echo "Service check, $(date -u +%Y-%m-%dT%H:%MZ), region $AWS_REGION"
printf '%s\n' "${RESULTS[@]}"
