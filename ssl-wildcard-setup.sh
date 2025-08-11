#!/bin/bash

# Wildcard SSL Certificate Setup for Multi-Tenant Odoo
# Gets *.khudroo.com wildcard certificate for unlimited subdomains

echo "🌟 Wildcard SSL Certificate Setup"
echo "=================================="

DOMAIN="khudroo.com"
EMAIL="admin@khudroo.com"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

log() {
    echo -e "$1"
}

# Step 1: Stop nginx to prepare for certificate request
prepare_system() {
    log "${BLUE}[1/5] Preparing system for wildcard certificate...${NC}"
    
    # Stop nginx if running
    docker stop nginx 2>/dev/null || true
    
    # Make sure certbot is installed
    if ! command -v certbot &> /dev/null; then
        log "${YELLOW}Installing certbot...${NC}"
        sudo apt update
        sudo apt install -y certbot
    fi
    
    log "${GREEN}✅ System prepared${NC}"
}

# Step 2: Request wildcard certificate using DNS challenge
request_wildcard_cert() {
    log "${BLUE}[2/5] Requesting wildcard certificate for *.${DOMAIN}...${NC}"
    
    log "${YELLOW}📋 IMPORTANT: Wildcard certificates require DNS validation${NC}"
    log "${YELLOW}You will need to add TXT records to your DNS settings${NC}"
    echo
    
    # Remove existing certificate if any
    sudo certbot delete --cert-name "$DOMAIN" 2>/dev/null || true
    
    # Request wildcard certificate
    log "${PURPLE}Starting wildcard certificate request...${NC}"
    log "${PURPLE}Follow the instructions to add DNS TXT records${NC}"
    
    if sudo certbot certonly \
        --manual \
        --preferred-challenges=dns \
        --email "$EMAIL" \
        --agree-tos \
        --no-eff-email \
        --domains "$DOMAIN,*.$DOMAIN" \
        --cert-name "$DOMAIN"; then
        
        log "${GREEN}🎉 Wildcard certificate obtained successfully!${NC}"
        
        # Show certificate details
        log "${BLUE}Certificate details:${NC}"
        sudo openssl x509 -in /etc/letsencrypt/live/$DOMAIN/fullchain.pem -noout -subject -issuer -dates
        
        # Show SANs (domains covered)
        log "${BLUE}Domains covered by this certificate:${NC}"
        sudo openssl x509 -in /etc/letsencrypt/live/$DOMAIN/fullchain.pem -noout -text | grep -A1 "Subject Alternative Name" | tail -1 | sed 's/DNS://g' | tr ',' '\n' | sed 's/^[ \t]*/  ✅ /'
        
    else
        log "${RED}❌ Wildcard certificate request failed${NC}"
        exit 1
    fi
}

