FROM quay.io/oauth2-proxy/oauth2-proxy:v7.14.2 AS oauth2-proxy

FROM python:3.11-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl openssl git nginx \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/nginx/sites-enabled/default

COPY conf/default.conf /etc/nginx/conf.d/default.conf
COPY conf/gzip.conf /etc/nginx/conf.d/gzip.conf

RUN mkdir -p /etc/ssl/private \
    && openssl genrsa -out /etc/ssl/private/jwt_signing_key.pem 2048 \
    && chmod 644 /etc/ssl/private/jwt_signing_key.pem

RUN curl -LO "https://dl.k8s.io/release/$(curl -Ls https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
    && chmod +x kubectl && mv kubectl /usr/local/bin/

RUN KUBEVIRT_VERSION=$(curl -s https://api.github.com/repos/kubevirt/kubevirt/releases/latest | grep tag_name | cut -d '"' -f 4) \
    && curl -L -o virtctl "https://github.com/kubevirt/kubevirt/releases/download/${KUBEVIRT_VERSION}/virtctl-${KUBEVIRT_VERSION}-linux-amd64" \
    && chmod +x virtctl && mv virtctl /usr/local/bin/

COPY --from=oauth2-proxy /bin/oauth2-proxy /bin/oauth2-proxy

WORKDIR /app

ENV UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY entrypoint.sh ./

RUN git clone https://github.com/novnc/noVNC.git /app/app/static/novnc

RUN mkdir -p /docker-entrypoint.d
COPY entrypoint/90-oauth-proxy.sh entrypoint/91-startkubectl.sh /docker-entrypoint.d/
RUN chmod +x /docker-entrypoint.d/*.sh

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8080

CMD ["/entrypoint.sh"]
