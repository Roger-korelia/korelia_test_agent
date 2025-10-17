FROM node:20-alpine AS deps
WORKDIR /app
COPY . /app
WORKDIR /app/apps/frontend
RUN npm ci || npm install

FROM node:20-alpine AS build
WORKDIR /app
COPY --from=deps /app /app
WORKDIR /app/apps/frontend
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
COPY --from=build /app/apps/frontend /app
ENV NODE_ENV=production
EXPOSE 3000
CMD ["npm", "run", "start", "--", "-H", "0.0.0.0"]
