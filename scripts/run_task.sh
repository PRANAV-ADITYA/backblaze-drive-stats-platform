#!/usr/bin/env bash
# Run the ingestion image once on Fargate, wait for it, and show what it printed.
#
# Usage: scripts/run_task.sh <module> [arguments...]
#   scripts/run_task.sh fetcher.fetch https://f001.backblazeb2.com/file/Backblaze-Hard-Drive-Data/data_Q3_2016.zip
#   scripts/run_task.sh fetcher.extract data_Q3_2016.zip
#   scripts/run_task.sh fetcher.bookkeeping
set -euo pipefail

CLUSTER=dsl-dev-cluster
TASK_DEFINITION=dsl-dev-fetcher
LOG_GROUP=/dsl-dev/fetcher

if [ "$#" -eq 0 ]; then
  echo "Usage: scripts/run_task.sh <module> [arguments...]" >&2
  exit 2
fi

# Where the task runs: the default network's subnets, behind the fetcher's door rules.
SECURITY_GROUP=$(aws ec2 describe-security-groups \
  --filters Name=group-name,Values=dsl-dev-fetcher \
  --query 'SecurityGroups[0].GroupId' --output text)
SUBNETS=$(aws ec2 describe-subnets \
  --filters Name=default-for-az,Values=true \
  --query 'Subnets[].SubnetId' --output text | tr '\t' ',')

# Turn the arguments into the JSON list that replaces the image's default command.
COMMAND=$(python3 -c 'import json, sys; print(json.dumps(sys.argv[1:]))' "$@")

TASK_ARN=$(aws ecs run-task \
  --cluster "$CLUSTER" \
  --task-definition "$TASK_DEFINITION" \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SECURITY_GROUP],assignPublicIp=ENABLED}" \
  --overrides "{\"containerOverrides\":[{\"name\":\"fetcher\",\"command\":$COMMAND}]}" \
  --query 'tasks[0].taskArn' --output text)

if [ "$TASK_ARN" = "None" ]; then
  echo "The task did not start. Run the 'aws ecs run-task' command by hand to see why." >&2
  exit 1
fi

TASK_ID=${TASK_ARN##*/}
echo "started task $TASK_ID: $*"

while true; do
  STATUS=$(aws ecs describe-tasks --cluster "$CLUSTER" --tasks "$TASK_ARN" \
    --query 'tasks[0].lastStatus' --output text)
  echo "  $(date +%H:%M:%S) $STATUS"
  if [ "$STATUS" = "STOPPED" ]; then
    break
  fi
  sleep 15
done

echo "--- what the program printed ---"
aws logs tail "$LOG_GROUP" --log-stream-names "fetcher/fetcher/$TASK_ID" --since 1d --format short \
  || echo "(no output found)"

echo "--- how it ended ---"
aws ecs describe-tasks --cluster "$CLUSTER" --tasks "$TASK_ARN" \
  --query 'tasks[0].{exitCode:containers[0].exitCode,stoppedReason:stoppedReason,containerReason:containers[0].reason}' \
  --output table
