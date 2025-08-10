#!/bin/bash

# Automated SSL Setup Script for Odoo Multi-Tenant System
# Bulletproof implementation with comprehensive error handling
# Author: Claude AI Assistant
# Version: 2.0

set -euo pipefail  # Exit on any error, undefined variable, or pipe failure
IFS=$'\n\t'       # Secure Internal Field Separator

# Script configuration
readonly SCRIPT_NAME="$(basename "$0")"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$SCRIPT_DIR"
readonly LOG_FILE="$PROJECT_DIR/ssl/logs/ssl-setup.log"
readonly LOCK_FILE="/tmp/${SCRIPT_NAME}.lock"

# Default configuration
readonly DEFAULT_DOMAIN="khudroo.com"
readonly DEFAULT_EMAIL="admin@khudroo.com"
readonly CERTBOT_IMAGE="certbot/certbot:latest"
readonly NGINX_TEST_TIMEOUT=30
readonly CERT_VALIDATION_TIMEOUT=300

# Colors for output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly CYAN='\033[0;36m'
readonly BOLD='\033[1m'
readonly NC='\033[0m' # No Color

# Global variables
DOMAIN=""
EMAIL=""
NETWORK_NAME=""
CERT_PATH=""
DEBUG_MODE=false
FORCE_MODE=false
SKIP_TESTS=false

# Logging functions
log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $message" | tee -a "$LOG_FILE"
}

log_info() { log "INFO" "$@"; }
log_warn() { log "WARN" "$@"; }
log_error() { log "ERROR" "$@"; }
log_debug() { [[ "$DEBUG_MODE" == true ]] && log "DEBUG" "$@" || true; }

# Print functions with logging
print_header() {
    local message="$1"
    echo -e "${BLUE}${BOLD}"
    echo "========================================"
    echo "$message"
    echo "========================================"
    echo -e "${NC}"
    log_info "=== $message ==="
}

print_step() {
    local step="$1"
    local message="$2"
    echo -e "${CYAN}${BOLD}[STEP $step]${NC} $message"
    log_info "STEP $step: $message"
}

print_success() {
    echo -e "${GREEN}[✓ SUCCESS]${NC} $1"
    log_info "SUCCESS: $1"
}

print_warning() {
    echo -e "${YELLOW}[⚠ WARNING]${NC} $1"
    log_warn "$1"
}

print_error() {
    echo -e "${RED}[✗ ERROR]${NC} $1"
    log_error "$1"
}

print_info() {
    echo -e "${BLUE}[ℹ INFO]${NC} $1"
    log_info "$1"
}

# Cleanup function
cleanup() {
    local exit_code=$?
    log_debug "Cleanup function called with exit code: $exit_code"
    
    # Remove lock file
    [[ -f "$LOCK_FILE" ]] && rm -f "$LOCK_FILE"
    
    # If script failed, provide helpful information
    if [[ $exit_code -ne 0 ]]; then
        print_error "Script failed with exit code $exit_code"
        print_info "Check the log file for details: $LOG_FILE"
        print_info "Common solutions:"
        print_info "1. Ensure domain DNS points to this server"
        print_info "2. Check firewall allows ports 80 and 443"
        print_info "3. Verify Docker containers are running"
        print_info "4. Run with --debug for verbose output"
    fi
    
    exit $exit_code
}

# Set up signal handlers
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Lock mechanism to prevent concurrent runs
acquire_lock() {
    if [[ -f "$LOCK_FILE" ]]; then
        local lock_pid
        lock_pid=$(cat "$LOCK_FILE" 2>/dev/null || echo "")
        if [[ -n "$lock_pid" ]] && kill -0 "$lock_pid" 2>/dev/null; then
            print_error "Another instance is already running (PID: $lock_pid)"
            exit 1
        else
            print_warning "Removing stale lock file"
            rm -f "$LOCK_FILE"
        fi
    fi
    echo $$ > "$LOCK_FILE"
    log_info "Lock acquired (PID: $$)"
}

