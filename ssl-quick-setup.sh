#!/bin/bash

# Quick SSL setup using existing certificates
# Works with whatever certificates are already available

set -e

DOMAIN="khudroo.com"

echo "🔐 Quick SSL Setup"
echo "Domain: $DOMAIN"
echo

# Check if we have certificates
if [[ ! -f "ssl/letsencrypt/live/$DOMAIN/fullchain.pem" ]]; then
    echo "❌ No certificates found at ssl/letsencrypt/live/$DOMAIN/fullchain.pem"
    echo "Run one of the SSL certificate scripts first"
    exit 1
fi

echo "✅ Certificate found"

# Check certificate details
echo "📋 Certificate info:"
openssl x509 -in ssl/letsencrypt/live/$DOMAIN/fullchain.pem -noout -text | grep -E "(Subject:|DNS:)" | head -5

# Check if wildcard
if openssl x509 -in ssl/letsencrypt/live/$DOMAIN/fullchain.pem -noout -text | grep -q "DNS:\*\.$DOMAIN"; then
    echo "✅ Wildcard certificate detected!"
    WILDCARD=true
else
    echo "⚠️ Standard certificate (main domain only)"
    WILDCARD=false
fi

# Check if staging
if openssl x509 -in ssl/letsencrypt/live/$DOMAIN/fullchain.pem -noout -issuer | grep -q "Fake LE"; then
    echo "⚠️ STAGING certificate (not trusted by browsers)"
    STAGING=true
else
    echo "✅ Production certificate"
    STAGING=false
fi

echo "🔧 Creating nginx configuration..."

# Create appropriate config based on certificate type
if [[ "$WILDCARD" == "true" ]]; then
    CONFIG_FILE="nginx/conf.d/wildcard-ssl.conf"
    cat > "$CONFIG_FILE" << EOF
# SSL Configuration with Wildcard Support for $DOMAIN
$(if [[ "$STAGING" == "true" ]]; then echo "# ⚠️  STAGING CERTIFICATE - NOT TRUSTED BY BROWSERS"; fi)

# Rate limiting
limit_req_zone \$binary_remote_addr zone=login_limit:10m rate=5r/m;
limit_req_zone \$binary_remote_addr zone=api_limit:10m rate=50r/m;

# WebSocket upgrade
map \$http_upgrade \$connection_upgrade {
    default upgrade;
    '' close;
}

# HTTP to HTTPS redirect for main domain
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;
    
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        try_files \$uri \$uri/ =404;
    }
    
    location / {
        return 301 https://\$server_name\$request_uri;
    }
}

# HTTP to HTTPS redirect for subdomains
server {
    listen 80;
    server_name ~^(?<subdomain>[^\\.]+)\\.$DOMAIN\$;
    
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        try_files \$uri \$uri/ =404;
    }
    
    location / {
        return 301 https://\$server_name\$request_uri;
    }
}

