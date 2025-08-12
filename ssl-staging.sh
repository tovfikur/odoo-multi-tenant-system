#!/bin/bash

# Get wildcard SSL certificate using Let's Encrypt STAGING environment
# Staging certificates are not trusted by browsers but allow testing SSL setup

set -e

DOMAIN="${1:-khudroo.com}"
EMAIL="${2:-admin@khudroo.com}"

echo "🔐 STAGING SSL Certificate Setup"
echo "Domain: $DOMAIN"
echo "Email: $EMAIL"
echo "⚠️  STAGING CERTIFICATES ARE NOT TRUSTED BY BROWSERS"
echo "   Use this for testing SSL configuration only"
echo

# Stop nginx
docker-compose stop nginx 2>/dev/null || true

# Create directories
mkdir -p ssl/certbot/conf ssl/certbot/www ssl/letsencrypt/live/$DOMAIN

echo "🌟 Requesting STAGING wildcard certificate..."

# Check if staging certificates already exist
if [[ -d "ssl/certbot/conf/live/$DOMAIN" ]]; then
    echo "✅ Found existing staging certificates"
    # Fix permissions and copy certificates
    sudo chown -R $USER:$USER ssl/certbot/conf/ 2>/dev/null || true
    
    if [[ -f "ssl/certbot/conf/live/$DOMAIN/fullchain.pem" ]]; then
        cp "ssl/certbot/conf/live/$DOMAIN/fullchain.pem" "ssl/letsencrypt/live/$DOMAIN/"
        cp "ssl/certbot/conf/live/$DOMAIN/privkey.pem" "ssl/letsencrypt/live/$DOMAIN/"
        cp "ssl/certbot/conf/live/$DOMAIN/chain.pem" "ssl/letsencrypt/live/$DOMAIN/" 2>/dev/null || true
        cp "ssl/certbot/conf/live/$DOMAIN/cert.pem" "ssl/letsencrypt/live/$DOMAIN/" 2>/dev/null || true
        chmod -R 755 ssl/letsencrypt/
        CERT_SUCCESS=true
    else
        echo "⚠️ Certificate directory exists but files missing, will request new certificate"
        CERT_SUCCESS=false
    fi
else
    CERT_SUCCESS=false
fi

# Request new staging wildcard certificate if needed
if [[ "$CERT_SUCCESS" != "true" ]]; then
    echo "🌟 Requesting new STAGING wildcard certificate..."
    if docker run --rm \
        -v "$(pwd)/ssl/certbot/conf:/etc/letsencrypt" \
        -v "$(pwd)/ssl/certbot/www:/var/www/certbot" \
        --network host \
        certbot/certbot certonly \
            --manual \
            --preferred-challenges=dns \
            --email "$EMAIL" \
            --agree-tos \
            --no-eff-email \
            --domains "$DOMAIN,*.$DOMAIN" \
            --cert-name "$DOMAIN" \
            --staging \
            --non-interactive; then
        
        echo "✅ New staging certificate obtained!"
        CERT_SUCCESS=true
    else
        echo "❌ Failed to obtain new staging certificate"
        CERT_SUCCESS=false
    fi
fi

if [[ "$CERT_SUCCESS" == "true" ]]; then
    
    # Ensure certificates are copied (may have been done earlier)
    if [[ ! -f "ssl/letsencrypt/live/$DOMAIN/fullchain.pem" ]]; then
        # Fix permissions from Docker certbot (runs as root)
        sudo chown -R $USER:$USER ssl/certbot/conf/ 2>/dev/null || true
        
        # Copy certificates to nginx location
        if [[ -f "ssl/certbot/conf/live/$DOMAIN/fullchain.pem" ]]; then
            cp "ssl/certbot/conf/live/$DOMAIN/fullchain.pem" "ssl/letsencrypt/live/$DOMAIN/"
            cp "ssl/certbot/conf/live/$DOMAIN/privkey.pem" "ssl/letsencrypt/live/$DOMAIN/"
            cp "ssl/certbot/conf/live/$DOMAIN/chain.pem" "ssl/letsencrypt/live/$DOMAIN/" 2>/dev/null || true
            cp "ssl/certbot/conf/live/$DOMAIN/cert.pem" "ssl/letsencrypt/live/$DOMAIN/" 2>/dev/null || true
            chmod -R 755 ssl/letsencrypt/
        else
            echo "❌ Certificate files still not accessible"
            exit 1
        fi
    fi
    
    echo "✅ Certificates ready for nginx"
    
    # Create nginx configuration for wildcard staging
    cat > nginx/conf.d/staging-ssl.conf << 'EOF'
# STAGING SSL Configuration with Wildcard Support
# ⚠️  STAGING CERTIFICATES ARE NOT TRUSTED BY BROWSERS

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
    
    # Headers
    add_header X-SSL-Warning "STAGING CERTIFICATE - NOT TRUSTED" always;
    add_header Strict-Transport-Security "max-age=300" always;  # Short HSTS for staging
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    
    # Health check
    location /ssl-health {
        return 200 "STAGING SSL OK - Main Domain";
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
        proxy_set_header Connection "upgrade";
        
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
EOF
    
    echo "✅ STAGING SSL configuration created"
    
    # Remove production configs to avoid conflicts
    for config in nginx/conf.d/*ssl*.conf; do
        if [[ -f "$config" && "$config" != *"staging-ssl.conf" ]]; then
            mv "$config" "$config.disabled.$(date +%s)" 2>/dev/null || true
        fi
    done
    
    # Start nginx
    echo "🚀 Starting nginx with STAGING SSL..."
    docker-compose up -d
    
    sleep 3
    
    # Test configuration
    if docker-compose exec -T nginx nginx -t; then
        echo "✅ Nginx configuration is valid"
        
        echo
        echo "🎉 STAGING SSL Setup Completed!"
        echo
        echo "⚠️  IMPORTANT: These are STAGING certificates"
        echo "   - Browsers will show security warnings"
        echo "   - Use 'Advanced' -> 'Proceed to site' to access"
        echo "   - Only for testing SSL configuration"
        echo
        echo "🌐 Test URLs (expect browser warnings):"
        echo "   • https://$DOMAIN (SaaS Manager)"
        echo "   • https://kdoo_test2.$DOMAIN (Tenant)"
        echo "   • https://any-subdomain.$DOMAIN (Any tenant)"
        echo
        echo "📋 Certificate Details:"
        openssl x509 -in ssl/letsencrypt/live/$DOMAIN/fullchain.pem -noout -text | grep -E "(Subject:|DNS:)"
        echo
        echo "🕒 To get production certificates:"
        echo "   Wait until after 2025-08-12 16:09:04 UTC"
        echo "   Then run: ./ssl-production-ultimate.sh"
        
    else
        echo "❌ Nginx configuration failed"
        docker-compose logs nginx
    fi
    
else
    echo "❌ Failed to obtain staging certificate"
    exit 1
fi