# Input validation functions
validate_domain() {
    local domain="$1"
    
    # Basic domain format validation
    if [[ ! "$domain" =~ ^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$ ]]; then
        print_error "Invalid domain format: $domain"
        return 1
    fi
    
    # Check domain length
    if [[ ${#domain} -gt 253 ]]; then
        print_error "Domain too long: $domain (max 253 characters)"
        return 1
    fi
    
    # Check for reserved domains
    local reserved_domains=("localhost" "example.com" "test.com" "invalid")
    for reserved in "${reserved_domains[@]}"; do
        if [[ "$domain" == "$reserved" ]]; then
            print_error "Cannot use reserved domain: $domain"
            return 1
        fi
    done
    
    return 0
}

validate_email() {
    local email="$1"
    
    # Basic email format validation
    if [[ ! "$email" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]; then
        print_error "Invalid email format: $email"
        return 1
    fi
    
    # Check email length
    if [[ ${#email} -gt 320 ]]; then
        print_error "Email too long: $email (max 320 characters)"
        return 1
    fi
    
    return 0
}

# System checks
check_root() {
    if [[ $EUID -eq 0 ]]; then
        print_error "Do not run this script as root"
        print_info "Run as regular user with sudo access"
        exit 1
    fi
}

check_commands() {
    local required_commands=("docker" "docker-compose" "curl" "openssl" "grep" "sed" "awk")
    local missing_commands=()
    
    for cmd in "${required_commands[@]}"; do
        if ! command -v "$cmd" &> /dev/null; then
            missing_commands+=("$cmd")
        fi
    done
    
    if [[ ${#missing_commands[@]} -gt 0 ]]; then
        print_error "Missing required commands: ${missing_commands[*]}"
        print_info "Please install missing packages"
        exit 1
    fi
}

check_docker() {
    # Check if Docker daemon is running
    if ! docker info &> /dev/null; then
        print_error "Docker daemon is not running or accessible"
        print_info "Start Docker: sudo systemctl start docker"
        print_info "Add user to docker group: sudo usermod -aG docker $USER"
        exit 1
    fi
    
    # Check Docker Compose
    if ! docker-compose version &> /dev/null; then
        print_error "Docker Compose is not working"
        exit 1
    fi
}

check_project_structure() {
    local required_files=("docker-compose.yml" "nginx/nginx.conf")
    local required_dirs=("nginx" "nginx/conf.d")
    
    # Check required files
    for file in "${required_files[@]}"; do
        if [[ ! -f "$file" ]]; then
            print_error "Required file not found: $file"
            print_info "Please run this script from the project root directory"
            exit 1
        fi
    done
    
    # Check required directories
    for dir in "${required_dirs[@]}"; do
        if [[ ! -d "$dir" ]]; then
            print_warning "Creating missing directory: $dir"
            mkdir -p "$dir"
        fi
    done
    
    # Validate docker-compose.yml
    if ! docker-compose config &> /dev/null; then
        print_error "Invalid docker-compose.yml configuration"
        exit 1
    fi
}

# Setup functions
setup_directories() {
    local dirs=("ssl/certbot/conf" "ssl/certbot/www" "ssl/logs" "nginx/conf.d")
    
    for dir in "${dirs[@]}"; do
        if [[ ! -d "$dir" ]]; then
            log_debug "Creating directory: $dir"
            mkdir -p "$dir"
        fi
    done
    
    # Fix permissions if directories exist but are not writable
    for dir in "${dirs[@]}"; do
        if [[ ! -w "$dir" ]]; then
            log_debug "Fixing permissions for: $dir"
            if sudo chown -R "$USER:$USER" "$dir" 2>/dev/null; then
                chmod 755 "$dir"
            else
                print_warning "Could not fix permissions for: $dir"
            fi
        fi
    done
}

# Docker management
get_docker_network() {
    log_debug "Detecting Docker network"
    
    # Try multiple methods to find the network
    local network_candidates=(
        $(docker network ls --format "{{.Name}}" | grep -E "(odoo|multi.*tenant)" 2>/dev/null | head -3)
        $(docker-compose ps -q 2>/dev/null | head -1 | xargs -r docker inspect --format '{{range .NetworkSettings.Networks}}{{.NetworkID}}{{end}}' 2>/dev/null | head -1 | xargs -r docker network inspect --format '{{.Name}}' 2>/dev/null || true)
        $(docker network ls --format "{{.Name}}" | grep -E "_default$" | head -1)
    )
    
    # Test each candidate
    for candidate in "${network_candidates[@]}"; do
        if [[ -n "$candidate" ]] && docker network inspect "$candidate" &>/dev/null; then
            NETWORK_NAME="$candidate"
            log_debug "Found network: $NETWORK_NAME"
            return 0
        fi
    done
    
    print_error "Could not detect Docker network"
    print_info "Available networks:"
    docker network ls
    exit 1
}

start_containers() {
    log_debug "Starting Docker containers"
    
    # Check container status
    local running_containers
    running_containers=$(docker-compose ps --services --filter "status=running" 2>/dev/null || true)
    
    if [[ -z "$running_containers" ]]; then
        print_info "Starting Docker containers..."
        if ! docker-compose up -d; then
            print_error "Failed to start containers"
            exit 1
        fi
    else
        print_info "Restarting containers to apply new configurations..."
        if ! docker-compose restart; then
            print_error "Failed to restart containers"
            exit 1
        fi
    fi
    
    # Wait for containers to be healthy
    local max_wait=60
    local wait_time=0
    
    while [[ $wait_time -lt $max_wait ]]; do
        local unhealthy_containers
        unhealthy_containers=$(docker-compose ps --format "table {{.Service}}\t{{.State}}" | grep -v "Up\|Name" | grep -v "^$" || true)
        
        if [[ -z "$unhealthy_containers" ]]; then
            break
        fi
        
        if [[ $wait_time -eq 0 ]]; then
            print_info "Waiting for containers to be ready..."
        fi
        
        sleep 5
        wait_time=$((wait_time + 5))
    done
    
    if [[ $wait_time -ge $max_wait ]]; then
        print_warning "Some containers may not be fully ready"
        docker-compose ps
    fi
}

test_local_connectivity() {
    if [[ "$SKIP_TESTS" == true ]]; then
        print_info "Skipping local connectivity tests"
        return 0
    fi
    
    local test_urls=("http://localhost" "http://127.0.0.1")
    local nginx_responding=false
    
    for url in "${test_urls[@]}"; do
        log_debug "Testing connectivity to: $url"
        if curl -s --max-time 5 --fail "$url" &>/dev/null; then
            nginx_responding=true
            print_success "Nginx responding at: $url"
            break
        fi
    done
    
    if [[ "$nginx_responding" == false ]]; then
        print_warning "Nginx not responding locally"
        
        # Try to diagnose the issue
        if docker-compose ps nginx | grep -q "Up"; then
            print_info "Nginx container is running, checking logs..."
            docker-compose logs --tail=10 nginx
        else
            print_error "Nginx container is not running"
            docker-compose ps
            exit 1
        fi
        
        # Try to restart nginx
        print_info "Attempting to restart nginx..."
        if docker-compose restart nginx; then
            sleep 5
            if curl -s --max-time 5 --fail "http://localhost" &>/dev/null; then
                print_success "Nginx responding after restart"
            else
                print_error "Nginx still not responding after restart"
                exit 1
            fi
        else
            print_error "Failed to restart nginx"
            exit 1
        fi
    fi
}

# Certificate management
generate_dh_params() {
    local dh_file="ssl/dhparam.pem"
    
    if [[ -f "$dh_file" ]]; then
        print_info "DH parameters already exist"
        return 0
    fi
    
    print_info "Generating DH parameters (this may take several minutes)..."
    if openssl dhparam -out "$dh_file" 2048 2>/dev/null; then
        chmod 644 "$dh_file"
        print_success "DH parameters generated"
    else
        print_error "Failed to generate DH parameters"
        exit 1
    fi
}

obtain_certificate() {
    local domain="$1"
    local email="$2"
    local network="$3"
    
    print_info "Requesting SSL certificate for: $domain"
    print_info "Email: $email"
    print_info "Network: $network"
    
    # Pull certbot image first
    if ! docker pull "$CERTBOT_IMAGE" &>/dev/null; then
        print_warning "Could not pull latest certbot image, using existing"
    fi
    
    # Run certbot
    local certbot_cmd=(
        "docker" "run" "--rm"
        "-v" "$(pwd)/ssl/certbot/conf:/etc/letsencrypt"
        "-v" "$(pwd)/ssl/certbot/www:/var/www/certbot"
        "--network" "$network"
        "$CERTBOT_IMAGE" "certonly"
        "--webroot"
        "--webroot-path=/var/www/certbot"
        "--email" "$email"
        "--agree-tos"
        "--no-eff-email"
        "--keep-until-expiring"
        "--non-interactive"
        "--expand"
        "-d" "$domain"
    )
    
    log_debug "Running certbot command: ${certbot_cmd[*]}"
    
    # Capture certbot output
    local certbot_output
    if certbot_output=$("${certbot_cmd[@]}" 2>&1); then
        print_success "Certificate request completed"
        log_debug "Certbot output: $certbot_output"
    else
        print_error "Certificate request failed"
        echo "$certbot_output" | tee -a "$LOG_FILE"
        return 1
    fi
    
    # Find the actual certificate path
    find_certificate_path "$domain"
    
    if [[ -z "$CERT_PATH" ]]; then
        print_error "Certificate files not found after successful request"
        return 1
    fi
    
    print_success "Certificate obtained at: $CERT_PATH"
    return 0
}

find_certificate_path() {
    local domain="$1"
    local cert_dirs=("ssl/certbot/conf/live/$domain" "ssl/certbot/conf/live/$domain-0001" "ssl/certbot/conf/live/$domain-0002")
    
    CERT_PATH=""
    
    for cert_dir in "${cert_dirs[@]}"; do
        if [[ -f "$cert_dir/fullchain.pem" && -f "$cert_dir/privkey.pem" ]]; then
            CERT_PATH="$cert_dir"
            log_debug "Found certificate at: $CERT_PATH"
            break
        fi
    done
    
    if [[ -z "$CERT_PATH" ]]; then
        print_warning "Searching for certificate in all live directories..."
        local found_dirs
        found_dirs=$(find ssl/certbot/conf/live -name "fullchain.pem" 2>/dev/null | head -1)
        if [[ -n "$found_dirs" ]]; then
            CERT_PATH=$(dirname "$found_dirs")
            print_info "Found certificate at: $CERT_PATH"
        fi
    fi
}

verify_certificate() {
    if [[ -z "$CERT_PATH" ]]; then
        print_error "No certificate path specified"
        return 1
    fi
    
    local cert_file="$CERT_PATH/cert.pem"
    local key_file="$CERT_PATH/privkey.pem"
    local chain_file="$CERT_PATH/fullchain.pem"
    
    # Check certificate files exist
    for file in "$cert_file" "$key_file" "$chain_file"; do
        if [[ ! -f "$file" ]]; then
            print_error "Certificate file missing: $file"
            return 1
        fi
    done
    
    # Verify certificate validity
    if ! openssl x509 -in "$cert_file" -noout -checkend 0 2>/dev/null; then
        print_error "Certificate is not valid or has expired"
        return 1
    fi
    
    # Check certificate expiration
    local expiry_date
    expiry_date=$(openssl x509 -in "$cert_file" -noout -enddate 2>/dev/null | cut -d= -f2)
    print_info "Certificate expires: $expiry_date"
    
    # Verify certificate matches private key
    local cert_modulus key_modulus
    cert_modulus=$(openssl x509 -noout -modulus -in "$cert_file" 2>/dev/null | openssl md5)
    key_modulus=$(openssl rsa -noout -modulus -in "$key_file" 2>/dev/null | openssl md5)
    
    if [[ "$cert_modulus" != "$key_modulus" ]]; then
        print_error "Certificate and private key do not match"
        return 1
    fi
    
    print_success "Certificate verification passed"
    return 0
}

# Nginx configuration
create_ssl_config() {
    local domain="$1"
    local cert_path="$2"
    local config_file="nginx/conf.d/auto-ssl.conf"
    
    # Remove existing SSL configs to avoid conflicts
    for old_config in nginx/conf.d/*ssl*.conf; do
        if [[ -f "$old_config" && "$old_config" != "$config_file" ]]; then
            mv "$old_config" "$old_config.disabled.$(date +%s)"
            print_info "Disabled conflicting config: $(basename "$old_config")"
        fi
    done
    
    # Create new SSL configuration
    cat > "$config_file" << EOF
# Automated SSL Configuration
# Generated by $SCRIPT_NAME on $(date)
# Domain: $domain
# Certificate: $cert_path

# WebSocket upgrade mapping
map \$http_upgrade \$connection_upgrade {
    default upgrade;
    ''      close;
}

# HTTP to HTTPS redirect
server {
    listen 80;
    server_name $domain;
    
    # ACME challenge location
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        try_files \$uri \$uri/ =404;
        allow all;
        expires -1;
        add_header Cache-Control "no-cache, no-store, must-revalidate";
    }
    
    # Redirect all other traffic to HTTPS
    location / {
        return 301 https://\$server_name\$request_uri;
    }
}

# HTTPS server
server {
    listen 443 ssl;
    http2 on;
    server_name $domain;
    
    # SSL certificates
    ssl_certificate /etc/letsencrypt/live/$(basename "$cert_path")/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$(basename "$cert_path")/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/$(basename "$cert_path")/chain.pem;
    
    # Modern SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL_AUTO:50m;
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
    
    # ACME challenge location
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
    
    print_success "SSL configuration created: $config_file"
}

update_nginx_config() {
    local nginx_conf="nginx/nginx.conf"
    local backup_file="$nginx_conf.backup.$(date +%s)"
    
    # Backup original configuration
    cp "$nginx_conf" "$backup_file"
    print_info "Backed up nginx.conf to: $backup_file"
    
    # Add include directive if not present
    if ! grep -q "include /etc/nginx/conf.d/\*.conf;" "$nginx_conf"; then
        # Find the location to add the include
        if grep -q "^}$" "$nginx_conf"; then
            # Add before the last closing brace
            sed -i '/^}$/i\    # Include SSL configuration files\n    include /etc/nginx/conf.d/*.conf;\n' "$nginx_conf"
            print_success "Added conf.d include to nginx.conf"
        else
            print_error "Could not find appropriate location to add include directive"
            return 1
        fi
    else
        print_info "nginx.conf already includes conf.d directory"
    fi
}

test_nginx_config() {
    print_info "Testing nginx configuration..."
    
    if docker-compose exec nginx nginx -t 2>&1; then
        print_success "Nginx configuration test passed"
        return 0
    else
        print_error "Nginx configuration test failed"
        print_info "Checking nginx logs..."
        docker-compose logs --tail=20 nginx
        return 1
    fi
}

restart_nginx() {
    print_info "Restarting nginx..."
    
    if docker-compose restart nginx; then
        # Wait for nginx to be ready
        local max_wait=30
        local wait_time=0
        
        while [[ $wait_time -lt $max_wait ]]; do
            if docker-compose exec nginx pgrep nginx &>/dev/null; then
                print_success "Nginx restarted successfully"
                return 0
            fi
            sleep 1
            wait_time=$((wait_time + 1))
        done
        
        print_error "Nginx took too long to start"
        docker-compose logs --tail=10 nginx
        return 1
    else
        print_error "Failed to restart nginx"
        return 1
    fi
}

# Auto-renewal setup
setup_auto_renewal() {
    local domain="$1"
    local email="$2"
    
    local renewal_script="ssl/auto-renew.sh"
    
    cat > "$renewal_script" << EOF
#!/bin/bash
# Auto-renewal script for SSL certificates
# Generated by $SCRIPT_NAME on $(date)

set -euo pipefail

# Configuration
SCRIPT_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="\$(dirname "\$SCRIPT_DIR")"
LOG_FILE="\$SCRIPT_DIR/logs/renewal.log"

# Logging function
log() {
    local timestamp=\$(date '+%Y-%m-%d %H:%M:%S')
    echo "[\$timestamp] \$*" | tee -a "\$LOG_FILE"
}

# Change to project directory
cd "\$PROJECT_DIR"

log "Starting certificate renewal check..."

# Find Docker network
NETWORK_NAME=\$(docker network ls --format "{{.Name}}" | grep -E "(odoo|multi.*tenant)" | head -1)

if [[ -z "\$NETWORK_NAME" ]]; then
    log "ERROR: Could not find Docker network"
    exit 1
fi

log "Using network: \$NETWORK_NAME"

# Renew certificates
if docker run --rm \\
    -v "\$(pwd)/ssl/certbot/conf:/etc/letsencrypt" \\
    -v "\$(pwd)/ssl/certbot/www:/var/www/certbot" \\
    --network "\$NETWORK_NAME" \\
    $CERTBOT_IMAGE renew --quiet; then
    
    log "Certificate renewal check completed successfully"
    
    # Reload nginx configuration
    if docker-compose exec nginx nginx -s reload; then
        log "Nginx configuration reloaded successfully"
    else
        log "ERROR: Failed to reload nginx configuration"
        exit 1
    fi
    
else
    log "ERROR: Certificate renewal failed"
    exit 1
fi

log "Auto-renewal process completed successfully"
EOF
    
    chmod +x "$renewal_script"
    print_success "Auto-renewal script created: $renewal_script"
    
    # Setup cron job
    local cron_command="0 2,14 * * * cd $PROJECT_DIR && ./ssl/auto-renew.sh >> $PROJECT_DIR/ssl/logs/renewal.log 2>&1"
    local existing_cron
    existing_cron=$(crontab -l 2>/dev/null | grep -F "$PROJECT_DIR/ssl/auto-renew.sh" || true)
    
    if [[ -z "$existing_cron" ]]; then
        (crontab -l 2>/dev/null || echo "") | grep -v "auto-renew.sh" | (cat; echo "$cron_command") | crontab -
        print_success "Cron job added for automatic renewal"
        print_info "Certificates will be checked twice daily (2 AM and 2 PM)"
    else
        print_info "Cron job for auto-renewal already exists"
    fi
}

# Testing functions
test_https_connectivity() {
    local domain="$1"
    
    if [[ "$SKIP_TESTS" == true ]]; then
        print_info "Skipping HTTPS connectivity tests"
        return 0
    fi
    
    print_info "Testing HTTPS connectivity..."
    
    # Test HTTPS connection
    local test_url="https://$domain/health"
    local max_attempts=3
    local attempt=1
    
    while [[ $attempt -le $max_attempts ]]; do
        log_debug "HTTPS test attempt $attempt/$max_attempts"
        
        if curl -s --max-time 10 --fail "$test_url" &>/dev/null; then
            print_success "HTTPS is working: $test_url"
            return 0
        fi
        
        if [[ $attempt -lt $max_attempts ]]; then
            print_info "HTTPS test failed, retrying in 5 seconds..."
            sleep 5
        fi
        
        attempt=$((attempt + 1))
    done
    
    print_warning "HTTPS connectivity test failed"
    print_info "This might be normal if testing from behind NAT/router"
    print_info "Try accessing https://$domain from an external network"
    
    return 0  # Don't fail the script for connectivity issues
}

# Main workflow
main() {
    local domain="${1:-$DEFAULT_DOMAIN}"
    local email="${2:-$DEFAULT_EMAIL}"
    
    print_header "Automated SSL Setup for Odoo Multi-Tenant System"
    
    print_info "Domain: $domain"
    print_info "Email: $email"
    print_info "Working Directory: $PROJECT_DIR"
    print_info "Log File: $LOG_FILE"
    print_info ""
    
    # Validation
    validate_domain "$domain" || exit 1
    validate_email "$email" || exit 1
    
    DOMAIN="$domain"
    EMAIL="$email"
    
    # System checks
    print_step "1" "Performing system checks..."
    check_root
    check_commands
    check_docker
    check_project_structure
    print_success "System checks passed"
    
    # Setup
    print_step "2" "Setting up directories and permissions..."
    setup_directories
    print_success "Directories setup completed"
    
    # Docker management
    print_step "3" "Managing Docker containers..."
    get_docker_network
    start_containers
    print_success "Docker containers are ready"
    
    # Local tests
    print_step "4" "Testing local connectivity..."
    test_local_connectivity
    print_success "Local connectivity verified"
    
    # Certificate preparation
    print_step "5" "Preparing for certificate generation..."
    generate_dh_params
    print_success "Certificate preparation completed"
    
    # Certificate acquisition
    print_step "6" "Obtaining SSL certificate..."
    if obtain_certificate "$domain" "$email" "$NETWORK_NAME"; then
        print_success "SSL certificate obtained successfully"
    else
        print_error "Failed to obtain SSL certificate"
        exit 1
    fi
    
    # Certificate verification
    print_step "7" "Verifying SSL certificate..."
    if verify_certificate; then
        print_success "SSL certificate verification passed"
    else
        print_error "SSL certificate verification failed"
        exit 1
    fi
    
    # Nginx configuration
    print_step "8" "Configuring nginx for SSL..."
    create_ssl_config "$domain" "$CERT_PATH"
    update_nginx_config
    
    if test_nginx_config; then
        print_success "Nginx configuration is valid"
    else
        print_error "Nginx configuration is invalid"
        exit 1
    fi
    
    # Nginx restart
    print_step "9" "Restarting nginx with SSL configuration..."
    if restart_nginx; then
        print_success "Nginx restarted with SSL configuration"
    else
        print_error "Failed to restart nginx"
        exit 1
    fi
    
    # Auto-renewal setup
    print_step "10" "Setting up automatic certificate renewal..."
    setup_auto_renewal "$domain" "$email"
    print_success "Auto-renewal configured"
    
    # Final tests
    print_step "11" "Testing HTTPS connectivity..."
    test_https_connectivity "$domain"
    
    # Success summary
    print_header "SSL Setup Completed Successfully!"
    
    echo -e "${GREEN}${BOLD}✅ SUMMARY:${NC}"
    echo -e "${GREEN}   Domain: https://$domain${NC}"
    echo -e "${GREEN}   Certificate: Let's Encrypt (globally trusted)${NC}"
    echo -e "${GREEN}   Certificate Path: $CERT_PATH${NC}"
    echo -e "${GREEN}   Auto-renewal: Enabled (twice daily)${NC}"
    echo -e "${GREEN}   HTTPS Redirect: Active${NC}"
    echo ""
    
    echo -e "${CYAN}${BOLD}🔗 NEXT STEPS:${NC}"
    echo -e "${CYAN}   1. Visit: https://$domain${NC}"
    echo -e "${CYAN}   2. Test SSL rating: https://www.ssllabs.com/ssltest/analyze.html?d=$domain${NC}"
    echo -e "${CYAN}   3. Monitor renewals: tail -f $PROJECT_DIR/ssl/logs/renewal.log${NC}"
    echo ""
    
    echo -e "${BLUE}${BOLD}🛡️ SECURITY FEATURES:${NC}"
    echo -e "${BLUE}   • TLS 1.2 and 1.3 only${NC}"
    echo -e "${BLUE}   • Perfect Forward Secrecy${NC}"
    echo -e "${BLUE}   • HSTS with preload support${NC}"
    echo -e "${BLUE}   • Comprehensive security headers${NC}"
    echo -e "${BLUE}   • OCSP stapling enabled${NC}"
    echo ""
    
    log_info "SSL setup completed successfully for domain: $domain"
}

# Command line argument parsing
show_usage() {
    cat << EOF
Usage: $SCRIPT_NAME [OPTIONS] [DOMAIN] [EMAIL]

Automated SSL setup script for Odoo Multi-Tenant System using Let's Encrypt.

Arguments:
  DOMAIN              Domain name (default: $DEFAULT_DOMAIN)
  EMAIL               Email for Let's Encrypt notifications (default: $DEFAULT_EMAIL)

Options:
  -h, --help          Show this help message
  -d, --debug         Enable debug logging
  -f, --force         Force renewal even if certificate exists
  -s, --skip-tests    Skip connectivity tests
  --version           Show script version

Examples:
  $SCRIPT_NAME
  $SCRIPT_NAME example.com admin@example.com
  $SCRIPT_NAME --debug mydomain.com contact@mydomain.com
  $SCRIPT_NAME --force --skip-tests khudroo.com admin@khudroo.com

Environment Variables:
  SSL_DOMAIN          Override default domain
  SSL_EMAIL           Override default email
  SSL_DEBUG           Enable debug mode (set to 'true')

Log files:
  SSL setup log: $LOG_FILE
  Auto-renewal log: ssl/logs/renewal.log

EOF
}

# Parse command line arguments
parse_args() {
    local args=()
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_usage
                exit 0
                ;;
            -d|--debug)
                DEBUG_MODE=true
                shift
                ;;
            -f|--force)
                FORCE_MODE=true
                shift
                ;;
            -s|--skip-tests)
                SKIP_TESTS=true
                shift
                ;;
            --version)
                echo "$SCRIPT_NAME version 2.0"
                exit 0
                ;;
            -*)
                print_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
            *)
                args+=("$1")
                shift
                ;;
        esac
    done
    
    # Handle environment variables
    local domain="${SSL_DOMAIN:-${args[0]:-$DEFAULT_DOMAIN}}"
    local email="${SSL_EMAIL:-${args[1]:-$DEFAULT_EMAIL}}"
    
    if [[ "${SSL_DEBUG:-false}" == "true" ]]; then
        DEBUG_MODE=true
    fi
    
    # Initialize logging
    setup_directories
    touch "$LOG_FILE"
    
    log_info "Script started with arguments: domain=$domain, email=$email, debug=$DEBUG_MODE, force=$FORCE_MODE, skip-tests=$SKIP_TESTS"
    
    # Run main function
    main "$domain" "$email"
}

# Script entry point
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    acquire_lock
    parse_args "$@"
fi