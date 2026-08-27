# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

ARG APP_UID=10001
ARG APP_GID=10001

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    DATA_DIR=/app/data \
    AGENT_BIND_HOST=0.0.0.0 \
    AGENT_PORT=9000 \
    APSARA_APM_AGENT_WORKSPACE_DIR=/home/appuser \
    HOME=/home/appuser

WORKDIR /app

RUN groupadd --gid "${APP_GID}" appuser \
    && useradd --uid "${APP_UID}" --gid "${APP_GID}" --create-home appuser

COPY requirements/ /tmp/requirements/

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /tmp/requirements/common.txt \
    && pip install --no-cache-dir aliyun-bootstrap==1.0.8 \
    && aliyun-bootstrap -a install \
    && pip check

# Keep the costly common A2A + ARMS layer identical across all four builds.
ARG AGENT_NAME
ENV AGENT_NAME=${AGENT_NAME}

RUN case "$AGENT_NAME" in policy|research|provider|concierge) ;; *) echo "Invalid AGENT_NAME: $AGENT_NAME" >&2; exit 2 ;; esac \
    && pip install --no-cache-dir -r "/tmp/requirements/${AGENT_NAME}.txt" \
    && pip check \
    && rm -rf /tmp/requirements

COPY --chown=appuser:appuser src/ /app/src/
COPY --chown=appuser:appuser data/ /app/data/

USER appuser

EXPOSE 9000

HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9000/healthz', timeout=2)"

# Each build fixes AGENT_NAME and installs only that Agent's direct dependencies.
# AgentRun deploys the four resulting images as four managed AgentRuntime resources.
CMD ["aliyun-instrument", "python", "-m", "agentrun_app"]
