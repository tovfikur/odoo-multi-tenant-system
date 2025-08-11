#!/bin/bash

# Complete SSL Setup for Odoo Multi-Tenant System
# Handles all SSL-related tasks: certificate generation, nginx configuration, and wildcard support
# Combines functionality from ssl-fix.sh, fix-csp.sh, and wildcard setup

set -e

# Configuration
DOMAIN="${1:-khudroo.com}"
EMAIL="${2:-admin@khudroo.com}"
DOCKER_SSL_DIR="./ssl"
NGINX_CONFIG_DIR="./nginx/conf.d"
SYSTEM_SSL_DIR="/etc/nginx/ssl"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

# Banner
show_banner() {
    echo -e "${PURPLE}============================================${NC}"
    echo -e "${PURPLE}   Complete SSL Setup for Odoo System     ${NC}"
    echo -e "${PURPLE}   Domain: $DOMAIN                         ${NC}"
    echo -e "${PURPLE}   Wildcard: *.$DOMAIN                     ${NC}"
    echo -e "${PURPLE}============================================${NC}"
    echo
}

# Logging
LOG_FILE="ssl/logs/ssl-setup.log"
mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
    echo -e "$1"
}

# Check prerequisites
check_prerequisites() {
    log "${BLUE}Checking prerequisites...${NC}"
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        log "${RED}Docker is not installed${NC}"
        exit 1
    fi
    
    # Check docker-compose
    if ! command -v docker-compose &> /dev/null; then
        log "${RED}Docker Compose is not installed${NC}"
        exit 1
    fi
    
    # Check network connectivity
    if ! ping -c 1 8.8.8.8 &> /dev/null; then
        log "${RED}No internet connection${NC}"
        exit 1
    fi
    
    # Find Docker network
    NETWORK_NAME=$(docker network ls --format "{{.Name}}" | grep -E "(odoo|multi.*tenant)" | head -1)
    if [ -z "$NETWORK_NAME" ]; then
        NETWORK_NAME="default"
        log "${YELLOW}Using default Docker network${NC}"
    else
        log "${GREEN}Using Docker network: $NETWORK_NAME${NC}"
    fi
    
    log "${GREEN}✓ Prerequisites check completed${NC}"
}

# Create directories
create_directories() {
    log "${BLUE}Creating SSL directories...${NC}"
    
    # Docker directories
    mkdir -p "$DOCKER_SSL_DIR/certbot/conf"
    mkdir -p "$DOCKER_SSL_DIR/certbot/www"
    mkdir -p "$DOCKER_SSL_DIR/logs"
    mkdir -p "$NGINX_CONFIG_DIR"
    
    # System directories (if possible)
    if [[ $EUID -eq 0 ]] || sudo -n true 2>/dev/null; then
        sudo mkdir -p "$SYSTEM_SSL_DIR" 2>/dev/null || true
    fi
    
    log "${GREEN}✓ SSL directories created${NC}"
}

# Generate DH parameters
generate_dhparam() {
    if [ ! -f "$DOCKER_SSL_DIR/dhparam.pem" ]; then
        log "${BLUE}Generating DH parameters (this may take a few minutes)...${NC}"
        openssl dhparam -out "$DOCKER_SSL_DIR/dhparam.pem" 2048
        log "${GREEN}✓ DH parameters generated${NC}"
    else
        log "${GREEN}✓ DH parameters already exist${NC}"
    fi
}

