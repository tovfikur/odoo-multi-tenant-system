#!/bin/bash

# Simple SSL Test Script
# For testing purposes only - uses staging certificates

echo "🧪 SSL Testing Script"
echo "===================="
echo "This creates staging SSL certificates for testing"
echo

DOMAIN="${1:-khudroo.com}"
EMAIL="${2:-admin@khudroo.com}"

# Install certbot if needed
if ! command -v certbot &> /dev/null; then
    echo "Installing certbot..."
    sudo apt update && sudo apt install -y certbot
fi

# Stop nginx
echo "Stopping nginx..."
docker stop nginx 2>/dev/null || true

# Remove old staging certs
sudo certbot delete --cert-name "$DOMAIN" 2>/dev/null || true

# Get staging certificate
echo "Requesting staging certificate..."
sudo certbot certonly \
    --standalone \
    --staging \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    --domains "$DOMAIN,www.$DOMAIN" \
    --cert-name "$DOMAIN"

if [[ $? -eq 0 ]]; then
    echo "✅ Staging certificate obtained"
    
    # Copy to docker location
    sudo mkdir -p ./ssl/letsencrypt/live/$DOMAIN
    sudo cp /etc/letsencrypt/live/$DOMAIN/*.pem ./ssl/letsencrypt/live/$DOMAIN/
    sudo chown -R $USER:$USER ./ssl/letsencrypt/
    
    # Create simple SSL config
    cat > nginx/conf.d/test-ssl.conf << 'EOF'
# Test SSL Configuration

server {
    listen 80;
    server_name khudroo.com www.khudroo.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl;
    server_name khudroo.com www.khudroo.com;
    
    ssl_certificate /etc/letsencrypt/live/khudroo.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/khudroo.com/privkey.pem;
    
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    
    add_header Strict-Transport-Security "max-age=31536000" always;
    
    location /ssl-health {
        return 200 "Test SSL Working";
        add_header Content-Type text/plain;
    }
    
    location / {
        proxy_pass http://saas_manager;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF
    
    # Update docker-compose
    if ! grep -q "/etc/letsencrypt" docker-compose.yml; then
        sed -i '/- \.\/ssl\/dhparam\.pem:\/etc\/nginx\/ssl\/dhparam\.pem/a\      - /etc/letsencrypt:/etc/letsencrypt:ro' docker-compose.yml
    fi
    
    # Start services manually to avoid ContainerConfig error
    echo "Starting services manually..."
    
    docker network create odoo_network 2>/dev/null || true
    
    # Start containers one by one
    docker run -d --name postgres --network odoo_network \
        -e POSTGRES_USER=odoo -e POSTGRES_PASSWORD=odoo -e POSTGRES_DB=postgres \
        -v "$(pwd)/postgres_data:/var/lib/postgresql/data" \
        postgres:15 2>/dev/null || docker start postgres
    
    sleep 5
    
    docker run -d --name redis --network odoo_network \
        redis:alpine 2>/dev/null || docker start redis
    
    sleep 3
    
    docker run -d --name saas_manager --network odoo_network \
        -v "$(pwd)/saas_manager:/app" \
        odoo-multi-tenant-system_saas_manager 2>/dev/null || docker start saas_manager
    
    sleep 5
    
    docker run -d --name nginx --network odoo_network \
        -p 80:80 -p 443:443 \
        -v "$(pwd)/nginx/nginx.conf:/etc/nginx/nginx.conf" \
        -v "$(pwd)/nginx/conf.d:/etc/nginx/conf.d" \
        -v "/etc/letsencrypt:/etc/letsencrypt:ro" \
        nginx:alpine 2>/dev/null || docker start nginx
    
    echo "✅ Test SSL setup complete!"
    echo "🔗 Test at: https://$DOMAIN/ssl-health"
    echo "⚠️  This is a STAGING certificate (not trusted by browsers)"
    
else
    echo "❌ Certificate request failed"
    exit 1
fi