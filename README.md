# CSR — Cloud Server Resurrector

> Secure UAT Instance Control Portal for the CSR Project

CSR lets authorized teams extend UAT EC2 instances and RDS databases beyond the 6 PM shutdown schedule — without disabling any EventBridge rules or affecting other environments.

---

## Quick Start

### 1. Create IAM Role for Lambda

First, create the IAM role that your Lambda will use to execute.
- Go to AWS Console → IAM → Roles → Create role.
- Select **AWS service** → **Lambda**.
- Attach the policy defined in `iam_policy/csr_lambda_execution_policy.json`.
- Copy the **Role ARN** (e.g., `arn:aws:iam::123456789012:role/csr-lambda-role`).

### 2. Deploy via GitHub Actions (CI/CD)

The application is built and deployed automatically to AWS Lambda via GitHub Actions (`.github/workflows/deploy.yml`) on every push to the `main` branch or manual trigger (`workflow_dispatch`).

Configure the following in your GitHub Repository Settings → **Secrets and variables** → **Actions**:

- **Repository Secrets**:
  - `AWS_ACCESS_KEY_ID`: IAM user access key with ECR and Lambda permissions.
  - `AWS_SECRET_ACCESS_KEY`: IAM user secret key.
  - `LAMBDA_ROLE_ARN`: The ARN of your Lambda IAM role (from Step 1).
- **Repository Variables** (optional, defaults provided):
  - `AWS_REGION`: AWS region (default: `ap-south-1`).
  - `ECR_REPOSITORY`: Name of the ECR repository (default: `service-up`).
  - `LAMBDA_FUNCTION_NAME`: Name of your Lambda function (default: `serviceup`).

### 3. Create S3 Bucket & Configure Lambda Environment Variables

Create your S3 bucket (e.g. `my-csr-data-bucket`) to store user accounts, activity logs, servers, and extensions.

Configure the environment variables in your Lambda Function (**Configuration → Environment variables**):
See `.env.example` for all variables.
- `S3_BUCKET_NAME`: Name of your S3 bucket (e.g., `my-csr-data-bucket`).
- `AWS_REGION`: AWS region (e.g., `ap-south-1`).
- `JWT_SECRET`: Random 32+ character secret string.
- `CSR_LAMBDA_ARN`: ARN of the Lambda function (e.g., `arn:aws:lambda:...`).
- `SCHEDULER_ROLE_ARN`: ARN of the EventBridge Scheduler execution role.
- `ALLOWED_ORIGINS`: `*` or your custom domain / Function URL.

### 4. Seed Initial Admin User

Run the helper script locally to create your admin credentials in the S3 bucket:

```bash
python3 seed_admin.py
```
This prompts for your bucket name, admin username, email, and password, then securely hashes the password with bcrypt and uploads `users.json` to your S3 bucket (or saves it locally for manual S3 upload).

### 4. Patch Shutdown Lambdas

Replace the code in your existing shutdown Lambda functions with:
- `Instances_AutoStop_6PM` → use `shutdown_lambda_patch/ec2_autostop_patched.py`
- `RDS_AutoStop_6PM` → use `shutdown_lambda_patch/rds_autostop_patched.py`

---

## Architecture

```
CSR Lambda (Docker container image, Python 3.13 / FastAPI + Mangum)
├── Serves Frontend (Static Files)
└── Serves API (/api/*)
    ↙           ↘
S3 Bucket      AWS APIs
(JSON data)    EC2 / RDS / EventBridge Scheduler
```

### How it works

1. User logs in → JWT issued (8hr expiry)
2. User selects a server and deadline in the dashboard
3. CSR starts the instance and adds `EXTEND_UNTIL` tag
4. A one-time EventBridge Scheduler fires at the deadline → stops instance, removes tag
5. Meanwhile: EventBridge shutdown rules fire at 6 PM, 7 PM... 2 AM as normal
6. The patched shutdown Lambda sees the tag and **skips** that instance
7. All other UAT instances still stop on schedule

---

## File Structure

```
AWS_ON/
├── backend/                   # Python 3.13 Lambda (FastAPI)
│   ├── main.py                # Entry point + scheduler callback handler
│   ├── requirements.txt
│   ├── Dockerfile             # Container definition
│   ├── routers/               # API route handlers
│   ├── services/              # S3, AWS, Auth services
│   ├── models/schemas.py      # Pydantic models
│   ├── middleware/            # JWT auth middleware
│   └── frontend/              # Embedded frontend files (HTML/CSS/JS)
├── docker-compose.yml         # Local execution setup
├── .github/workflows/         # CI/CD pipelines
├── shutdown_lambda_patch/     # Drop-in replacements for shutdown Lambdas
│   ├── ec2_autostop_patched.py
│   └── rds_autostop_patched.py
├── iam_policy/                # IAM policies
│   ├── csr_lambda_execution_policy.json
│   └── csr_scheduler_invoke_policy.json
├── seed_admin.py              # Bootstrap first admin user (local or direct S3)
└── .env.example
```

---

## S3 Data Files (bucket: `instance-rds-extend`)

| File | Contents |
|---|---|
| `users.json` | User accounts (bcrypt-hashed passwords) |
| `activity.json` | Full audit log (up to 10,000 entries) |
| `servers.json` | Registered EC2/RDS instances |
| `extensions.json` | Extension records |

---

## IAM Setup

### CSR Lambda Execution Role
- Attach policy: `iam_policy/csr_lambda_execution_policy.json`
- EC2, RDS, S3 (instance-rds-extend bucket), EventBridge Scheduler, CloudWatch Logs

### EventBridge Scheduler Role (`csr-scheduler-invoke-role`)
1. Create IAM Role with trust: `scheduler.amazonaws.com`
2. Attach policy: `iam_policy/csr_scheduler_invoke_policy.json`
3. Copy ARN → Lambda env var `SCHEDULER_ROLE_ARN`

---

## Local Development

### Option 1: Without Docker (Python Native)

If you don't have Docker installed, you can run the app directly using Python.

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run the server
export S3_BUCKET_NAME=instance-rds-extend-local
export JWT_SECRET=local_secret_key_for_testing
export AWS_REGION=ap-south-1
# AWS_PROFILE is automatically used by boto3 if you ran `aws configure`
python3 -m uvicorn main:app --reload --port 8000
```

### Option 2: With Docker Compose

```bash
docker compose up --build
```

**Note**: To allow the container to access your AWS resources (like fetching EC2 details or writing to S3), the `docker-compose.yml` mounts your local `~/.aws` credentials folder. Ensure you have run `aws configure` on your local machine.

Open your browser to [http://localhost:8000](http://localhost:8000). The frontend HTML/JS will be served automatically from the root, and API requests will be routed properly.

---

## Security Notes

- Passwords hashed with bcrypt (12 rounds)
- JWT tokens expire after 8 hours
- All AWS ops use IAM Role — no credentials in code
- Admin routes return 403 to non-admin users
- All actions logged with IP + timestamp

**Change `JWT_SECRET` immediately after first deploy.**