# HTTPS Main Domain - SaaS Manager
server {
    listen 443 ssl;
    http2 on;
    server_name $DOMAIN www.$DOMAIN;
    
    # SSL Configuration
    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    
    # SSL Security
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL_MAIN:50m;
    ssl_session_timeout 1d;
    ssl_dhparam /etc/nginx/ssl/dhparam.pem;
    
    # Security Headers
$(if [[ "$STAGING" == "true" ]]; then
    echo "    add_header X-SSL-Warning \"STAGING CERTIFICATE - NOT TRUSTED\" always;"
    echo "    add_header Strict-Transport-Security \"max-age=300\" always;"
else
    echo "    add_header Strict-Transport-Security \"max-age=63072000; includeSubDomains; preload\" always;"
fi)
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    # Health check
    location /ssl-health {
        return 200 "SSL OK - Main Domain$(if [[ "$STAGING" == "true" ]]; then echo " (STAGING)"; fi)";
        add_header Content-Type text/plain;
    }
    
    # Rate limiting for auth
    location ~ ^/(login|auth) {
        limit_req zone=login_limit burst=5 nodelay;
        
        proxy_pass http://saas_manager;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-Port \$server_port;
    }
    
    # Main proxy
    location / {
        proxy_pass http://saas_manager;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-Port \$server_port;
        
        # WebSocket support
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$connection_upgrade;
        
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}

# HTTPS Subdomains (Wildcard) - Odoo Tenants
server {
    listen 443 ssl;
    http2 on;
    server_name ~^(?<subdomain>[^\\.]+)\\.$DOMAIN\$;
    
    # SSL Configuration (same wildcard cert)
    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    
    # SSL Security
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL_TENANT:50m;
    ssl_session_timeout 1d;
    ssl_dhparam /etc/nginx/ssl/dhparam.pem;
    
    # Security Headers
$(if [[ "$STAGING" == "true" ]]; then
    echo "    add_header X-SSL-Warning \"STAGING CERTIFICATE - NOT TRUSTED\" always;"
    echo "    add_header Strict-Transport-Security \"max-age=300\" always;"
else
    echo "    add_header Strict-Transport-Security \"max-age=63072000; includeSubDomains; preload\" always;"
fi)
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    # Health check
    location /ssl-health {
        return 200 "SSL OK - Subdomain: \$subdomain$(if [[ "$STAGING" == "true" ]]; then echo " (STAGING)"; fi)";
        add_header Content-Type text/plain;
    }
    
    # Block database selector
    location ~ ^/web/database/(selector|manager) {
        return 404;
    }
    
    # Rate limiting for tenant auth
    location ~ ^/web/(login|session/authenticate) {
        limit_req zone=login_limit burst=3 nodelay;
        
        proxy_pass http://odoo_workers;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Subdomain \$subdomain;
    }
    
    # API rate limiting
    location ~ ^/(web/dataset/call_kw|jsonrpc) {
        limit_req zone=api_limit burst=20 nodelay;
        
        proxy_pass http://odoo_workers;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Subdomain \$subdomain;
    }
    
    # Main tenant proxy
    location / {
        proxy_pass http://odoo_workers;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Subdomain \$subdomain;
        
        # WebSocket support
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$connection_upgrade;
        
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
EOF
else
    # Standard certificate config
    CONFIG_FILE="nginx/conf.d/standard-ssl.conf"
    cat > "$CONFIG_FILE" << EOF
# SSL Configuration for $DOMAIN (Standard Certificate)
$(if [[ "$STAGING" == "true" ]]; then echo "# ⚠️  STAGING CERTIFICATE - NOT TRUSTED BY BROWSERS"; fi)

server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;
    
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        try_files \$uri \$uri/ =404;
    }
    
    location / {
        return 301 https://\$server_name\$request_uri;
    }
}

server {
    listen 443 ssl;
    http2 on;
    server_name $DOMAIN www.$DOMAIN;
    
    # SSL Configuration
    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    
    # SSL Security
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:50m;
    ssl_session_timeout 1d;
    ssl_dhparam /etc/nginx/ssl/dhparam.pem;
    
    # Security Headers
$(if [[ "$STAGING" == "true" ]]; then
    echo "    add_header X-SSL-Warning \"STAGING CERTIFICATE - NOT TRUSTED\" always;"
    echo "    add_header Strict-Transport-Security \"max-age=300\" always;"
else
    echo "    add_header Strict-Transport-Security \"max-age=63072000; includeSubDomains; preload\" always;"
fi)
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    # Health check
    location /ssl-health {
        return 200 "SSL OK - Main Domain Only$(if [[ "$STAGING" == "true" ]]; then echo " (STAGING)"; fi)";
        add_header Content-Type text/plain;
    }
    
    # Main proxy to SaaS Manager
    location / {
        proxy_pass http://saas_manager;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-Port \$server_port;
        
        # WebSocket support
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$connection_upgrade;
        
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
EOF
fi

echo "✅ Configuration created: $CONFIG_FILE"

# Remove conflicting SSL configs
for config in nginx/conf.d/*ssl*.conf; do
    if [[ -f "$config" && "$config" != "$CONFIG_FILE" ]]; then
        mv "$config" "$config.disabled.$(date +%s)" 2>/dev/null || true
    fi
done

# Start services
echo "🚀 Starting nginx with SSL..."
docker-compose up -d

sleep 3

# Test configuration
if docker-compose exec -T nginx nginx -t; then
    echo "✅ Nginx configuration is valid"
    
    echo
    echo "🎉 SSL Setup Completed!"
    echo
    if [[ "$STAGING" == "true" ]]; then
        echo "⚠️  STAGING CERTIFICATE - Browsers will show warnings"
        echo "   Click 'Advanced' -> 'Proceed to site' to access"
    else
        echo "✅ Production certificate - Trusted by browsers"
    fi
    echo
    if [[ "$WILDCARD" == "true" ]]; then
        echo "🌐 Available HTTPS URLs:"
        echo "   • https://$DOMAIN (SaaS Manager)"
        echo "   • https://www.$DOMAIN (SaaS Manager)"
        echo "   • https://kdoo_test2.$DOMAIN (Tenant)"
        echo "   • https://any-subdomain.$DOMAIN (Any tenant)"
        echo "   • https://test.$DOMAIN/ssl-health (Health check)"
    else
        echo "🌐 Available HTTPS URLs:"
        echo "   • https://$DOMAIN (SaaS Manager)"
        echo "   • https://www.$DOMAIN (SaaS Manager)"
        echo "   ⚠️ Subdomains not supported (standard certificate)"
    fi
    echo
    if [[ "$STAGING" != "true" ]]; then
        echo "🔍 Test SSL rating: https://www.ssllabs.com/ssltest/analyze.html?d=$DOMAIN"
    fi
else
    echo "❌ Nginx configuration failed"
    docker-compose logs nginx
    exit 1
fi