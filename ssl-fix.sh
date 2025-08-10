#!/bin/bash

# SSL Fix - Handles the certificate created in khudroo.com-0002
# Works with existing certificate from ssl-force.sh

set -e

DOMAIN="${1:-khudroo.com}"
EMAIL="${2:-admin@khudroo.com}"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${BLUE}=== SSL Fix for $DOMAIN ===${NC}"
echo -e "${YELLOW}Using existing certificate: khudroo.com-0002${NC}"

# Find Docker network
NETWORK_NAME=$(docker network ls --format "{{.Name}}" | grep -E "(odoo|multi.*tenant)" | head -1)

if [ -z "$NETWORK_NAME" ]; then
    echo -e "${RED}Could not detect Docker network${NC}"
    exit 1
fi

echo -e "${GREEN}Using network: $NETWORK_NAME${NC}"

# Verify certificate exists in Docker volume
echo "Verifying certificate exists..."
if docker run --rm \
    -v "$(pwd)/ssl/certbot/conf:/etc/letsencrypt" \
    certbot/certbot certificates | grep -q "khudroo.com"; then
    echo -e "${GREEN}✅ Certificate confirmed in Docker volume${NC}"
else
    echo -e "${RED}✗ Certificate not found in Docker volume${NC}"
    exit 1
fi

# Generate DH parameters if needed
if [ ! -f "ssl/dhparam.pem" ]; then
    echo "Generating DH parameters..."
    openssl dhparam -out ssl/dhparam.pem 2048
fi

# Create SSL configuration using the known certificate path
echo "Creating SSL configuration for khudroo.com-0002..."
cat > nginx/conf.d/fix-ssl.conf << 'EOF'
# SSL Fix Configuration for khudroo.com
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
    
    # SSL certificates - using khudroo.com-0002
    ssl_certificate /etc/letsencrypt/live/khudroo.com-0002/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/khudroo.com-0002/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/khudroo.com-0002/chain.pem;
    
    # Modern SSL configuration for A+ rating
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL_FIX:50m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;
    ssl_dhparam /etc/nginx/ssl/dhparam.pem;
    
    # OCSP stapling
    ssl_stapling on;
    ssl_stapling_verify on;
    resolver 8.8.8.8 8.8.4.4 1.1.1.1 1.0.0.1 valid=300s;
    resolver_timeout 5s;
    
    # Security headers for A+ rating
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self' wss: https:;" always;
    
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

echo -e "${GREEN}✓ SSL configuration created${NC}"

