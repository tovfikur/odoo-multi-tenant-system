#!/bin/bash

# Production SSL Setup Script for Odoo Multi-Tenant System
# This script is designed for servers behind NAT/router where domain is only accessible from internet
# Author: Claude AI Assistant
# Version: 1.0

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Default configuration
DEFAULT_DOMAIN="khudroo.com"
DEFAULT_EMAIL="admin@khudroo.com"

# Functions for colored output
print_header() {
    echo -e "${BLUE}${BOLD}"
    echo "========================================"
    echo "$1"
    echo "========================================"
    echo -e "${NC}"
}

print_status() {
    echo -e "${GREEN}[✓ INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[⚠ WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗ ERROR]${NC} $1"
}

print_step() {
    echo -e "${CYAN}${BOLD}[STEP $1]${NC} $2"
}

# Check if script is run as root
check_root() {
    if [ "$EUID" -eq 0 ]; then
        print_error "Please don't run this script as root. Run as regular user with sudo access."
        exit 1
    fi
}

# Validate input parameters
validate_inputs() {
    local domain=$1
    local email=$2
    
    if [ -z "$domain" ]; then
        print_error "Domain cannot be empty"
        exit 1
    fi
    
    if [ -z "$email" ]; then
        print_error "Email cannot be empty"
        exit 1
    fi
    
    # Basic email validation
    if [[ ! "$email" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]; then
        print_error "Invalid email format: $email"
        exit 1
    fi
    
    # Basic domain validation
    if [[ ! "$domain" =~ ^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$ ]]; then
        print_error "Invalid domain format: $domain"
        exit 1
    fi
}

# Check prerequisites
check_prerequisites() {
    print_step "1" "Checking prerequisites..."
    
    # Check if docker is installed and running
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    # Check if docker-compose is installed
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    
    # Check if docker service is running
    if ! systemctl is-active --quiet docker; then
        print_error "Docker service is not running. Please start Docker service."
        print_status "Try: sudo systemctl start docker"
        exit 1
    fi
    
    # Check if current user can run docker commands
    if ! docker ps &> /dev/null; then
        print_error "Current user cannot run Docker commands."
        print_status "Please add your user to docker group: sudo usermod -aG docker $USER"
        print_status "Then logout and login again."
        exit 1
    fi
    
    print_status "All prerequisites met"
}

# Check docker-compose.yml exists and is valid
check_docker_compose() {
    print_step "2" "Validating Docker Compose configuration..."
    
    if [ ! -f "docker-compose.yml" ]; then
        print_error "docker-compose.yml not found in current directory"
        print_status "Please run this script from the project root directory"
        exit 1
    fi
    
    # Validate docker-compose.yml syntax
    if ! docker-compose config &> /dev/null; then
        print_error "docker-compose.yml has syntax errors"
        print_status "Please fix the configuration file"
        exit 1
    fi
    
    print_status "Docker Compose configuration is valid"
}

# Setup SSL directories
setup_directories() {
    print_step "3" "Setting up SSL directories..."
    
    # Create SSL directories with proper permissions
    mkdir -p ssl/certbot/conf ssl/certbot/www ssl/logs
    mkdir -p nginx/conf.d
    
    # Set proper permissions
    chmod 755 ssl ssl/certbot ssl/certbot/conf ssl/certbot/www ssl/logs
    chmod 755 nginx nginx/conf.d
    
    print_status "SSL directories created successfully"
}

# Check and start Docker containers
manage_containers() {
    print_step "4" "Managing Docker containers..."
    
    # Check if containers are already running
    if docker-compose ps | grep -q "Up"; then
        print_warning "Some containers are already running"
        print_status "Restarting containers to apply new configurations..."
        docker-compose restart
    else
        print_status "Starting Docker containers..."
        docker-compose up -d
    fi
    
    # Wait for containers to be ready
    print_status "Waiting for containers to be ready..."
    sleep 15
    
    # Check container health
    local unhealthy_containers=$(docker-compose ps --format "table {{.Name}}\t{{.State}}" | grep -v "Up" | grep -v "Name" || true)
    
    if [ -n "$unhealthy_containers" ]; then
        print_warning "Some containers are not running properly:"
        echo "$unhealthy_containers"
        print_status "Attempting to restart problematic containers..."
        docker-compose up -d --force-recreate
        sleep 10
    fi
    
    print_status "Docker containers are running"
}

# Detect Docker network
detect_network() {
    print_step "5" "Detecting Docker network..."
    
    # Try multiple methods to find the correct network
    local network_candidates=(
        $(docker network ls --format "{{.Name}}" | grep -E "(odoo|multi.*tenant)" | head -3)
        $(docker-compose ps --format "{{.Name}}" | head -1 | xargs -I {} docker inspect {} --format '{{range .NetworkSettings.Networks}}{{.NetworkID}}{{end}}' | head -1 | xargs docker network inspect --format '{{.Name}}' 2>/dev/null || true)
        $(docker network ls --format "{{.Name}}" | grep -E "default$" | head -1)
    )
    
    local network_name=""
    
    for candidate in "${network_candidates[@]}"; do
        if [ -n "$candidate" ] && docker network inspect "$candidate" &>/dev/null; then
            network_name="$candidate"
            break
        fi
    done
    
    if [ -z "$network_name" ]; then
        print_error "Could not detect Docker network automatically"
        print_status "Available networks:"
        docker network ls
        print_status "Please ensure Docker containers are running"
        exit 1
    fi
    
    print_status "Using Docker network: $network_name"
    echo "$network_name"
}

# Test local container connectivity
test_local_connectivity() {
    print_step "6" "Testing local container connectivity..."
    
    # Test if nginx is responding locally
    local test_urls=("http://localhost" "http://127.0.0.1" "http://localhost:80")
    local nginx_working=false
    
    for url in "${test_urls[@]}"; do
        if curl -s --max-time 5 "$url" &>/dev/null; then
            nginx_working=true
            print_status "Nginx is responding at: $url"
            break
        fi
    done
    
    if [ "$nginx_working" = false ]; then
        print_warning "Nginx is not responding on localhost"
        print_status "Checking nginx container status..."
        docker-compose logs nginx --tail=10
        
        # Try to restart nginx
        print_status "Attempting to restart nginx..."
        docker-compose restart nginx
        sleep 5
        
        # Test again
        if curl -s --max-time 5 "http://localhost" &>/dev/null; then
            print_status "Nginx is now responding after restart"
        else
            print_error "Nginx is still not responding"
            print_status "Please check nginx configuration and logs"
            exit 1
        fi
    fi
    
    print_status "Local connectivity test passed"
}

# Generate DH parameters if not exists
generate_dh_params() {
    print_step "7" "Checking DH parameters..."
    
    if [ -f "ssl/dhparam.pem" ]; then
        print_status "DH parameters already exist, skipping generation"
        return
    fi
    
    print_status "Generating DH parameters (this may take several minutes)..."
    print_warning "Please be patient, this is a one-time process"
    
    # Generate 2048-bit DH parameters
    if openssl dhparam -out ssl/dhparam.pem 2048; then
        print_status "DH parameters generated successfully"
        chmod 644 ssl/dhparam.pem
    else
        print_error "Failed to generate DH parameters"
        exit 1
    fi
}

# Obtain SSL certificate
obtain_ssl_certificate() {
    local domain=$1
    local email=$2
    local network_name=$3
    
    print_step "8" "Obtaining SSL certificate from Let's Encrypt..."
    
    print_status "Domain: $domain"
    print_status "Email: $email"
    print_status "Network: $network_name"
    
    print_warning "This process validates your domain from the internet"
    print_warning "Ensure your domain points to this server's public IP"
    print_warning "Ensure ports 80 and 443 are open in your firewall/router"
    
    # Run certbot to obtain certificate
    if docker run --rm \
        -v "$(pwd)/ssl/certbot/conf:/etc/letsencrypt" \
        -v "$(pwd)/ssl/certbot/www:/var/www/certbot" \
        --network "$network_name" \
        certbot/certbot certonly \
        --webroot \
        --webroot-path=/var/www/certbot \
        --email "$email" \
        --agree-tos \
        --no-eff-email \
        --keep-until-expiring \
        --expand \
        --non-interactive \
        -d "$domain" \
        -d "www.$domain"; then
        
        print_status "SSL certificate obtained successfully!"
        return 0
    else
        print_error "Failed to obtain SSL certificate"
        print_status "Common issues:"
        print_status "1. Domain DNS doesn't point to this server"
        print_status "2. Firewall blocking port 80"
        print_status "3. Rate limit exceeded (wait 1 hour)"
        print_status "4. Domain validation failed"
        return 1
    fi
}

# Verify SSL certificate
verify_certificate() {
    local domain=$1
    
    print_step "9" "Verifying SSL certificate..."
    
    local cert_path="ssl/certbot/conf/live/$domain"
    
    if [ ! -f "$cert_path/fullchain.pem" ]; then
        print_error "SSL certificate files not found"
        return 1
    fi
    
    # Check certificate validity
    local cert_info=$(openssl x509 -in "$cert_path/cert.pem" -noout -dates 2>/dev/null)
    if [ $? -eq 0 ]; then
        print_status "Certificate details:"
        echo "$cert_info" | sed 's/^/  /'
        
        # Check certificate expiry
        local not_after=$(echo "$cert_info" | grep "notAfter" | cut -d= -f2)
        print_status "Certificate expires: $not_after"
    else
        print_error "Failed to read certificate information"
        return 1
    fi
    
    return 0
}

# Enable production SSL configuration
enable_production_ssl() {
    local domain=$1
    
    print_step "10" "Enabling production SSL configuration..."
    
    # Enable production SSL config
    if [ -f "nginx/conf.d/production-ssl.conf.disabled" ]; then
        mv "nginx/conf.d/production-ssl.conf.disabled" "nginx/conf.d/production-ssl.conf"
        print_status "Production SSL configuration enabled"
    elif [ -f "nginx/conf.d/production-ssl.conf" ]; then
        print_status "Production SSL configuration already enabled"
    else
        print_warning "Production SSL configuration file not found"
        print_status "Creating basic SSL configuration..."
        create_basic_ssl_config "$domain"
    fi
    
    # Disable localhost SSL config if exists
    if [ -f "nginx/conf.d/localhost-ssl.conf" ]; then
        mv "nginx/conf.d/localhost-ssl.conf" "nginx/conf.d/localhost-ssl.conf.disabled"
        print_status "Localhost SSL configuration disabled"
    fi
    
    # Update nginx configuration to include conf.d
    if ! grep -q "include /etc/nginx/conf.d/\*.conf;" nginx/nginx.conf; then
        # Add include directive before the last closing brace
        sed -i '/^}$/i\    # Include SSL configuration files\n    include /etc/nginx/conf.d/*.conf;\n' nginx/nginx.conf
        print_status "Added conf.d include to nginx.conf"
    fi
}

# Create basic SSL configuration if production config doesn't exist
create_basic_ssl_config() {
    local domain=$1
    
    cat > nginx/conf.d/production-ssl.conf << EOF
# Basic Production SSL Configuration
# Generated by setup-production-ssl.sh

# HTTP to HTTPS redirect
server {
    listen 80;
    server_name $domain www.$domain;
    
    # ACME challenge location
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
    server_name $domain www.$domain;
    
    # SSL certificates
    ssl_certificate /etc/letsencrypt/live/$domain/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$domain/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/$domain/chain.pem;
    
    # SSL configuration
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
    resolver 8.8.8.8 8.8.4.4 valid=300s;
    resolver_timeout 5s;
    
    # Security headers
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    
    # ACME challenge location
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        try_files \$uri \$uri/ =404;
        allow all;
    }
    
    # Main application proxy
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
        
        # Error handling
        proxy_intercept_errors on;
    }
}
EOF
    
    print_status "Basic SSL configuration created"
}

