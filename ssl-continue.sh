#!/bin/bash

# Continue SSL setup with existing certificate
# Skip certificate generation due to rate limiting

set -e

DOMAIN="khudroo.com"
EMAIL="admin@khudroo.com"

echo "🔐 Continuing SSL setup with existing certificate..."
echo "Domain: $DOMAIN"
echo

# Check if certificate exists
if [[ ! -f "ssl/letsencrypt/live/$DOMAIN/fullchain.pem" ]]; then
    echo "❌ No certificate found at ssl/letsencrypt/live/$DOMAIN/fullchain.pem"
    exit 1
fi

echo "✅ Certificate found, continuing with SSL configuration..."

# Create production SSL config for nginx
cat > nginx/conf.d/production-ssl.conf << 'EOF'
# Production SSL Configuration for khudroo.com
# Using existing certificate (non-wildcard)

server {
    listen 80;
    server_name khudroo.com www.khudroo.com;
    
    # ACME challenge
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        try_files $uri $uri/ =404;
        allow all;
    }
    
    # Redirect to HTTPS
    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS Main Domain
server {
    listen 443 ssl http2;
    server_name khudroo.com www.khudroo.com;
    
    # SSL Configuration
    ssl_certificate /etc/letsencrypt/live/khudroo.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/khudroo.com/privkey.pem;
    
    # Modern SSL Configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:50m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;
    ssl_dhparam /etc/nginx/ssl/dhparam.pem;
    
    # Security Headers
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    # Health check
    location /ssl-health {
        access_log off;
        return 200 "SSL OK - Main Domain";
        add_header Content-Type text/plain;
    }
    
    # Proxy to SaaS Manager
    location / {
        proxy_pass http://saas_manager;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Port $server_port;
        
        # WebSocket support
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
EOF

echo "✅ SSL configuration created"

# Start nginx
echo "🚀 Starting nginx with SSL configuration..."
docker-compose up -d nginx

sleep 3

# Test configuration
echo "🧪 Testing SSL configuration..."
if docker-compose exec -T nginx nginx -t; then
    echo "✅ Nginx configuration is valid"
    
    # Test HTTPS connectivity
    echo "🌐 Testing HTTPS connectivity..."
    if timeout 10 curl -k -s "https://$DOMAIN/ssl-health" > /dev/null 2>&1; then
        echo "✅ HTTPS is working!"
        echo
        echo "🎉 SSL setup completed successfully!"
        echo "✅ Available URLs:"
        echo "   • https://$DOMAIN"
        echo "   • https://www.$DOMAIN"
        echo
        echo "⚠️  Note: This is a standard certificate (not wildcard)"
        echo "   Subdomains like kdoo_test2.$DOMAIN will show certificate errors"
        echo "   To get wildcard certificate, wait until after 2025-08-12 16:08:11 UTC"
        echo
        echo "🔍 Test your SSL: https://www.ssllabs.com/ssltest/analyze.html?d=$DOMAIN"
    else
        echo "⚠️  HTTPS test failed, but configuration was applied"
        echo "Check docker logs: docker-compose logs nginx"
    fi
else
    echo "❌ Nginx configuration test failed"
    docker-compose logs nginx
    exit 1
fi