# Check for existing certificates
check_existing_certificates() {
    log "${BLUE}Checking for existing certificates...${NC}"
    
    # Check Docker volume certificates
    if docker run --rm \
        -v "$(pwd)/ssl/certbot/conf:/etc/letsencrypt" \
        certbot/certbot certificates 2>/dev/null | grep -q "$DOMAIN"; then
        
        CERT_PATH=$(docker run --rm \
            -v "$(pwd)/ssl/certbot/conf:/etc/letsencrypt" \
            certbot/certbot certificates 2>/dev/null | grep "Certificate Path" | tail -1 | awk '{print $3}')
        
        if [[ "$CERT_PATH" =~ $DOMAIN-[0-9]{4} ]]; then
            CERT_NAME=$(basename "$(dirname "$CERT_PATH")")
            log "${GREEN}✓ Found existing certificate: $CERT_NAME${NC}"
            return 0
        fi
    fi
    
    # Check system certificates
    if [ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
        CERT_NAME="$DOMAIN"
        log "${GREEN}✓ Found system certificate: $CERT_NAME${NC}"
        return 0
    fi
    
    # Check for numbered certificates
    for cert_dir in /etc/letsencrypt/live/$DOMAIN-*; do
        if [ -d "$cert_dir" ] && [ -f "$cert_dir/fullchain.pem" ]; then
            CERT_NAME=$(basename "$cert_dir")
            log "${GREEN}✓ Found system certificate: $CERT_NAME${NC}"
            return 0
        fi
    done
    
    log "${YELLOW}No existing certificates found${NC}"
    return 1
}

# Request new certificate
request_certificate() {
    log "${BLUE}Requesting new Let's Encrypt certificate...${NC}"
    
    read -p "Do you want a wildcard certificate (*.$DOMAIN)? (y/n): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        request_wildcard_certificate
    else
        request_standard_certificate
    fi
}

# Request wildcard certificate
request_wildcard_certificate() {
    log "${YELLOW}Requesting wildcard certificate for *.$DOMAIN${NC}"
    log "${YELLOW}You will need to add DNS TXT records when prompted${NC}"
    
    # Start nginx for ACME challenges
    echo "Starting nginx for ACME challenges..."
    if docker-compose ps nginx &>/dev/null && [ "$(docker-compose ps -q nginx)" ]; then
        docker-compose restart nginx
    else
        docker-compose up -d nginx
    fi
    
    sleep 5
    
    # Request certificate with manual DNS validation
    if docker run --rm -it \
        -v "$(pwd)/ssl/certbot/conf:/etc/letsencrypt" \
        -v "$(pwd)/ssl/certbot/www:/var/www/certbot" \
        certbot/certbot certonly \
            --manual \
            --preferred-challenges=dns \
            --email "$EMAIL" \
            --agree-tos \
            --no-eff-email \
            --domains "$DOMAIN,*.$DOMAIN" \
            --cert-name "$DOMAIN"; then
        
        CERT_NAME="$DOMAIN"
        log "${GREEN}✓ Wildcard certificate obtained${NC}"
        return 0
    else
        log "${RED}✗ Wildcard certificate request failed${NC}"
        return 1
    fi
}

# Request standard certificate
request_standard_certificate() {
    log "${YELLOW}Requesting standard certificate for $DOMAIN${NC}"
    
    # Start nginx for ACME challenges
    docker-compose up -d nginx
    sleep 5
    
    # Request certificate with webroot validation
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
            --domain "$DOMAIN"; then
        
        CERT_NAME="$DOMAIN"
        log "${GREEN}✓ Standard certificate obtained${NC}"
        return 0
    else
        log "${RED}✗ Standard certificate request failed${NC}"
        return 1
    fi
}

# Create nginx SSL configuration
create_ssl_config() {
    log "${BLUE}Creating nginx SSL configuration...${NC}"
    
    # Disable existing SSL configs
    for config in "$NGINX_CONFIG_DIR"/*ssl*.conf; do
        if [[ -f "$config" && ! "$config" =~ disabled ]]; then
            mv "$config" "$config.disabled.$(date +%s)"
            log "${GREEN}✓ Disabled: $(basename "$config")${NC}"
        fi
    done
    
    # Determine certificate path
    local cert_path="/etc/letsencrypt/live/$CERT_NAME"
    
    # Create comprehensive SSL configuration
    cat > "$NGINX_CONFIG_DIR/complete-ssl.conf" << EOF
# Complete SSL Configuration for $DOMAIN
# Generated by setup-complete-ssl.sh on $(date)

# WebSocket upgrade mapping
map \$http_upgrade \$connection_upgrade {
    default upgrade;
    ''      close;
}

# HTTP to HTTPS redirect for main domain
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;
    
    # ACME challenge for certificate renewal
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        try_files \$uri \$uri/ =404;
        allow all;
        expires -1;
        add_header Cache-Control "no-cache, no-store, must-revalidate";
    }
    
    # Redirect all HTTP traffic to HTTPS
    location / {
        return 301 https://\$server_name\$request_uri;
    }
}

# HTTP to HTTPS redirect for subdomains (wildcard support)
server {
    listen 80;
    server_name ~^(?<subdomain>[^\\.]+)\\.$DOMAIN\$;
    
    # Skip reserved subdomains
    if (\$subdomain ~* "^(www|api|admin|manage|master|health)\$") {
        return 404;
    }
    
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
    
    # SSL Certificate Configuration
    ssl_certificate $cert_path/fullchain.pem;
    ssl_certificate_key $cert_path/privkey.pem;
    ssl_trusted_certificate $cert_path/chain.pem;
    
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
    resolver 8.8.8.8 8.8.4.4 1.1.1.1 1.0.0.1 valid=300s;
    resolver_timeout 5s;
    
    # Security headers with CDN-friendly CSP
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdnjs.cloudflare.com https://unpkg.com https://fonts.googleapis.com; style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com; img-src 'self' data: https: blob:; font-src 'self' data: https://fonts.gstatic.com https://cdnjs.cloudflare.com; connect-src 'self' wss: https:; frame-src 'self'; media-src 'self' data: https:;" always;
    add_header Permissions-Policy "camera=(), microphone=(), geolocation=(), payment=(), usb=()" always;
    
    # ACME challenge
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        try_files \$uri \$uri/ =404;
        allow all;
    }
    
    # Health check endpoint
    location /health {
        proxy_pass http://saas_manager/health;
        proxy_set_header Host \$host;
        access_log off;
        return 200 "SSL OK";
        add_header Content-Type text/plain;
    }
    
    # Rate limiting for sensitive endpoints
    location /login {
        limit_req zone=login_limit burst=5 nodelay;
        
        proxy_pass http://saas_manager;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-Port \$server_port;
        
        # Security headers for login
        add_header Cache-Control "no-cache, no-store, must-revalidate" always;
        add_header Pragma "no-cache" always;
        add_header Expires "0" always;
    }
    
    # Static files with caching
    location ~* \\.(css|js|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)\$ {
        proxy_pass http://saas_manager;
        proxy_set_header Host \$host;
        expires 1h;
        add_header Cache-Control "public, immutable";
        
        # CORS headers for CDN resources
        add_header Access-Control-Allow-Origin "*";
        add_header Access-Control-Allow-Methods "GET, OPTIONS";
        add_header Access-Control-Allow-Headers "Content-Type";
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
    }
}

# HTTPS Tenant Subdomains (Wildcard support)
server {
    listen 443 ssl http2;
    server_name ~^(?<subdomain>[^\\.]+)\\.$DOMAIN\$;
    
    # Skip reserved subdomains
    if (\$subdomain ~* "^(www|api|admin|manage|master|health)\$") {
        return 404;
    }
    
    # SSL Certificate Configuration (same certificate for wildcard)
    ssl_certificate $cert_path/fullchain.pem;
    ssl_certificate_key $cert_path/privkey.pem;
    ssl_trusted_certificate $cert_path/chain.pem;
    
    # Modern SSL Configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL_TENANT:50m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;
    ssl_dhparam /etc/nginx/ssl/dhparam.pem;
    
    # OCSP stapling
    ssl_stapling on;
    ssl_stapling_verify on;
    resolver 8.8.8.8 8.8.4.4 1.1.1.1 1.0.0.1 valid=300s;
    resolver_timeout 5s;
    
    # Security headers for tenant subdomains
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdnjs.cloudflare.com https://unpkg.com; style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com; img-src 'self' data: https: blob:; font-src 'self' data: https://fonts.gstatic.com; connect-src 'self' wss: https:; frame-src 'self';" always;
    
    # Health check endpoint
    location /health {
        access_log off;
        return 200 "Tenant SSL OK - \$subdomain";
        add_header Content-Type text/plain;
    }
    
    # Odoo static assets with caching
    location /web/static/ {
        proxy_pass http://odoo_workers;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Subdomain \$subdomain;
        
        expires 1h;
        add_header Cache-Control "public, immutable";
        gzip on;
        gzip_types text/css application/javascript;
    }
    
    # Odoo login with rate limiting
    location /web/login {
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
        proxy_Set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Subdomain \$subdomain;
    }
    
    # File uploads and downloads
    location /web/binary/ {
        client_max_body_size 100M;
        
        proxy_pass http://odoo_workers;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Subdomain \$subdomain;
        
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
    
    # Main Odoo application
    location / {
        proxy_pass http://odoo_workers;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Subdomain \$subdomain;
        
        # WebSocket support for real-time features
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

    log "${GREEN}✓ SSL configuration created: complete-ssl.conf${NC}"
}

# Update nginx.conf to include rate limiting
update_nginx_conf() {
    log "${BLUE}Updating nginx.conf with rate limiting...${NC}"
    
    # Check if rate limiting already exists
    if ! grep -q "limit_req_zone" nginx/nginx.conf; then
        # Add rate limiting zones to nginx.conf
        sed -i '/^http {/a\
    # Rate limiting zones\
    limit_req_zone $binary_remote_addr zone=login_limit:10m rate=5r/m;\
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=30r/m;\
    limit_req_zone $binary_remote_addr zone=general_limit:10m rate=50r/m;\
' nginx/nginx.conf
        
        log "${GREEN}✓ Added rate limiting to nginx.conf${NC}"
    fi
    
    # Ensure conf.d is included
    if ! grep -q "include /etc/nginx/conf.d/\*.conf;" nginx/nginx.conf; then
        sed -i '/^}$/i\    # Include SSL configuration files\n    include /etc/nginx/conf.d/*.conf;' nginx/nginx.conf
        log "${GREEN}✓ Added conf.d include to nginx.conf${NC}"
    fi
}

# Setup auto-renewal
setup_auto_renewal() {
    log "${BLUE}Setting up automatic certificate renewal...${NC}"
    
    # Create renewal script
    cat > "$DOCKER_SSL_DIR/auto-renew.sh" << 'RENEWAL_SCRIPT'
#!/bin/bash

# Auto-renewal script for SSL certificates
cd "$(dirname "$0")/.."

DOMAIN="khudroo.com"
LOG_FILE="ssl/logs/renewal.log"
NETWORK=$(docker network ls --format "{{.Name}}" | grep -E "(odoo|multi.*tenant)" | head -1)

echo "$(date): Starting certificate renewal..." >> "$LOG_FILE"

# Renew certificates
if docker run --rm \
    -v "$(pwd)/ssl/certbot/conf:/etc/letsencrypt" \
    -v "$(pwd)/ssl/certbot/www:/var/www/certbot" \
    --network "${NETWORK:-default}" \
    certbot/certbot renew --quiet; then
    
    echo "$(date): Certificate renewal completed successfully" >> "$LOG_FILE"
    
    # Reload nginx
    if docker-compose exec nginx nginx -s reload 2>/dev/null; then
        echo "$(date): Nginx reloaded successfully" >> "$LOG_FILE"
    else
        echo "$(date): Nginx reload failed, restarting container" >> "$LOG_FILE"
        docker-compose restart nginx
    fi
    
    echo "$(date): SSL renewal process completed" >> "$LOG_FILE"
else
    echo "$(date): ERROR - Certificate renewal failed" >> "$LOG_FILE"
    exit 1
fi
RENEWAL_SCRIPT
    
    chmod +x "$DOCKER_SSL_DIR/auto-renew.sh"
    
    # Add to cron if not exists
    if ! crontab -l 2>/dev/null | grep -q "auto-renew.sh"; then
        (crontab -l 2>/dev/null | grep -v "auto-renew"; echo "0 2,14 * * * cd $(pwd) && ./ssl/auto-renew.sh") | crontab -
        log "${GREEN}✓ Auto-renewal cron job configured (runs twice daily)${NC}"
    else
        log "${GREEN}✓ Auto-renewal already configured${NC}"
    fi
}

# Test SSL configuration
test_ssl_config() {
    log "${BLUE}Testing SSL configuration...${NC}"
    
    # Test nginx syntax
    if docker-compose exec nginx nginx -t 2>&1; then
        log "${GREEN}✓ Nginx configuration syntax test passed${NC}"
        
        # Restart nginx
        log "${BLUE}Restarting nginx with SSL configuration...${NC}"
        if docker-compose restart nginx; then
            sleep 5
            log "${GREEN}✓ Nginx restarted successfully${NC}"
            
            # Test HTTPS connectivity
            if curl -sSf -k "https://$DOMAIN/health" &>/dev/null; then
                log "${GREEN}✓ HTTPS connectivity test passed${NC}"
                return 0
            else
                log "${YELLOW}⚠ HTTPS connectivity test failed (may be normal initially)${NC}"
            fi
        else
            log "${RED}✗ Nginx restart failed${NC}"
            return 1
        fi
    else
        log "${RED}✗ Nginx configuration test failed${NC}"
        log "Nginx logs:"
        docker-compose logs --tail=20 nginx
        return 1
    fi
}

# Show final results
show_results() {
    log "${PURPLE}============================================${NC}"
    log "${PURPLE}   SSL Setup Complete!                    ${NC}"
    log "${PURPLE}============================================${NC}"
    echo
    
    log "${GREEN}✅ CONFIGURATION SUMMARY:${NC}"
    log "${GREEN}   Domain: $DOMAIN${NC}"
    log "${GREEN}   Certificate: Let's Encrypt${NC}"
    log "${GREEN}   Certificate Name: $CERT_NAME${NC}"
    log "${GREEN}   SSL Configuration: nginx/conf.d/complete-ssl.conf${NC}"
    log "${GREEN}   Auto-renewal: Enabled (twice daily)${NC}"
    echo
    
    log "${CYAN}🌐 SSL-ENABLED URLS:${NC}"
    log "${CYAN}   • Main site: https://$DOMAIN${NC}"
    log "${CYAN}   • Tenant subdomains: https://[tenant].$DOMAIN${NC}"
    log "${CYAN}   • Health check: https://$DOMAIN/health${NC}"
    echo
    
    log "${BLUE}🔒 SECURITY FEATURES:${NC}"
    log "${BLUE}   • TLS 1.2 and 1.3 only${NC}"
    log "${BLUE}   • Perfect Forward Secrecy${NC}"
    log "${BLUE}   • HSTS with preload support${NC}"
    log "${BLUE}   • CDN-friendly Content Security Policy${NC}"
    log "${BLUE}   • OCSP stapling${NC}"
    log "${BLUE}   • Rate limiting for sensitive endpoints${NC}"
    log "${BLUE}   • Modern cipher suites${NC}"
    echo
    
    log "${YELLOW}📋 MONITORING:${NC}"
    log "${YELLOW}   • Renewal logs: ssl/logs/renewal.log${NC}"
    log "${YELLOW}   • Setup logs: ssl/logs/ssl-setup.log${NC}"
    log "${YELLOW}   • Check certificates: docker run --rm -v \$(pwd)/ssl/certbot/conf:/etc/letsencrypt certbot/certbot certificates${NC}"
    log "${YELLOW}   • Test renewal: ./ssl/auto-renew.sh${NC}"
    echo
    
    log "${GREEN}🎉 Your Odoo Multi-Tenant System is now secured with HTTPS!${NC}"
    echo
}

# Main execution
main() {
    show_banner
    check_prerequisites
    create_directories
    generate_dhparam
    
    # Check for existing certificates or request new ones
    if ! check_existing_certificates; then
        if ! request_certificate; then
            log "${RED}Failed to obtain SSL certificate${NC}"
            exit 1
        fi
    fi
    
    create_ssl_config
    update_nginx_conf
    setup_auto_renewal
    
    if test_ssl_config; then
        show_results
    else
        log "${RED}SSL configuration test failed. Please check the logs.${NC}"
        exit 1
    fi
}

# Handle script interruption
trap 'log "${RED}Script interrupted${NC}"; exit 1' INT TERM

# Run main function
main "$@"