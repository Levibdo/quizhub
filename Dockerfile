FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY index.html vite.config.js eslint.config.js ./
COPY public ./public
COPY src ./src

RUN chown -R node:node /app

ARG VITE_API_URL=http://localhost:8001
ENV VITE_API_URL=${VITE_API_URL}

EXPOSE 5173

USER node
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
