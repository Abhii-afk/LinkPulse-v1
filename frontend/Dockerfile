# Build the single page application and serve the built assets.
FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# The API origin is baked into the bundle at build time, so it has to be
# supplied when the image is built.
ARG VITE_API_BASE_URL=http://127.0.0.1:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build

FROM node:20-alpine AS runtime

WORKDIR /app

COPY --from=build /app/dist ./dist
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/package.json ./package.json

EXPOSE 4173

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:4173/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]

CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "4173"]
