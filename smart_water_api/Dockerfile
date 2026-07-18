FROM ghcr.io/home-assistant/base:latest

WORKDIR /app

ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN apk add --no-cache \
    python3 \
    py3-pip

RUN python3 -m venv "$VIRTUAL_ENV" \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir poetry

COPY pyproject.toml poetry.lock ./

RUN poetry install \
    --only main \
    --no-root \
    --no-interaction \
    --no-ansi

COPY app ./app
COPY run.sh /run.sh

RUN chmod +x /run.sh

CMD ["/run.sh"]