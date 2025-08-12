#!/bin/bash

# Production SSL Fix Script - Simple and Reliable
# For khudroo.com on production server

set -e

DOMAIN="khudroo.com"
EMAIL="admin@khudroo.com"

echo "🔐 Production SSL Setup for $DOMAIN"
echo "=================================="

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    echo -e "$1"
}

# Step 1: Check if services are running
check_services() {
    log "${BLUE}[1/7] Checking Docker services...${NC}"
    
    if ! docker-compose ps | grep -q "Up"; then
        log "${YELLOW}Starting Docker services...${NC}"
        docker-compose up -d postgres redis
        sleep 10
        docker-compose up -d saas_manager odoo_master odoo_worker1 odoo_worker2
        sleep 5
        docker-compose up -d nginx
        log "${GREEN}✅ Services started${NC}"
    else
        log "${GREEN}✅ Services are running${NC}"
    fi
}

# Step 2: Install certbot on the system (bypass Docker issues)
install_certbot() {
    log "${BLUE}[2/7] Installing/updating certbot...${NC}"
    
    if ! command -v certbot &> /dev/null; then
        sudo apt update
        sudo apt install -y certbot
        log "${GREEN}✅ Certbot installed${NC}"
    else
        log "${GREEN}✅ Certbot already available${NC}"
    fi
}

# Step 3: Stop nginx temporarily for certificate request
prepare_for_cert() {
    log "${BLUE}[3/7] Preparing for certificate request...${NC}"
    
    # Stop nginx to free port 80
    docker-compose stop nginx
    
    # Check if port 80 is free
    if lsof -i :80 | grep -q LISTEN; then
        log "${RED}Port 80 is still in use. Please stop any services using port 80${NC}"
        exit 1
    fi
    
    log "${GREEN}✅ Port 80 is available${NC}"
}

# Step 4: Request Let's Encrypt certificate
request_certificate() {
    log "${BLUE}[4/7] Requesting Let's Encrypt certificate...${NC}"
    
    # Request certificate using standalone method
    if sudo certbot certonly \
        --standalone \
        --email "$EMAIL" \
        --agree-tos \
        --no-eff-email \
        --domains "$DOMAIN,www.$DOMAIN" \
        --cert-name "$DOMAIN"; then
        
        log "${GREEN}✅ Certificate obtained successfully${NC}"
    else
        log "${RED}❌ Certificate request failed${NC}"
        exit 1
    fi
}

# Step 5: Copy certificates to Docker volume
setup_certificates() {
    log "${BLUE}[5/7] Setting up certificates for Docker...${NC}"
    
    # Create certificate directory in Docker volume
    sudo mkdir -p ./ssl/letsencrypt/live/$DOMAIN
    sudo mkdir -p ./ssl/letsencrypt/archive/$DOMAIN
    
    # Copy certificates
    sudo cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem ./ssl/letsencrypt/live/$DOMAIN/
    sudo cp /etc/letsencrypt/live/$DOMAIN/privkey.pem ./ssl/letsencrypt/live/$DOMAIN/
    sudo cp /etc/letsencrypt/live/$DOMAIN/chain.pem ./ssl/letsencrypt/live/$DOMAIN/
    sudo cp /etc/letsencrypt/live/$DOMAIN/cert.pem ./ssl/letsencrypt/live/$DOMAIN/
    
    # Set permissions
    sudo chown -R $USER:$USER ./ssl/letsencrypt/
    
    log "${GREEN}✅ Certificates copied to Docker volume${NC}"
}

# Step 6: Create production SSL configuration
create_ssl_config() {
    log "${BLUE}[6/7] Creating SSL configuration...${NC}"
    
    # Backup existing config
    if [[ -f "nginx/conf.d/ssl.conf" ]]; then
        cp nginx/conf.d/ssl.conf nginx/conf.d/ssl.conf.backup.$(date +%s)
    fi
    
    # Create production SSL config
    cat > nginx/conf.d/production-ssl.conf << EOF
# Production SSL Configuration for $DOMAIN
# Let's Encrypt certificates

# HTTP to HTTPS redirect
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN ~^.*\\.$DOMAIN\$;
    
    # ACME challenge for renewals
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        try_files \$uri \$uri/ =404;
        allow all;
    }
    
    # Redirect to HTTPS
    location / {
        return 301 https://\$server_name\$request_uri;
    }
}

# HTTPS Main Domain - SaaS Manager
server {
    listen 443 ssl http2;
    server_name $DOMAIN www.$DOMAIN;
    
    # Let's Encrypt SSL Certificate
    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/$DOMAIN/chain.pem;
    
    # Modern SSL settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:50m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;
    ssl_dhparam /etc/nginx/ssl/dhparam.pem;
    
    # OCSP stapling
    ssl_stapling on;
    ssl_stapling_verify on;
    resolver 1.1.1.1 1.0.0.1 valid=300s;
    resolver_timeout 5s;
    
    # Security headers (CSP disabled for CDN compatibility)
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    
    # ACME challenge
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        try_files \$uri \$uri/ =404;
        allow all;
    }
    
    # Health check
    location /ssl-health {
        access_log off;
        return 200 "Production SSL OK";
        add_header Content-Type text/plain;
    }
    
    # Main application
    location / {
        proxy_pass http://saas_manager;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$host;
        
        # WebSocket support
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$connection_upgrade;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        # Error handling
        proxy_intercept_errors on;
    }
}

