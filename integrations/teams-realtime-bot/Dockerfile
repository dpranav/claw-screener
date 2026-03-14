FROM node:20-bookworm-slim

WORKDIR /app

ENV NODE_ENV=production

COPY package.json /app/package.json
COPY src /app/src

RUN npm install --omit=dev

EXPOSE 7090

CMD ["node", "src/server.js"]