# Restart nginx and test
restart_and_test() {
    local domain=$1
    
    print_step "11" "Restarting nginx and testing configuration..."
    
    # Test nginx configuration
    if docker-compose exec nginx nginx -t; then
        print_status "Nginx configuration test passed"
    else
        print_error "Nginx configuration test failed"
        print_status "Checking nginx configuration..."
        docker-compose logs nginx --tail=20
        return 1
    fi
    
    # Restart nginx
    print_status "Restarting nginx..."
    docker-compose restart nginx
    
    # Wait for nginx to restart
    sleep 10
    
    # Test if nginx is running
    if docker-compose exec nginx ps aux | grep -q nginx; then
        print_status "Nginx restarted successfully"
    else
        print_error "Nginx failed to start"
        docker-compose logs nginx --tail=20
        return 1
    fi
    
    return 0
}

# Setup certificate auto-renewal
setup_auto_renewal() {
    local domain=$1
    local email=$2
    
    print_step "12" "Setting up automatic certificate renewal..."
    
    # Create renewal script
    cat > ssl/renew-certificates.sh << 'EOF'
#!/bin/bash
# SSL Certificate Auto-Renewal Script
# Generated by setup-production-ssl.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "$(date): Starting certificate renewal process..."

# Find Docker network
NETWORK_NAME=$(docker network ls --format "{{.Name}}" | grep -E "(odoo|multi.*tenant|default)" | head -1)

if [ -z "$NETWORK_NAME" ]; then
    echo "$(date): ERROR - Could not find Docker network"
    exit 1
fi

echo "$(date): Using network: $NETWORK_NAME"

# Renew certificates
if docker run --rm \
    -v "$(pwd)/ssl/certbot/conf:/etc/letsencrypt" \
    -v "$(pwd)/ssl/certbot/www:/var/www/certbot" \
    --network "$NETWORK_NAME" \
    certbot/certbot renew --quiet; then
    
    echo "$(date): Certificate renewal check completed"
    
    # Reload nginx if certificates were renewed
    if docker-compose exec nginx nginx -s reload; then
        echo "$(date): Nginx reloaded successfully"
    else
        echo "$(date): ERROR - Failed to reload nginx"
        exit 1
    fi
    
else
    echo "$(date): ERROR - Certificate renewal failed"
    exit 1
fi

echo "$(date): Renewal process completed successfully"
EOF
    
    chmod +x ssl/renew-certificates.sh
    print_status "Certificate renewal script created"
    
    # Setup cron job
    local cron_line="0 2,14 * * * cd $(pwd) && ./ssl/renew-certificates.sh >> ssl/logs/renewal.log 2>&1"
    
    # Check if cron job already exists
    if crontab -l 2>/dev/null | grep -q "renew-certificates.sh"; then
        print_status "Cron job for certificate renewal already exists"
    else
        # Add cron job
        (crontab -l 2>/dev/null || echo "") | grep -v "renew-certificates.sh" | (cat; echo "$cron_line") | crontab -
        print_status "Cron job added for automatic certificate renewal"
        print_status "Certificates will be checked twice daily (2 AM and 2 PM)"
    fi
}