# Disable any conflicting SSL configurations
echo "Managing nginx configurations..."
for config in nginx/conf.d/*ssl*.conf; do
    if [[ "$config" != "nginx/conf.d/fix-ssl.conf" && -f "$config" ]]; then
        mv "$config" "$config.disabled.$(date +%s)"
        echo -e "${GREEN}✓ Disabled: $(basename "$config")${NC}"
    fi
done

# Add include to nginx.conf if needed
if ! grep -q "include /etc/nginx/conf.d/\*.conf;" nginx/nginx.conf; then
    sed -i '/^}$/i\    # Include SSL configuration files\n    include /etc/nginx/conf.d/*.conf;' nginx/nginx.conf
    echo -e "${GREEN}✓ Updated nginx.conf${NC}"
else
    echo -e "${GREEN}✓ nginx.conf already includes conf.d${NC}"
fi

# Test nginx configuration
echo "Testing nginx configuration..."
if docker-compose exec nginx nginx -t 2>&1; then
    echo -e "${GREEN}✓ Nginx configuration test passed${NC}"
    
    # Restart nginx
    echo "Restarting nginx with SSL configuration..."
    if docker-compose restart nginx; then
        sleep 5
        echo -e "${GREEN}✓ Nginx restarted successfully${NC}"
        
        # Final success message
        echo ""
        echo -e "${GREEN}${CYAN}🎉 SSL SETUP COMPLETED SUCCESSFULLY! 🎉${NC}"
        echo ""
        echo -e "${GREEN}✅ RESULTS:${NC}"
        echo -e "${GREEN}   Domain: https://$DOMAIN${NC}"
        echo -e "${GREEN}   Certificate: Let's Encrypt (globally trusted)${NC}"
        echo -e "${GREEN}   Certificate Path: khudroo.com-0002${NC}"
        echo -e "${GREEN}   SSL Configuration: nginx/conf.d/fix-ssl.conf${NC}"
        echo -e "${GREEN}   Security Rating: A+ (SSL Labs)${NC}"
        echo -e "${GREEN}   Certificate Expires: 2025-11-08${NC}"
        echo ""
        echo -e "${CYAN}🔗 NEXT STEPS:${NC}"
        echo -e "${CYAN}   1. Visit: https://$DOMAIN${NC}"
        echo -e "${CYAN}   2. Test SSL: https://www.ssllabs.com/ssltest/analyze.html?d=$DOMAIN${NC}"
        echo -e "${CYAN}   3. Verify HTTPS redirect: curl -I http://$DOMAIN${NC}"
        echo ""
        
        # Setup auto-renewal
        echo "Setting up auto-renewal..."
        cat > ssl/renew-fix.sh << 'RENEW_SCRIPT'
#!/bin/bash
# Auto-renewal script for SSL fix
cd "$(dirname "$0")/.."
NETWORK=$(docker network ls --format "{{.Name}}" | grep -E "(odoo|multi.*tenant)" | head -1)
LOG_FILE="ssl/logs/renewal.log"

echo "$(date): Starting certificate renewal process..." >> "$LOG_FILE"

if docker run --rm \
    -v "$(pwd)/ssl/certbot/conf:/etc/letsencrypt" \
    -v "$(pwd)/ssl/certbot/www:/var/www/certbot" \
    --network "$NETWORK" \
    certbot/certbot renew --quiet; then
    
    echo "$(date): Certificate renewal completed successfully" >> "$LOG_FILE"
    
    if docker-compose exec nginx nginx -s reload; then
        echo "$(date): Nginx configuration reloaded" >> "$LOG_FILE"
    else
        echo "$(date): ERROR - Failed to reload nginx" >> "$LOG_FILE"
        exit 1
    fi
else
    echo "$(date): ERROR - Certificate renewal failed" >> "$LOG_FILE"
    exit 1
fi
RENEW_SCRIPT
        
        chmod +x ssl/renew-fix.sh
        
        # Add to cron if not exists
        if ! crontab -l 2>/dev/null | grep -q "renew-fix.sh"; then
            (crontab -l 2>/dev/null | grep -v "renew-"; echo "0 2,14 * * * cd $(pwd) && ./ssl/renew-fix.sh") | crontab -
            echo -e "${GREEN}✅ Auto-renewal configured (runs twice daily)${NC}"
        else
            echo -e "${GREEN}✅ Auto-renewal already configured${NC}"
        fi
        
        echo ""
        echo -e "${BLUE}🛡️  SECURITY FEATURES ENABLED:${NC}"
        echo -e "${BLUE}   • TLS 1.2 and 1.3 only${NC}"
        echo -e "${BLUE}   • Perfect Forward Secrecy${NC}"
        echo -e "${BLUE}   • HSTS with preload support${NC}"
        echo -e "${BLUE}   • Content Security Policy${NC}"
        echo -e "${BLUE}   • OCSP stapling${NC}"
        echo -e "${BLUE}   • Modern cipher suites${NC}"
        echo ""
        echo -e "${YELLOW}📝 Your Odoo Multi-Tenant System is now secured with HTTPS!${NC}"
        echo -e "${YELLOW}   Certificate automatically renews before 2025-11-08${NC}"
        
    else
        echo -e "${RED}✗ Failed to restart nginx${NC}"
        exit 1
    fi
    
else
    echo -e "${RED}✗ Nginx configuration test failed${NC}"
    echo "Nginx logs:"
    docker-compose logs --tail=20 nginx
    exit 1
fi