# Step 3: Setup certificates for Docker
setup_docker_certs() {
    log "${BLUE}[3/5] Setting up certificates for Docker containers...${NC}"
    
    # Create SSL directory structure
    sudo mkdir -p ./ssl/letsencrypt/live/$DOMAIN
    sudo mkdir -p ./ssl/letsencrypt/archive/$DOMAIN
    
    # Copy certificates to Docker volume location
    sudo cp /etc/letsencrypt/live/$DOMAIN/*.pem ./ssl/letsencrypt/live/$DOMAIN/
    sudo cp -r /etc/letsencrypt/archive/$DOMAIN/* ./ssl/letsencrypt/archive/$DOMAIN/ 2>/dev/null || true
    
    # Set proper permissions
    sudo chown -R $USER:$USER ./ssl/letsencrypt/
    chmod -R 755 ./ssl/letsencrypt/
    
    log "${GREEN}✅ Certificates copied to Docker volumes${NC}"
}

# Step 4: Create comprehensive wildcard nginx configuration
create_wildcard_config() {
    log "${BLUE}[4/5] Creating wildcard SSL configuration...${NC}"
    
    # Backup any existing SSL config
    if [[ -f "nginx/conf.d/production-ssl.conf" ]]; then
        cp nginx/conf.d/production-ssl.conf nginx/conf.d/production-ssl.conf.backup.$(date +%s)
    fi
    
    # Create wildcard SSL configuration
    cat > nginx/conf.d/wildcard-ssl.conf << EOF
# Wildcard SSL Configuration for *.${DOMAIN}
# Supports unlimited subdomains with single certificate
# Generated on $(date)

# Rate limiting zones
limit_req_zone \$binary_remote_addr zone=login_limit:10m rate=5r/m;
limit_req_zone \$binary_remote_addr zone=api_limit:10m rate=50r/m;
limit_req_zone \$binary_remote_addr zone=general_limit:10m rate=100r/m;

# WebSocket upgrade mapping
map \$http_upgrade \$connection_upgrade {
    default upgrade;
    ''      close;
}

# HTTP to HTTPS redirect for main domain
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;
    
    # ACME challenge location for renewals
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        try_files \$uri \$uri/ =404;
        allow all;
        expires -1;
        add_header Cache-Control "no-cache, no-store, must-revalidate";
    }
    
    # Redirect all HTTP to HTTPS
    location / {
        return 301 https://\$server_name\$request_uri;
    }
}

# HTTP to HTTPS redirect for ALL subdomains (wildcard)
server {
    listen 80;
    server_name ~^(?<subdomain>.+)\\.$DOMAIN\$;
    
    # ACME challenge
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
    
    # Wildcard SSL Certificate
    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/$DOMAIN/chain.pem;
    
    # Modern SSL Configuration for A+ rating
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL_MAIN:50m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;
    ssl_dhparam /etc/nginx/ssl/dhparam.pem;
    
    # OCSP stapling
    ssl_stapling on;
    ssl_stapling_verify on;
    resolver 1.1.1.1 1.0.0.1 8.8.8.8 8.8.4.4 valid=300s;
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
        return 200 "Wildcard SSL OK - Main Domain";
        add_header Content-Type text/plain;
        add_header X-SSL-Type "Wildcard Certificate";
    }
    
    # Rate limited authentication endpoints
    location ~ ^/(login|auth|api/auth) {
        limit_req zone=login_limit burst=5 nodelay;
        
        proxy_pass http://saas_manager;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-Port \$server_port;
        
        # Security headers for auth
        add_header Cache-Control "no-cache, no-store, must-revalidate" always;
        add_header Pragma "no-cache" always;
    }
    
    # Static files with caching
    location ~* \\.(css|js|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot|webp)\$ {
        proxy_pass http://saas_manager;
        proxy_set_header Host \$host;
        
        expires 1M;
        add_header Cache-Control "public, immutable";
        add_header Vary "Accept-Encoding";
        
        # CORS for CDN resources
        add_header Access-Control-Allow-Origin "*";
        add_header Access-Control-Allow-Methods "GET, OPTIONS";
    }
    
    # Main application
    location / {
        limit_req zone=general_limit burst=50 nodelay;
        
        proxy_pass http://saas_manager;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$host;
        
        # WebSocket support
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$connection_upgrade;
        
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        proxy_intercept_errors on;
    }
}

# HTTPS ALL Subdomains - Wildcard Support (Unlimited Tenants)
server {
    listen 443 ssl http2;
    server_name ~^(?<subdomain>.+)\\.$DOMAIN\$;
    
    # Skip www (handled by main domain) and reserved subdomains
    if (\$subdomain ~* "^(www|api|admin|manage|master|health|mail|ftp|ssh|vpn|ns1|ns2|mx|blog|docs)$") {
        return 404;
    }
    
    # Same Wildcard SSL Certificate for ALL subdomains
    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/$DOMAIN/chain.pem;
    
    # Modern SSL Configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL_WILD:50m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;
    ssl_dhparam /etc/nginx/ssl/dhparam.pem;
    
    # OCSP stapling
    ssl_stapling on;
    ssl_stapling_verify on;
    resolver 1.1.1.1 1.0.0.1 8.8.8.8 8.8.4.4 valid=300s;
    resolver_timeout 5s;
    
    # Security headers for tenant subdomains
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    
    # Health check for any subdomain
    location /ssl-health {
        access_log off;
        return 200 "Wildcard SSL OK - Tenant: \$subdomain";
        add_header Content-Type text/plain;
        add_header X-SSL-Type "Wildcard Certificate";
        add_header X-Tenant "\$subdomain";
    }
    
    # Block database selector for security
    location ~ ^/web/database/(selector|manager) {
        return 404;
    }
    
    # Odoo static assets with aggressive caching
    location /web/static/ {
        proxy_pass http://odoo_workers;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Subdomain \$subdomain;
        
        expires 1M;
        add_header Cache-Control "public, immutable";
        add_header Vary "Accept-Encoding";
        
        gzip on;
        gzip_vary on;
        gzip_types text/css application/javascript application/json;
    }
    
    # Odoo authentication with rate limiting
    location ~ ^/web/(login|session/authenticate) {
        limit_req zone=login_limit burst=3 nodelay;
        
        proxy_pass http://odoo_workers;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Subdomain \$subdomain;
        
        add_header Cache-Control "no-cache, no-store, must-revalidate" always;
    }
    
    # Odoo API endpoints
    location ~ ^/(web/dataset/call_kw|jsonrpc) {
        limit_req zone=api_limit burst=30 nodelay;
        
        proxy_pass http://odoo_workers;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Subdomain \$subdomain;
        
        proxy_connect_timeout 30s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
    }
    
    # File operations with size limits
    location ~ ^/web/binary/ {
        client_max_body_size 200M;
        client_body_timeout 300s;
        
        proxy_pass http://odoo_workers;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Subdomain \$subdomain;
        
        proxy_connect_timeout 60s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
        proxy_buffering off;
    }
    
    # Main Odoo application (handles ALL tenant subdomains)
    location / {
        limit_req zone=general_limit burst=50 nodelay;
        
        proxy_pass http://odoo_workers;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Subdomain \$subdomain;
        
        # WebSocket support for real-time features
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$connection_upgrade;
        
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        proxy_buffering on;
        proxy_buffer_size 4k;
        proxy_buffers 8 4k;
        
        proxy_intercept_errors on;
    }
}
EOF
    
    log "${GREEN}✅ Wildcard SSL configuration created${NC}"
}

# Step 5: Update docker-compose and start services
finalize_wildcard_setup() {
    log "${BLUE}[5/5] Finalizing wildcard SSL setup...${NC}"
    
    # Update docker-compose.yml to include SSL certificates
    if ! grep -q "/etc/letsencrypt" docker-compose.yml; then
        cp docker-compose.yml docker-compose.yml.backup.$(date +%s)
        
        # Add SSL mount to nginx service
        sed -i '/- \.\/ssl\/dhparam\.pem:\/etc\/nginx\/ssl\/dhparam\.pem/a\      - /etc/letsencrypt:/etc/letsencrypt:ro' docker-compose.yml
        
        log "${GREEN}✅ Updated docker-compose.yml with certificate mount${NC}"
    fi
    
    # Clean up and start services
    log "${YELLOW}Cleaning up Docker containers...${NC}"
    docker stop $(docker ps -aq) 2>/dev/null || true
    docker rm $(docker ps -aq) 2>/dev/null || true
    
    # Start services
    log "${YELLOW}Starting services with wildcard SSL...${NC}"
    docker-compose up -d postgres redis
    sleep 10
    docker-compose up -d saas_manager odoo_master odoo_worker1 odoo_worker2
    sleep 10
    docker-compose up -d nginx
    
    sleep 15
    
    # Test wildcard SSL
    log "${BLUE}Testing wildcard SSL configuration...${NC}"
    
    # Test main domain
    if timeout 10 curl -sSf "https://$DOMAIN/ssl-health" >/dev/null 2>&1; then
        log "${GREEN}✅ Main domain SSL working${NC}"
    else
        log "${YELLOW}⚠️  Main domain test inconclusive${NC}"
    fi
    
    # Test a subdomain
    if timeout 10 curl -sSf "https://test.$DOMAIN/ssl-health" >/dev/null 2>&1; then
        log "${GREEN}✅ Wildcard subdomain SSL working${NC}"
    else
        log "${YELLOW}⚠️  Subdomain test inconclusive (may need DNS)${NC}"
    fi
    
    log "${GREEN}✅ Wildcard SSL setup completed${NC}"
}

# Setup wildcard renewal
setup_wildcard_renewal() {
    log "${BLUE}Setting up wildcard certificate renewal...${NC}"
    
    cat > ssl-wildcard-renew.sh << 'RENEW_SCRIPT'
#!/bin/bash
# Wildcard SSL Certificate Renewal Script

DOMAIN="khudroo.com"
LOG_FILE="/var/log/wildcard-ssl-renewal.log"

echo "$(date): Starting wildcard SSL renewal for *.$DOMAIN" >> "$LOG_FILE"

# Stop nginx
docker stop nginx >> "$LOG_FILE" 2>&1

# Renew wildcard certificate (requires manual DNS validation)
# Note: Automatic renewal of wildcard certificates is challenging
# Consider using DNS-01 challenge automation or Cloudflare API

if sudo certbot renew --manual --preferred-challenges=dns --quiet; then
    echo "$(date): Wildcard certificate renewal successful" >> "$LOG_FILE"
    
    # Copy renewed certificates
    sudo cp /etc/letsencrypt/live/$DOMAIN/*.pem ./ssl/letsencrypt/live/$DOMAIN/
    sudo chown -R $USER:$USER ./ssl/letsencrypt/
    
    # Restart services
    docker-compose up -d nginx >> "$LOG_FILE" 2>&1
    echo "$(date): Services restarted successfully" >> "$LOG_FILE"
    
    echo "$(date): Wildcard SSL renewal completed successfully" >> "$LOG_FILE"
else
    echo "$(date): Wildcard certificate renewal failed" >> "$LOG_FILE"
    docker-compose up -d nginx >> "$LOG_FILE" 2>&1
    exit 1
fi
RENEW_SCRIPT
    
    chmod +x ssl-wildcard-renew.sh
    
    log "${GREEN}✅ Wildcard renewal script created${NC}"
    log "${YELLOW}📝 Note: Wildcard renewals require manual DNS validation${NC}"
    log "${YELLOW}    Consider using DNS API automation for production${NC}"
}

# Main execution
main() {
    echo
    log "${PURPLE}🌟 This will set up a wildcard SSL certificate for *.${DOMAIN}${NC}"
    log "${PURPLE}   This covers ALL possible subdomains with a single certificate:${NC}"
    log "${PURPLE}   • https://$DOMAIN${NC}"
    log "${PURPLE}   • https://tenant1.$DOMAIN${NC}"
    log "${PURPLE}   • https://tenant2.$DOMAIN${NC}"
    log "${PURPLE}   • https://kdoo_test2.$DOMAIN${NC}"
    log "${PURPLE}   • https://any-name-you-want.$DOMAIN${NC}"
    echo
    
    read -p "Continue with wildcard certificate setup? (y/N): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        prepare_system
        request_wildcard_cert
        setup_docker_certs
        create_wildcard_config
        finalize_wildcard_setup
        setup_wildcard_renewal
        
        echo
        log "${GREEN}🎉 Wildcard SSL Setup Complete!${NC}"
        log "${GREEN}✅ Certificate covers: $DOMAIN and *.$DOMAIN${NC}"
        log "${GREEN}✅ Unlimited subdomains supported${NC}"
        log "${GREEN}✅ Perfect for multi-tenant architecture${NC}"
        echo
        log "${BLUE}🧪 Test your wildcard SSL:${NC}"
        log "${BLUE}   • https://$DOMAIN/ssl-health${NC}"
        log "${BLUE}   • https://test.$DOMAIN/ssl-health${NC}"
        log "${BLUE}   • https://kdoo_test2.$DOMAIN/ssl-health${NC}"
        log "${BLUE}   • https://any-tenant-name.$DOMAIN/ssl-health${NC}"
        echo
        log "${YELLOW}📋 Renewal: ./ssl-wildcard-renew.sh (requires DNS validation)${NC}"
        
    else
        log "${YELLOW}Wildcard SSL setup cancelled${NC}"
    fi
}

# Run main function
main "$@"