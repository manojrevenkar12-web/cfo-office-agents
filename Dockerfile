# The console and API with the platform's agents, as a client's IT would run it inside their network.
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY cofa/ cofa/
COPY config/ config/
COPY reports/ reports/
COPY --from=web /web/dist web/dist
ENV COFA_RUN=/data/console PORT=8080
EXPOSE 8080
USER 1000
CMD ["python", "-m", "cofa.service.api"]