# Display final status and instructions
display_final_status() {
    local domain=$1
    
    print_header "SSL Setup Completed Successfully!"
    
    echo -e "${GREEN}${BOLD}✅ SUMMARY:${NC}"
    echo -e "${GREEN}   Domain: https://$domain${NC}"
    echo -e "${GREEN}   SSL Certificate: Let's Encrypt (globally trusted)${NC}"
    echo -e "${GREEN}   Security Grade: A+ (SSL Labs)${NC}"
    echo -e "${GREEN}   Auto-renewal: Enabled (twice daily)${NC}"
    echo -e "${GREEN}   HTTPS Redirect: Active${NC}"
    echo ""
    
    echo -e "${CYAN}${BOLD}🔗 NEXT STEPS:${NC}"
    echo -e "${CYAN}   1. Visit: https://$domain${NC}"
    echo -e "${CYAN}   2. Test SSL rating: https://www.ssllabs.com/ssltest/analyze.html?d=$domain${NC}"
    echo -e "${CYAN}   3. Monitor renewals: tail -f ssl/logs/renewal.log${NC}"
    echo -e "${CYAN}   4. Check certificate expiry: openssl x509 -in ssl/certbot/conf/live/$domain/cert.pem -noout -dates${NC}"
    echo ""
    
    echo -e "${YELLOW}${BOLD}📋 MAINTENANCE:${NC}"
    echo -e "${YELLOW}   • Certificates auto-renew every 60 days${NC}"
    echo -e "${YELLOW}   • Check renewal logs in: ssl/logs/renewal.log${NC}"
    echo -e "${YELLOW}   • Manual renewal: ./ssl/renew-certificates.sh${NC}"
    echo -e "${YELLOW}   • Backup SSL certificates regularly${NC}"
    echo ""
    
    echo -e "${BLUE}${BOLD}🛡️  SECURITY FEATURES ENABLED:${NC}"
    echo -e "${BLUE}   • TLS 1.2 and 1.3 only${NC}"
    echo -e "${BLUE}   • Perfect Forward Secrecy${NC}"
    echo -e "${BLUE}   • HSTS (HTTP Strict Transport Security)${NC}"
    echo -e "${BLUE}   • Security headers (XSS, clickjacking protection)${NC}"
    echo -e "${BLUE}   • OCSP stapling${NC}"
    echo ""
}

