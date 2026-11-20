FROM node:22-alpine AS build
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Браузер ходит в API через тот же адрес (/backend/* → api:8000), поэтому снаружи открыт только сайт.
ENV NEXT_PUBLIC_API_URL=/backend API_ORIGIN=http://api:8000 NEXT_TELEMETRY_DISABLED=1 NEXT_NO_COMPRESS=1
# devDependencies не удаляем: next start читает next.config.ts, для этого нужен typescript
RUN npm run build

FROM node:22-alpine
WORKDIR /web
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 API_ORIGIN=http://api:8000 NEXT_NO_COMPRESS=1
COPY --from=build /web/package.json /web/next.config.ts ./
COPY --from=build /web/node_modules ./node_modules
COPY --from=build /web/.next ./.next
USER node
CMD ["npx", "next", "start", "-p", "3000"]
