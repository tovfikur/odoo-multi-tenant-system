#!/bin/bash

# Fix staging SSL setup using existing certificates
# Use existing staging certificates to set up wildcard SSL

set -e

DOMAIN="khudroo.com"

echo "🔐 Fixing Staging SSL with existing certificates"
echo "Domain: $DOMAIN"
echo

# Create directories
mkdir -p ssl/letsencrypt/live/$DOMAIN

# Fix permissions for certbot certificates
echo "🔧 Fixing certificate permissions..."
sudo chown -R $USER:$USER ssl/certbot/ 2>/dev/null || true

# Check what certificates we have
echo "📋 Available certificates:"
if [[ -d "ssl/certbot/conf/live" ]]; then
    ls -la ssl/certbot/conf/live/
else
    echo "No certbot certificates found"
fi

# Try to use any existing certificate
CERT_FOUND=false

if [[ -f "ssl/certbot/conf/live/$DOMAIN/fullchain.pem" ]]; then
    echo "✅ Found staging certificate in certbot volume"
    cp "ssl/certbot/conf/live/$DOMAIN/fullchain.pem" "ssl/letsencrypt/live/$DOMAIN/"
    cp "ssl/certbot/conf/live/$DOMAIN/privkey.pem" "ssl/letsencrypt/live/$DOMAIN/"
    cp "ssl/certbot/conf/live/$DOMAIN/chain.pem" "ssl/letsencrypt/live/$DOMAIN/" 2>/dev/null || true
    cp "ssl/certbot/conf/live/$DOMAIN/cert.pem" "ssl/letsencrypt/live/$DOMAIN/" 2>/dev/null || true
    CERT_FOUND=true
elif [[ -f "ssl/letsencrypt/live/$DOMAIN/fullchain.pem" ]]; then
    echo "✅ Certificate already exists in nginx location"
    CERT_FOUND=true
else
    echo "❌ No staging certificates found"
    echo "   Please run: ./ssl-staging.sh and complete DNS validation manually"
    exit 1
fi

if [[ "$CERT_FOUND" == "true" ]]; then
    chmod -R 755 ssl/letsencrypt/
    
    echo "📋 Certificate info:"
    openssl x509 -in ssl/letsencrypt/live/$DOMAIN/fullchain.pem -noout -text | grep -E "(Subject:|DNS:)" | head -5
    
    # Check if this is a wildcard certificate
    if openssl x509 -in ssl/letsencrypt/live/$DOMAIN/fullchain.pem -noout -text | grep -q "DNS:\*\.$DOMAIN"; then
        echo "✅ This is a wildcard certificate!"
        WILDCARD=true
    else
        echo "⚠️ This is a standard certificate (not wildcard)"
        WILDCARD=false
    fi
    
    # Create nginx configuration
    echo "🔧 Creating nginx configuration..."
    
    if [[ "$WILDCARD" == "true" ]]; then
        # Use wildcard configuration
        cat > nginx/conf.d/staging-ssl.conf << 'EOF'
# STAGING SSL Configuration with Wildcard Support
# ⚠️  STAGING CERTIFICATES ARE NOT TRUSTED BY BROWSERS

# Rate limiting
limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;
limit_req_zone $binary_remote_addr zone=api:10m rate=50r/m;

# WebSocket upgrade
map $http_upgrade $connection_upgrade {
    default upgrade;
    '' close;
}

# HTTP to HTTPS redirect for main domain
server {
    listen 80;
    server_name khudroo.com www.khudroo.com;
    
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        try_files $uri $uri/ =404;
    }
    
    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTP to HTTPS redirect for subdomains (wildcard)
server {
    listen 80;
    server_name ~^(?<subdomain>[^\.]+)\.khudroo\.com$;
    
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        try_files $uri $uri/ =404;
    }
    
    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS Main Domain - SaaS Manager
