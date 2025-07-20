FROM nginx:alpine

# Install build dependencies
RUN apk add --no-cache --virtual .build-deps \
    gcc \
    libc-dev \
    make \
    openssl-dev \
    pcre-dev \
    zlib-dev \
    linux-headers \
    curl \
    git

# Download and compile ngx_http_redis module
RUN git clone https://github.com/openresty/redis-nginx-module.git /tmp/redis-nginx-module && \
    curl -sSL https://nginx.org/download/nginx-$(nginx -v 2>&1 | grep -o '[0-9.]*').tar.gz | tar -xz -C /tmp && \
    cd /tmp/nginx-$(nginx -v 2>&1 | grep -o '[0-9.]*') && \
    ./configure --add-module=/tmp/redis-nginx-module && \
    make && make install && \
    rm -rf /tmp/redis-nginx-module /tmp/nginx-$(nginx -v 2>&1 | grep -o '[0-9.]*')

# Clean up
RUN apk del .build-deps

COPY nginx.conf /etc/nginx/nginx.conf