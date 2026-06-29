#!/bin/bash
# ─── CSR Backend Deployment — Docker Container Image ─────────────────────────
#
# Builds the CSR backend Docker image, pushes it to Amazon ECR,
# and updates the Lambda function to use the new image.
#
# Pre-requisites:
#   • Docker running locally (docker info)
#   • AWS CLI configured with permissions to ECR + Lambda
#   • Lambda function already created with package type = "Image"
#
# Usage:
#   bash deploy/deploy_backend.sh
#
# Environment variables (override defaults):
#   FUNCTION_NAME   Lambda function name     (default: csr-backend)
#   ECR_REPO        ECR repository name      (default: csr-backend)
#   AWS_REGION      AWS region               (default: ap-south-1)
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

FUNCTION_NAME="${FUNCTION_NAME:-csr-backend}"
ECR_REPO="${ECR_REPO:-csr-backend}"
REGION="${AWS_REGION:-ap-south-1}"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   CSR Backend — Docker Lambda Deployment     ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "Function : $FUNCTION_NAME"
echo "ECR repo : $ECR_REPO"
echo "Region   : $REGION"
echo ""

# ─── 1. Resolve AWS account ID ─────────────────────────────────────────────
echo "🔑 Resolving AWS account ID…"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
IMAGE_URI="${ECR_REGISTRY}/${ECR_REPO}:latest"
echo "   Registry : $ECR_REGISTRY"
echo "   Image    : $IMAGE_URI"
echo ""

# ─── 2. Ensure ECR repository exists ───────────────────────────────────────
echo "📦 Checking ECR repository…"
if aws ecr describe-repositories \
      --repository-names "$ECR_REPO" \
      --region "$REGION" \
      --output text > /dev/null 2>&1; then
  echo "   ✅ Repository already exists"
else
  aws ecr create-repository \
    --repository-name "$ECR_REPO" \
    --image-scanning-configuration scanOnPush=true \
    --region "$REGION" \
    --output text > /dev/null
  echo "   ✅ Repository created"
fi
echo ""

# ─── 3. Authenticate Docker with ECR ───────────────────────────────────────
echo "🔐 Logging in to ECR…"
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "$ECR_REGISTRY"
echo ""

# ─── 4. Build Docker image ─────────────────────────────────────────────────
echo "🐳 Building Docker image…"
docker build \
  --platform linux/amd64 \
  --tag "${ECR_REPO}:latest" \
  backend/
echo ""

# ─── 5. Tag and push to ECR ────────────────────────────────────────────────
echo "📤 Pushing image to ECR…"
docker tag "${ECR_REPO}:latest" "$IMAGE_URI"
docker push "$IMAGE_URI"
echo ""

# ─── 6. Deploy to Lambda ─────────────────────────────────────────────────────
echo "🚀 Checking Lambda function '$FUNCTION_NAME'…"

if aws lambda get-function --function-name "$FUNCTION_NAME" --region "$REGION" > /dev/null 2>&1; then
  echo "   Function exists. Updating code to new image…"
  aws lambda update-function-code \
    --function-name "$FUNCTION_NAME" \
    --image-uri "$IMAGE_URI" \
    --region "$REGION" \
    --output json \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"   State: {d.get('State','?')} | Last update: {d.get('LastUpdateStatus','?')}\")"
else
  echo "   Function does NOT exist."
  if [ -z "${LAMBDA_ROLE_ARN:-}" ]; then
    echo ""
    echo "❌ ERROR: Cannot create function because LAMBDA_ROLE_ARN is not set."
    echo "Please set your IAM Role ARN to create the function automatically:"
    echo "  export LAMBDA_ROLE_ARN=arn:aws:iam::${ACCOUNT_ID}:role/your-lambda-execution-role"
    echo "  bash deploy/deploy_backend.sh"
    echo ""
    echo "Or create the function manually in the AWS Console using this Image URI:"
    echo "  $IMAGE_URI"
    exit 1
  fi
  
  echo "   Creating new Lambda function from image…"
  aws lambda create-function \
    --function-name "$FUNCTION_NAME" \
    --package-type Image \
    --code ImageUri="$IMAGE_URI" \
    --role "$LAMBDA_ROLE_ARN" \
    --timeout 30 \
    --memory-size 256 \
    --region "$REGION" \
    --output json \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"   Created successfully! State: {d.get('State','?')}\")"
fi

echo ""
echo "✅ Deployment complete!"
echo ""
echo "Next steps if this is your first deploy:"
echo "  1. Add environment variables to Lambda: S3_BUCKET_NAME, JWT_SECRET, CSR_LAMBDA_ARN, SCHEDULER_ROLE_ARN, ALLOWED_ORIGINS"
echo "  2. Run: python deploy/seed_admin.py   (create first admin user)"
echo "  3. Configure API Gateway HTTP API to trigger this Lambda function."
