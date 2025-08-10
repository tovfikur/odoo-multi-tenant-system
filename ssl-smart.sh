#!/bin/bash

# Smart SSL Setup - Checks existing certificates first
# Perfect for khudroo.com where certificates may already exist

set -e

DOMAIN="${1:-khudroo.com}"
EMAIL="${2:-admin@khudroo.com}"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== Smart SSL Setup for $DOMAIN ===${NC}"

# Create directories
echo "Setting up SSL directories..."
mkdir -p ssl/certbot/conf ssl/certbot/www ssl/logs nginx/conf.d

# Find Docker network
echo "Detecting Docker network..."
NETWORK_NAME=$(docker network ls --format "{{.Name}}" | grep -E "(odoo|multi.*tenant)" | head -1)

if [ -z "$NETWORK_NAME" ]; then
    echo -e "${RED}Could not detect Docker network${NC}"
    echo "Available networks:"
    docker network ls
    exit 1
fi

echo -e "${GREEN}Using network: $NETWORK_NAME${NC}"

# Function to find existing certificates
find_existing_certificate() {
    local domain="$1"
    echo "Searching for existing certificates for $domain..."
    
    # Check if we have any certificates
    if [ ! -d "ssl/certbot/conf/live" ]; then
        echo "No existing certificates found (no live directory)"
        return 1
    fi
    
    # Search for certificates
    cert_candidates=(
        "ssl/certbot/conf/live/$domain"
        "ssl/certbot/conf/live/$domain-0001" 
        "ssl/certbot/conf/live/$domain-0002"
        "ssl/certbot/conf/live/$domain-0003"
    )
    
    for cert_dir in "${cert_candidates[@]}"; do
        echo "Checking: $cert_dir"
        if [[ -f "$cert_dir/fullchain.pem" && -f "$cert_dir/privkey.pem" ]]; then
            # Check if certificate is still valid (not expired)
            if openssl x509 -checkend 86400 -noout -in "$cert_dir/cert.pem" 2>/dev/null; then
                CERT_PATH="$cert_dir"
                local expiry=$(openssl x509 -enddate -noout -in "$cert_dir/cert.pem" | cut -d= -f2)
                echo -e "${GREEN}Found valid certificate at: $cert_dir${NC}"
                echo -e "${GREEN}Certificate expires: $expiry${NC}"
                return 0
            else
                echo -e "${YELLOW}Found expired certificate at: $cert_dir${NC}"
            fi
        fi
    done
    
    # Search all live directories
    for cert_dir in ssl/certbot/conf/live/*/; do
        if [[ -f "$cert_dir/fullchain.pem" && -f "$cert_dir/privkey.pem" ]]; then
            if openssl x509 -checkend 86400 -noout -in "$cert_dir/cert.pem" 2>/dev/null; then
                CERT_PATH="$cert_dir"
                local expiry=$(openssl x509 -enddate -noout -in "$cert_dir/cert.pem" | cut -d= -f2)
                echo -e "${GREEN}Found valid certificate at: $cert_dir${NC}"
                echo -e "${GREEN}Certificate expires: $expiry${NC}"
                return 0
            fi
        fi
    done
    
    echo "No valid certificates found"
    return 1
}

# Restart containers
echo "Restarting Docker containers..."
docker-compose restart
sleep 10

# Generate DH parameters if needed
if [ ! -f "ssl/dhparam.pem" ]; then
    echo "Generating DH parameters..."
    openssl dhparam -out ssl/dhparam.pem 2048
fi

# Check for existing valid certificate first
CERT_PATH=""
if find_existing_certificate "$DOMAIN"; then
    echo -e "${GREEN}✅ Using existing valid certificate!${NC}"
else
    # Need to get new certificate
    echo -e "${GREEN}Requesting new SSL certificate from Let's Encrypt...${NC}"
    echo -e "${YELLOW}Domain will be validated from the internet${NC}"
    
    if docker run --rm \
        -v "$(pwd)/ssl/certbot/conf:/etc/letsencrypt" \
        -v "$(pwd)/ssl/certbot/www:/var/www/certbot" \
        --network "$NETWORK_NAME" \
        certbot/certbot certonly \
        --webroot \
        --webroot-path=/var/www/certbot \
        --email "$EMAIL" \
        --agree-tos \
        --no-eff-email \
        --keep-until-expiring \
        --non-interactive \
        -d "$DOMAIN"; then
        
        echo -e "${GREEN}✅ SSL Certificate obtained!${NC}"
        
        # Find the newly created certificate
        if ! find_existing_certificate "$DOMAIN"; then
            echo -e "${RED}Certificate was created but cannot be found${NC}"
            exit 1
        fi
    else
        echo -e "${RED}✗ Certificate request failed${NC}"
        echo -e "${YELLOW}This might be due to:${NC}"
        echo -e "${YELLOW}1. Rate limiting (try again in 1 hour)${NC}"
        echo -e "${YELLOW}2. Domain DNS not pointing to this server${NC}"
        echo -e "${YELLOW}3. Firewall blocking port 80${NC}"
        exit 1
    fi
fi

CERT_DIR_NAME=$(basename "$CERT_PATH")
echo -e "${GREEN}Using certificate: $CERT_DIR_NAME${NC}"

# Create SSL configuration
echo "Creating SSL configuration..."
cat > nginx/conf.d/smart-ssl.conf << EOF
# Smart SSL Configuration for $DOMAIN
# Certificate: $CERT_DIR_NAME

# WebSocket upgrade mapping
map \$http_upgrade \$connection_upgrade {
    default upgrade;
    ''      close;
}

# HTTP to HTTPS redirect
server {
    listen 80;
    server_name $DOMAIN;
    
    # ACME challenge
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        try_files \$uri \$uri/ =404;
        allow all;
        expires -1;
        add_header Cache-Control "no-cache, no-store, must-revalidate";
    }
    
    # Redirect to HTTPS
    location / {
        return 301 https://\$server_name\$request_uri;
    }
}

# HTTPS server
server {
    listen 443 ssl;
    http2 on;
    server_name $DOMAIN;
    
    # SSL certificates
    ssl_certificate /etc/letsencrypt/live/$CERT_DIR_NAME/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$CERT_DIR_NAME/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/$CERT_DIR_NAME/chain.pem;
    
    # Modern SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL_SMART:50m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;
    ssl_dhparam /etc/nginx/ssl/dhparam.pem;
    
    # OCSP stapling
    ssl_stapling on;
    ssl_stapling_verify on;
    resolver 8.8.8.8 8.8.4.4 1.1.1.1 1.0.0.1 valid=300s;
    resolver_timeout 5s;
    
    # Security headers
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self' wss: https:;" always;
    
    # ACME challenge
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        try_files \$uri \$uri/ =404;
        allow all;
    }
    
    # Main application
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
        proxy_pass http://saas_manager;
        proxy_set_header Host \$host;
        access_log off;
    }
    
    # Static files with caching
    location ~* \.(css|js|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        proxy_pass http://saas_manager;
        proxy_set_header Host \$host;
        expires 1h;
        add_header Cache-Control "public, immutable";
    }
}
EOF

echo -e "${GREEN}✓ SSL configuration created${NC}"

# Disable conflicting configs
for config in nginx/conf.d/*ssl*.conf; do
    if [[ "$config" != "nginx/conf.d/smart-ssl.conf" && -f "$config" ]]; then
        mv "$config" "$config.disabled"
        echo -e "${GREEN}✓ Disabled: $(basename "$config")${NC}"
    fi
done

# Add include to nginx.conf if needed
if ! grep -q "include /etc/nginx/conf.d/\*.conf;" nginx/nginx.conf; then
    sed -i '/^}$/i\    include /etc/nginx/conf.d/*.conf;' nginx/nginx.conf
    echo -e "${GREEN}✓ Updated nginx.conf${NC}"
fi

# Test nginx configuration
echo "Testing nginx configuration..."
if docker-compose exec nginx nginx -t; then
    echo -e "${GREEN}✓ Nginx config valid${NC}"
    
    # Restart nginx
    echo "Restarting nginx..."
    docker-compose restart nginx
    sleep 5
    
    echo ""
    echo -e "${GREEN}🎉 SSL SETUP COMPLETED SUCCESSFULLY!${NC}"
    echo -e "${GREEN}✅ Domain: https://$DOMAIN${NC}"
    echo -e "${GREEN}✅ Certificate: Let's Encrypt (globally trusted)${NC}"
    echo -e "${GREEN}✅ Certificate path: $CERT_DIR_NAME${NC}"
    echo -e "${GREEN}✅ Configuration: nginx/conf.d/smart-ssl.conf${NC}"
    echo ""
    echo -e "${BLUE}🔗 Test your site: https://$DOMAIN${NC}"
    echo -e "${BLUE}🔒 SSL rating: https://www.ssllabs.com/ssltest/analyze.html?d=$DOMAIN${NC}"
    
    # Setup auto-renewal
    cat > ssl/renew-smart.sh << 'RENEW_SCRIPT'
#!/bin/bash
cd "$(dirname "$0")/.."
NETWORK=$(docker network ls --format "{{.Name}}" | grep -E "(odoo|multi.*tenant)" | head -1)
echo "$(date): Starting certificate renewal check..."
if docker run --rm \
    -v "$(pwd)/ssl/certbot/conf:/etc/letsencrypt" \
    -v "$(pwd)/ssl/certbot/www:/var/www/certbot" \
    --network "$NETWORK" \
    certbot/certbot renew --quiet; then
    echo "$(date): Certificate renewal check completed"
    if docker-compose exec nginx nginx -s reload; then
        echo "$(date): Nginx reloaded successfully"
    else
        echo "$(date): Failed to reload nginx"
        exit 1
    fi
else
    echo "$(date): Certificate renewal failed"
    exit 1
fi
RENEW_SCRIPT
    
    chmod +x ssl/renew-smart.sh
    
    # Add to cron if not exists
    if ! crontab -l 2>/dev/null | grep -q "renew-smart"; then
        (crontab -l 2>/dev/null | grep -v "renew-smart"; echo "0 2,14 * * * cd $(pwd) && ./ssl/renew-smart.sh >> ssl/logs/renewal.log 2>&1") | crontab -
        echo -e "${GREEN}✅ Auto-renewal configured${NC}"
    else
        echo -e "${GREEN}✅ Auto-renewal already configured${NC}"
    fi
    
else
    echo -e "${RED}✗ Nginx configuration test failed${NC}"
    docker-compose logs --tail=10 nginx
    exit 1
fi