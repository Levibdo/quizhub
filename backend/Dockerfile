FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN groupadd --system quizhub && useradd --system --gid quizhub --home /app quizhub

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --upgrade pip && python -m pip install -r requirements.txt

COPY alembic ./alembic
COPY alembic.ini ./
COPY app ./app
COPY dados_oficiais/manifest.json ./dados_oficiais/manifest.json
COPY dados_oficiais/quiz_classico_v2.json ./dados_oficiais/quiz_classico_v2.json
COPY dados_oficiais/nem_a_pato_macabro_v1.json ./dados_oficiais/nem_a_pato_macabro_v1.json
COPY docker-entrypoint.sh ./docker-entrypoint.sh

RUN chown -R quizhub:quizhub /app && chmod 755 /app/docker-entrypoint.sh

USER quizhub
EXPOSE 8001

ENTRYPOINT ["/app/docker-entrypoint.sh"]