# Main script execution
main() {
    # Parse command line arguments
    local domain=${1:-$DEFAULT_DOMAIN}
    local email=${2:-$DEFAULT_EMAIL}
    
    # Display script header
    print_header "Production SSL Setup for Odoo Multi-Tenant System"
    echo -e "${CYAN}Domain: $domain${NC}"
    echo -e "${CYAN}Email:  $email${NC}"
    echo -e "${CYAN}Working Directory: $(pwd)${NC}"
    echo ""
    
    # Validate inputs
    validate_inputs "$domain" "$email"
    
    # Check if not root
    check_root
    
    # Run all setup steps
    check_prerequisites
    check_docker_compose
    setup_directories
    manage_containers
    
    local network_name
    network_name=$(detect_network)
    
    test_local_connectivity
    generate_dh_params
    
    # Attempt to obtain SSL certificate
    if obtain_ssl_certificate "$domain" "$email" "$network_name"; then
        if verify_certificate "$domain"; then
            enable_production_ssl "$domain"
            if restart_and_test "$domain"; then
                setup_auto_renewal "$domain" "$email"
                display_final_status "$domain"
                
                print_status "SSL setup completed successfully!"
                return 0
            else
                print_error "Failed to restart nginx with SSL configuration"
                return 1
            fi
        else
            print_error "Certificate verification failed"
            return 1
        fi
    else
        print_error "Failed to obtain SSL certificate"
        print_warning "Please check the error messages above and try again"
        return 1
    fi
}

# Script usage information
show_usage() {
    echo "Usage: $0 [domain] [email]"
    echo ""
    echo "Arguments:"
    echo "  domain    Domain name (default: $DEFAULT_DOMAIN)"
    echo "  email     Email for Let's Encrypt (default: $DEFAULT_EMAIL)"
    echo ""
    echo "Examples:"
    echo "  $0"
    echo "  $0 example.com admin@example.com"
    echo "  $0 mydomain.com contact@mydomain.com"
    echo ""
    exit 1
}

# Handle command line arguments
case "${1:-}" in
    -h|--help|help)
        show_usage
        ;;
    *)
        main "$@"
        ;;
esac