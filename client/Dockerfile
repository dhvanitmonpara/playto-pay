FROM node:24-alpine

WORKDIR /app

COPY package.json bun.lock* ./
RUN npm install

COPY . .

EXPOSE 5173

