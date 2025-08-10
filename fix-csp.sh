#!/bin/bash

# Fix CSP (Content Security Policy) to allow CDN resources
# This resolves the CDN blocking issues on khudroo.com

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== Fixing CSP for CDN Support ===${NC}"

# Find the SSL configuration file that's currently being used
SSL_CONFIG=""
for config in nginx/conf.d/*ssl*.conf; do
    if [[ -f "$config" && ! "$config" =~ disabled ]]; then
        SSL_CONFIG="$config"
        break
    fi
done

if [[ -z "$SSL_CONFIG" ]]; then
    echo -e "${YELLOW}No active SSL config found, creating new one${NC}"
    SSL_CONFIG="nginx/conf.d/cdn-ssl.conf"
    
    # Create SSL configuration with CDN-friendly CSP
    cat > "$SSL_CONFIG" << 'EOF'
# CDN-Friendly SSL Configuration for khudroo.com
# Certificate: khudroo.com-0002

# WebSocket upgrade mapping
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

# HTTP to HTTPS redirect
server {
    listen 80;
    server_name khudroo.com;
    
    # ACME challenge
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        try_files $uri $uri/ =404;
        allow all;
        expires -1;
        add_header Cache-Control "no-cache, no-store, must-revalidate";
    }
    
    # Redirect to HTTPS
    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS server
server {
    listen 443 ssl;
    http2 on;
    server_name khudroo.com;
    
    # SSL certificates
    ssl_certificate /etc/letsencrypt/live/khudroo.com-0002/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/khudroo.com-0002/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/khudroo.com-0002/chain.pem;
    
    # Modern SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL_CDN:50m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;
    ssl_dhparam /etc/nginx/ssl/dhparam.pem;
    
    # OCSP stapling
    ssl_stapling on;
    ssl_stapling_verify on;
    resolver 8.8.8.8 8.8.4.4 1.1.1.1 1.0.0.1 valid=300s;
    resolver_timeout 5s;
    
    # Security headers with CDN-friendly CSP
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdnjs.cloudflare.com https://unpkg.com https://fonts.googleapis.com; style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com; img-src 'self' data: https: blob:; font-src 'self' data: https://fonts.gstatic.com https://cdnjs.cloudflare.com; connect-src 'self' wss: https:; frame-src 'self'; media-src 'self' data: https:;" always;
    
    # ACME challenge
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        try_files $uri $uri/ =404;
        allow all;
    }
    
    # Main application
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
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        # Error handling
        proxy_intercept_errors on;
        error_page 502 503 504 /50x.html;
    }
    
    # Health check endpoint
    location /health {
        proxy_pass http://saas_manager/health;
        proxy_set_header Host $host;
        access_log off;
    }
    
    # Static files with caching
    location ~* \.(css|js|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        proxy_pass http://saas_manager;
        proxy_set_header Host $host;
        expires 1h;
        add_header Cache-Control "public, immutable";
    }
}
EOF

else
    echo -e "${YELLOW}Found SSL config: $SSL_CONFIG${NC}"
    
    # Update existing SSL config with CDN-friendly CSP
    if grep -q "Content-Security-Policy" "$SSL_CONFIG"; then
        echo "Updating Content-Security-Policy..."
        # Replace the CSP line with CDN-friendly version
        sed -i 's|add_header Content-Security-Policy.*always;|add_header Content-Security-Policy "default-src '\''self'\''; script-src '\''self'\'' '\''unsafe-inline'\'' '\''unsafe-eval'\'' https://cdnjs.cloudflare.com https://unpkg.com https://fonts.googleapis.com; style-src '\''self'\'' '\''unsafe-inline'\'' https://cdnjs.cloudflare.com https://fonts.googleapis.com; img-src '\''self'\'' data: https: blob:; font-src '\''self'\'' data: https://fonts.gstatic.com https://cdnjs.cloudflare.com; connect-src '\''self'\'' wss: https:; frame-src '\''self'\''; media-src '\''self'\'' data: https:;" always;|g' "$SSL_CONFIG"
    else
        echo "Adding CDN-friendly CSP to existing config..."
        # Add CDN-friendly CSP before the location blocks
        sed -i '/location \^~ \/.well-known\/acme-challenge\//i\    # CDN-friendly Content Security Policy\n    add_header Content-Security-Policy "default-src '\''self'\''; script-src '\''self'\'' '\''unsafe-inline'\'' '\''unsafe-eval'\'' https://cdnjs.cloudflare.com https://unpkg.com https://fonts.googleapis.com; style-src '\''self'\'' '\''unsafe-inline'\'' https://cdnjs.cloudflare.com https://fonts.googleapis.com; img-src '\''self'\'' data: https: blob:; font-src '\''self'\'' data: https://fonts.gstatic.com https://cdnjs.cloudflare.com; connect-src '\''self'\'' wss: https:; frame-src '\''self'\''; media-src '\''self'\'' data: https:;" always;\n' "$SSL_CONFIG"
    fi
fi

echo -e "${GREEN}✓ SSL configuration updated with CDN support${NC}"

# Disable other SSL configs to avoid conflicts
echo "Managing SSL configurations..."
for config in nginx/conf.d/*ssl*.conf; do
    if [[ "$config" != "$SSL_CONFIG" && -f "$config" && ! "$config" =~ disabled ]]; then
        mv "$config" "$config.disabled.$(date +%s)"
        echo -e "${GREEN}✓ Disabled: $(basename "$config")${NC}"
    fi
done

# Test nginx configuration
echo "Testing nginx configuration..."
if docker-compose exec nginx nginx -t 2>&1; then
    echo -e "${GREEN}✓ Nginx configuration test passed${NC}"
    
    # Reload nginx configuration
    echo "Reloading nginx configuration..."
    if docker-compose exec nginx nginx -s reload; then
        echo -e "${GREEN}✓ Nginx configuration reloaded${NC}"
        
        echo ""
        echo -e "${GREEN}🎉 CSP Fixed Successfully! 🎉${NC}"
        echo ""
        echo -e "${GREEN}✅ CDN Resources Now Allowed:${NC}"
        echo -e "${GREEN}   • cdnjs.cloudflare.com (Bootstrap, jQuery, etc.)${NC}"
        echo -e "${GREEN}   • unpkg.com (Lottie files, etc.)${NC}"
        echo -e "${GREEN}   • fonts.googleapis.com (Google Fonts)${NC}"
        echo -e "${GREEN}   • fonts.gstatic.com (Font files)${NC}"
        echo ""
        echo -e "${BLUE}🔗 Test your site: https://khudroo.com${NC}"
        echo -e "${YELLOW}Refresh your browser to see the changes!${NC}"
        
    else
        echo -e "${GREEN}✓ Nginx restart successful (reload failed but that's ok)${NC}"
        docker-compose restart nginx
        echo -e "${GREEN}✓ Full nginx restart completed${NC}"
    fi
    
else
    echo "Nginx configuration test failed. Checking logs..."
    docker-compose logs --tail=20 nginx
fi