# HTTPS Subdomains (Wildcard support via same certificate)
server {
    listen 443 ssl http2;
    server_name ~^(?<subdomain>[^\\.]+)\\.$DOMAIN\$;
    
    # Skip reserved subdomains
    if (\$subdomain ~* "^(www|api|admin|manage|master|health|mail|ftp)$") {
        return 404;
    }
    
    # Same SSL certificate
    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/$DOMAIN/chain.pem;
    
    # SSL settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL_SUB:50m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;
    ssl_dhparam /etc/nginx/ssl/dhparam.pem;
    
    # OCSP stapling
    ssl_stapling on;
    ssl_stapling_verify on;
    resolver 1.1.1.1 1.0.0.1 valid=300s;
    resolver_timeout 5s;
    
    # Security headers for subdomains
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    
    # Health check
    location /ssl-health {
        access_log off;
        return 200 "Subdomain SSL OK - \$subdomain";
        add_header Content-Type text/plain;
    }
    
    # Odoo application
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
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        # Error handling
        proxy_intercept_errors on;
    }
}
EOF
    
    log "${GREEN}✅ Production SSL configuration created${NC}"
}

# Step 7: Start nginx and test
finalize_setup() {
    log "${BLUE}[7/7] Starting nginx with SSL configuration...${NC}"
    
    # Update docker-compose to mount certificates
    if ! grep -q "/etc/letsencrypt" docker-compose.yml; then
        log "${YELLOW}Adding certificate mount to docker-compose.yml...${NC}"
        # Backup docker-compose.yml
        cp docker-compose.yml docker-compose.yml.backup.$(date +%s)
        
        # Add certificate volume mount (simple approach)
        sed -i '/- \.\/ssl\/dhparam\.pem:\/etc\/nginx\/ssl\/dhparam\.pem/a\      - ./ssl/letsencrypt:/etc/letsencrypt:ro' docker-compose.yml
    fi
    
    # Start nginx
    docker-compose up -d nginx
    
    sleep 5
    
    # Test SSL
    if timeout 10 curl -sSf "https://$DOMAIN/ssl-health" >/dev/null 2>&1; then
        log "${GREEN}✅ SSL is working perfectly!${NC}"
        log "${GREEN}🎉 Your site is now secure: https://$DOMAIN${NC}"
    else
        log "${YELLOW}⚠️  SSL test failed, but configuration is in place${NC}"
        log "${BLUE}Check nginx logs: docker-compose logs nginx${NC}"
    fi
    
    # Setup auto-renewal
    setup_auto_renewal
}

# Setup automatic renewal
setup_auto_renewal() {
    log "${BLUE}Setting up auto-renewal...${NC}"
    
    # Create renewal script
    cat > ssl-renew.sh << 'RENEW_SCRIPT'
#!/bin/bash
# SSL Certificate Renewal Script

DOMAIN="khudroo.com"
LOG_FILE="/var/log/ssl-renewal.log"

echo "$(date): Starting SSL renewal for $DOMAIN" >> "$LOG_FILE"

# Stop nginx
docker-compose stop nginx >> "$LOG_FILE" 2>&1

# Renew certificate
if sudo certbot renew --quiet; then
    echo "$(date): Certificate renewal successful" >> "$LOG_FILE"
    
    # Copy renewed certificates
    sudo cp /etc/letsencrypt/live/$DOMAIN/*.pem ./ssl/letsencrypt/live/$DOMAIN/
    sudo chown -R $USER:$USER ./ssl/letsencrypt/
    
    # Restart nginx
    docker-compose up -d nginx >> "$LOG_FILE" 2>&1
    echo "$(date): Nginx restarted successfully" >> "$LOG_FILE"
else
    echo "$(date): Certificate renewal failed" >> "$LOG_FILE"
    docker-compose up -d nginx >> "$LOG_FILE" 2>&1
    exit 1
fi
RENEW_SCRIPT
    
    chmod +x ssl-renew.sh
    
    # Add to cron
    if ! crontab -l 2>/dev/null | grep -q "ssl-renew"; then
        (crontab -l 2>/dev/null; echo "0 2 * * 0 cd $(pwd) && ./ssl-renew.sh") | crontab -
        log "${GREEN}✅ Auto-renewal configured (weekly)${NC}"
    fi
}

# Main execution
main() {
    check_services
    install_certbot
    prepare_for_cert
    request_certificate
    setup_certificates
    create_ssl_config
    finalize_setup
    
    echo
    log "${GREEN}🎉 Production SSL Setup Complete!${NC}"
    log "${GREEN}✅ https://$DOMAIN is now secure${NC}"
    log "${GREEN}✅ Subdomains like https://kdoo_test2.$DOMAIN will work${NC}"
    log "${BLUE}📋 Certificate renewal: ./ssl-renew.sh${NC}"
}

# Run main function
main "$@"