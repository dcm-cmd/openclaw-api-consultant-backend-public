FROM node:22-slim

LABEL org.opencontainers.image.description="OpenClaw API Consultant Gateway"
LABEL service="openclaw-api-consultant"

ARG OPENCLAW_VERSION=2026.5.27

RUN npm install -g openclaw@${OPENCLAW_VERSION} \
    && mkdir -p /home/node/.openclaw/workspace/consultant-main \
    && mkdir -p /home/node/.config/openclaw

WORKDIR /home/node
USER node

ENTRYPOINT ["openclaw"]
CMD ["gateway"]
