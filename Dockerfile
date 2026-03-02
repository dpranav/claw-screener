FROM oven/bun:1-debian AS skill-deps

WORKDIR /skill
COPY package.json bun.lock ./
RUN bun install

FROM node:22-bookworm

RUN apt-get update && apt-get install -y \
    curl git ca-certificates unzip python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://bun.sh/install | bash
RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh
ENV PATH="/root/.bun/bin:/root/.local/bin:${PATH}"

RUN npm install -g openclaw@latest
RUN pip3 install clawmetry --break-system-packages
RUN mkdir -p /root/.openclaw/skills /root/.openclaw/data

WORKDIR /root/.openclaw/skills/claw-screener
COPY --from=skill-deps /skill/node_modules ./node_modules
COPY package.json bun.lock tsconfig.json SKILL.md ./
COPY src/ ./src/
COPY scripts/ ./scripts/

WORKDIR /root

EXPOSE 18789 8900

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN sed -i 's/\r$//' /docker-entrypoint.sh && chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
