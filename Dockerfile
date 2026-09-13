FROM couchdb:3.5.2

USER root

RUN apt-get update && \
    apt-get install -y python3 python3-venv curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN python3 -m venv /venv
ENV PATH="/venv/bin:$PATH"

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x /app/start.sh

ENTRYPOINT []

CMD ["bash", "/app/start.sh"]