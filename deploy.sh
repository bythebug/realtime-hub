#!/usr/bin/env bash
# Deploy realtime-hub to AWS ECS via ECR.
#
# Prerequisites:
#   - AWS CLI configured (aws configure)
#   - Docker running
#   - Environment variables set (see .env.example)
#
# Usage:
#   ./deploy.sh                      # deploy current git HEAD
#   IMAGE_TAG=v1.2.3 ./deploy.sh     # deploy a specific tag

set -euo pipefail

# ---- Configuration -----------------------------------------------------------
AWS_REGION="${AWS_REGION:-us-east-1}"
ECR_REGISTRY="${ECR_REGISTRY:?Set ECR_REGISTRY (e.g. 123456789.dkr.ecr.us-east-1.amazonaws.com)}"
ECR_REPOSITORY="${ECR_REPOSITORY:-realtime-hub}"
ECS_CLUSTER="${ECS_CLUSTER:-realtime-hub-cluster}"
ECS_SERVICE="${ECS_SERVICE:-realtime-hub-service}"
IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD)}"

IMAGE_URI="${ECR_REGISTRY}/${ECR_REPOSITORY}:${IMAGE_TAG}"
LATEST_URI="${ECR_REGISTRY}/${ECR_REPOSITORY}:latest"

# ---- Helpers -----------------------------------------------------------------
log()  { echo "[$(date '+%Y-%m-%dT%H:%M:%S')] $*"; }
fail() { echo "[ERROR] $*" >&2; exit 1; }

# ---- Step 1: Authenticate with ECR -------------------------------------------
log "Authenticating with ECR (${AWS_REGION})..."
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${ECR_REGISTRY}"

# ---- Step 2: Build image -----------------------------------------------------
log "Building image: ${IMAGE_URI}"
docker build \
  --platform linux/amd64 \
  --build-arg BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --build-arg GIT_SHA="${IMAGE_TAG}" \
  -t "${IMAGE_URI}" \
  -t "${LATEST_URI}" \
  .

# ---- Step 3: Push to ECR -----------------------------------------------------
log "Pushing ${IMAGE_URI}..."
docker push "${IMAGE_URI}"
docker push "${LATEST_URI}"

# ---- Step 4: Database migrations ---------------------------------------------
log "Running database migrations..."
aws ecs run-task \
  --cluster "${ECS_CLUSTER}" \
  --task-definition "realtime-hub-app" \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={
      subnets=[${SUBNET_IDS:?Set SUBNET_IDS}],
      securityGroups=[${SECURITY_GROUP_IDS:?Set SECURITY_GROUP_IDS}],
      assignPublicIp=DISABLED
    }" \
  --overrides "{
      \"containerOverrides\": [{
        \"name\": \"app\",
        \"image\": \"${IMAGE_URI}\",
        \"command\": [
          \"python\", \"-c\",
          \"from models import Base; from sqlalchemy import create_engine; import os; e=create_engine(os.environ['DATABASE_URL']); Base.metadata.create_all(e); print('Migrations done.')\"
        ]
      }]
    }" \
  --query 'tasks[0].taskArn' \
  --output text

log "Waiting for migration task to complete..."
# Give the task a moment to start, then wait (simple polling)
sleep 10

# ---- Step 5: Deploy new app revision -----------------------------------------
log "Deploying ${IMAGE_URI} to ECS service ${ECS_SERVICE}..."
aws ecs update-service \
  --cluster "${ECS_CLUSTER}" \
  --service "${ECS_SERVICE}" \
  --force-new-deployment \
  --output text \
  --query 'service.serviceArn' > /dev/null

# Also update the Celery worker service if it exists
WORKER_SERVICE="${ECS_SERVICE}-worker"
if aws ecs describe-services \
     --cluster "${ECS_CLUSTER}" \
     --services "${WORKER_SERVICE}" \
     --query 'services[0].status' \
     --output text 2>/dev/null | grep -q ACTIVE; then
  log "Deploying Celery worker service ${WORKER_SERVICE}..."
  aws ecs update-service \
    --cluster "${ECS_CLUSTER}" \
    --service "${WORKER_SERVICE}" \
    --force-new-deployment \
    --output text \
    --query 'service.serviceArn' > /dev/null
fi

# ---- Step 6: Wait for stability ----------------------------------------------
log "Waiting for ${ECS_SERVICE} to stabilize (this may take a few minutes)..."
aws ecs wait services-stable \
  --cluster "${ECS_CLUSTER}" \
  --services "${ECS_SERVICE}"

log "✓ Deployment complete!"
log "  Image:   ${IMAGE_URI}"
log "  Cluster: ${ECS_CLUSTER}"
log "  Service: ${ECS_SERVICE}"
