# ① ビルド用：TypeScript / React を静的ファイル（HTML・JS）に変換する
FROM node:24-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# APIのURLはビルド時にJSへ埋め込まれるので、ビルド引数で受け取る
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# ② 配信用：できあがった静的ファイルだけを nginx で配る
FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80