server {
    listen 443 ssl;
    http2 on;
    server_name khudroo.com www.khudroo.com;
    
    # SSL Configuration (STAGING)
    ssl_certificate /etc/letsencrypt/live/khudroo.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/khudroo.com/privkey.pem;
    
    # SSL Security
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:50m;
    ssl_session_timeout 1d;
    ssl_dhparam /etc/nginx/ssl/dhparam.pem;
    
    # Headers (shorter HSTS for staging)
    add_header X-SSL-Warning "STAGING CERTIFICATE - NOT TRUSTED" always;
    add_header Strict-Transport-Security "max-age=300" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    # Health check
    location /ssl-health {
        return 200 "STAGING SSL OK - Main Domain";
        add_header Content-Type text/plain;
    }
    
    # Login rate limiting
    location ~ ^/(login|auth) {
        limit_req zone=login burst=5 nodelay;
        
        proxy_pass http://saas_manager;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
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
        proxy_set_header Connection $connection_upgrade;
        
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}

# HTTPS Subdomains (Wildcard) - Odoo Tenants
server {
    listen 443 ssl;
    http2 on;
    server_name ~^(?<subdomain>[^\.]+)\.khudroo\.com$;
    
    # SSL Configuration (STAGING - same wildcard cert)
    ssl_certificate /etc/letsencrypt/live/khudroo.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/khudroo.com/privkey.pem;
    
    # SSL Security
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:50m;
    ssl_session_timeout 1d;
    ssl_dhparam /etc/nginx/ssl/dhparam.pem;
    
    # Headers
    add_header X-SSL-Warning "STAGING CERTIFICATE - NOT TRUSTED" always;
    add_header Strict-Transport-Security "max-age=300" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    
    # Health check
    location /ssl-health {
        return 200 "STAGING SSL OK - Subdomain: $subdomain";
        add_header Content-Type text/plain;
    }
    
    # Block database selector
    location ~ ^/web/database/(selector|manager) {
        return 404;
    }
    
    # Login rate limiting
    location ~ ^/web/(login|session/authenticate) {
        limit_req zone=login burst=3 nodelay;
        
        proxy_pass http://odoo_workers;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Subdomain $subdomain;
    }
    
    # API rate limiting
    location ~ ^/(web/dataset/call_kw|jsonrpc) {
        limit_req zone=api burst=20 nodelay;
        
        proxy_pass http://odoo_workers;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Subdomain $subdomain;
    }
    
    # Proxy to Odoo workers
    location / {
        proxy_pass http://odoo_workers;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Subdomain $subdomain;
        
        # WebSocket support
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
EOF
    else
        # Use standard configuration (no wildcard)
        cat > nginx/conf.d/staging-ssl.conf << 'EOF'
# STAGING SSL Configuration (Standard Certificate)
# ⚠️  STAGING CERTIFICATES ARE NOT TRUSTED BY BROWSERS

server {
    listen 80;
    server_name khudroo.com www.khudroo.com;
    
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        try_files $uri $uri/ =404;
    }
    
    location / {
        return 301 https://$server_name$request_uri;
    }
}

server {
    listen 443 ssl;
    http2 on;
    server_name khudroo.com www.khudroo.com;
    
    # SSL Configuration (STAGING)
    ssl_certificate /etc/letsencrypt/live/khudroo.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/khudroo.com/privkey.pem;
    
    # SSL Security
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:50m;
    ssl_session_timeout 1d;
    ssl_dhparam /etc/nginx/ssl/dhparam.pem;
    
    # Headers
    add_header X-SSL-Warning "STAGING CERTIFICATE - NOT TRUSTED" always;
    add_header Strict-Transport-Security "max-age=300" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    
    # Health check
    location /ssl-health {
        return 200 "STAGING SSL OK - Main Domain Only";
        add_header Content-Type text/plain;
    }
    
    # Proxy to SaaS Manager
    location / {
        proxy_pass http://saas_manager;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
EOF
    fi
    
    echo "✅ Nginx configuration created"
    
    # Remove production configs to avoid conflicts
    for config in nginx/conf.d/*ssl*.conf; do
        if [[ -f "$config" && "$config" != *"staging-ssl.conf" ]]; then
            mv "$config" "$config.disabled.$(date +%s)" 2>/dev/null || true
        fi
    done
    
    # Start nginx
    echo "🚀 Starting nginx with SSL configuration..."
    docker-compose up -d nginx
    
    sleep 3
    
    # Test configuration
    if docker-compose exec -T nginx nginx -t; then
        echo "✅ Nginx configuration is valid"
        
        echo
        echo "🎉 STAGING SSL Setup Completed!"
        echo
        echo "⚠️  IMPORTANT: These are STAGING certificates"
        echo "   - Browsers will show 'Not Secure' warnings"
        echo "   - Click 'Advanced' -> 'Proceed to site' to access"
        echo "   - Only for testing SSL configuration"
        echo
        if [[ "$WILDCARD" == "true" ]]; then
            echo "🌐 Test URLs (expect browser warnings):"
            echo "   • https://$DOMAIN (SaaS Manager)"
            echo "   • https://kdoo_test2.$DOMAIN (Tenant)"
            echo "   • https://any-subdomain.$DOMAIN (Any tenant)"
        else
            echo "🌐 Test URLs (expect browser warnings):"
            echo "   • https://$DOMAIN (SaaS Manager)"
            echo "   • https://www.$DOMAIN (SaaS Manager)"
            echo "   ⚠️ Subdomains not supported (standard certificate)"
        fi
        echo
        echo "🕒 To get trusted production certificates:"
        echo "   Wait until after 2025-08-12 16:09:04 UTC"
        echo "   Then run: ./ssl-production-ultimate.sh"
        
    else
        echo "❌ Nginx configuration failed"
        docker-compose logs nginx
        exit 1
    fi
else
    echo "❌ No certificates available"
    exit 1
fi