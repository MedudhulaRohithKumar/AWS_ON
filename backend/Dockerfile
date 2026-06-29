# ─── CSR — Cloud Server Resurrector ─────────────────────────────────────────
# Lambda Container Image (Python 3.13)
#
# Build: docker build -t csr-backend .
# ─────────────────────────────────────────────────────────────────────────────

FROM public.ecr.aws/lambda/python:3.13

# Layer 1: dependencies (cached unless requirements.txt changes)
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Layer 2: application code
COPY main.py              ${LAMBDA_TASK_ROOT}/
COPY models/              ${LAMBDA_TASK_ROOT}/models/
COPY services/            ${LAMBDA_TASK_ROOT}/services/
COPY routers/             ${LAMBDA_TASK_ROOT}/routers/
COPY middleware/          ${LAMBDA_TASK_ROOT}/middleware/
COPY frontend/            ${LAMBDA_TASK_ROOT}/frontend/

# Lambda invocation entry point
CMD ["main.lambda_handler"]
