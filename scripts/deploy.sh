#!/bin/bash

# Odoo SaaS System Deployment Script
# This script automates the complete deployment of the Odoo SaaS system

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"
ENV_FILE="${PROJECT_ROOT}/.env"
COMPOSE_FILE="${PROJECT_ROOT}/docker-compose.yml"
BACKUP_DIR="/opt/backups"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Logging functions
log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')] INFO:${NC} $1"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" >&2
}

success() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] SUCCESS:${NC} $1"
}

warning() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
}

info() {
    echo -e "${PURPLE}[$(date '+%Y-%m-%d %H:%M:%S')] INFO:${NC} $1"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to generate random password
generate_password() {
    local length=${1:-32}
    openssl rand -base64 $length | tr -d "=+/" | cut -c1-$length
}

# Function to check system requirements
check_requirements() {
    log "Checking system requirements..."
    
    local missing_deps=()
    
    # Check for required commands
    local required_commands=("docker" "docker-compose" "openssl" "curl")
    
    for cmd in "${required_commands[@]}"; do
        if ! command_exists "$cmd"; then
            missing_deps+=("$cmd")
        fi
    done
    
    if [ ${#missing_deps[@]} -ne 0 ]; then
        error "Missing required dependencies: ${missing_deps[*]}"
        info "Please install the missing dependencies and run this script again."
        exit 1
    fi
    
    # Check Docker daemon
    if ! docker info >/dev/null 2>&1; then
        error "Docker daemon is not running. Please start Docker and try again."
        exit 1
    fi
    
    # Check available disk space (minimum 10GB)
    local available_space=$(df / | awk 'NR==2 {print $4}')
    local min_space=$((10 * 1024 * 1024)) # 10GB in KB
    
    if [ "$available_space" -lt "$min_space" ]; then
        warning "Available disk space is less than 10GB. You may encounter issues."
    fi
    
    success "System requirements check passed"
}

# Function to setup environment variables
setup_environment() {
    log "Setting up environment variables..."
    
    if [ -f "${ENV_FILE}" ]; then
        warning "Environment file already exists. Backing up existing file..."
        cp "${ENV_FILE}" "${ENV_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
    fi
    
    # Generate secure passwords and keys
    local postgres_password=$(generate_password 32)
    local secret_key=$(generate_password 64)
    local odoo_master_password=$(generate_password 16)
    
    # Create .env file
    cat > "${ENV_FILE}" << EOF
# Database Configuration
POSTGRES_PASSWORD=${postgres_password}
ODOO_MASTER_DB=odoo_master
ODOO_MASTER_USERNAME=admin
ODOO_MASTER_PASSWORD=${odoo_master_password}

# SaaS Manager Configuration
SECRET_KEY=${secret_key}

# Backup Configuration
BACKUP_RETENTION_DAYS=30

# SSL Configuration (set to true if using SSL)
USE_SSL=false
SSL_CERT_PATH=./ssl/cert.pem
SSL_KEY_PATH=./ssl/key.pem

# Domain Configuration
DOMAIN=localhost
EMAIL=admin@localhost

# Scaling Configuration
MIN_WORKERS=2
MAX_WORKERS=10
LOAD_THRESHOLD=80

# Logging
LOG_LEVEL=INFO

# Timezone
TZ=UTC
EOF
    
    success "Environment file created at ${ENV_FILE}"
    info "Important: Save these credentials securely!"
    info "Postgres Password: ${postgres_password}"
    info "Odoo Master Password: ${odoo_master_password}"
}

# Function to create directory structure
create_directories() {
    log "Creating directory structure..."
    
    local directories=(
        "${PROJECT_ROOT}/nginx/conf.d"
        "${PROJECT_ROOT}/ssl"
        "${PROJECT_ROOT}/init-scripts"
        "${PROJECT_ROOT}/saas_manager/logs"
        "${PROJECT_ROOT}/saas_manager/templates"
        "${PROJECT_ROOT}/saas_manager/static/css"
        "${PROJECT_ROOT}/saas_manager/static/js"
        "${PROJECT_ROOT}/odoo_master/addons"
        "${PROJECT_ROOT}/odoo_master/config"
        "${PROJECT_ROOT}/odoo_workers/addons"
        "${PROJECT_ROOT}/odoo_workers/config"
        "${BACKUP_DIR}/databases"
        "${BACKUP_DIR}/filestore"
        "${BACKUP_DIR}/logs"
    )
    
    for dir in "${directories[@]}"; do
        if [ ! -d "$dir" ]; then
            mkdir -p "$dir"
            log "Created directory: $dir"
        fi
    done
    
    success "Directory structure created"
}

# Function to setup SSL certificates
setup_ssl() {
    local use_ssl=${1:-false}
    
    if [ "$use_ssl" = "true" ]; then
        log "Setting up SSL certificates..."
        
        local ssl_dir="${PROJECT_ROOT}/ssl"
        local cert_file="${ssl_dir}/cert.pem"
        local key_file="${ssl_dir}/key.pem"
        
        if [ ! -f "$cert_file" ] || [ ! -f "$key_file" ]; then
            warning "SSL certificates not found. Generating self-signed certificates..."
            
            openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
                -keyout "$key_file" \
                -out "$cert_file" \
                -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"
            
            success "Self-signed SSL certificates generated"
            warning "For production, replace with proper SSL certificates"
        else
            success "SSL certificates found"
        fi
    else
        log "SSL disabled, skipping SSL setup"
    fi
}

# Function to build custom images
build_images() {
    log "Building custom Docker images..."
    
    cd "${PROJECT_ROOT}"
    
    # Build SaaS Manager image
    if [ -f "${PROJECT_ROOT}/saas_manager/Dockerfile" ]; then
        log "Building SaaS Manager image..."
        docker-compose build saas_manager
        success "SaaS Manager image built successfully"
    else
        warning "SaaS Manager Dockerfile not found, skipping build"
    fi
}

# Function to initialize databases
init_databases() {
    log "Initializing databases..."
    
    # Start PostgreSQL first
    docker-compose up -d postgres
    
    # Wait for PostgreSQL to be ready
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if docker-compose exec -T postgres pg_isready -h localhost -U odoo_master >/dev/null 2>&1; then
            break
        fi
        
        log "Waiting for PostgreSQL to be ready... (attempt $attempt/$max_attempts)"
        sleep 2
        ((attempt++))
    done
    
    if [ $attempt -gt $max_attempts ]; then
        error "PostgreSQL failed to start within expected time"
        exit 1
    fi
    
    success "PostgreSQL is ready"
    
    # Create additional databases if needed
    if [ -f "${PROJECT_ROOT}/init-scripts/init-db.sql" ]; then
        log "Running database initialization scripts..."
        docker-compose exec -T postgres psql -U odoo_master -d postgres -f /docker-entrypoint-initdb.d/init-db.sql
    fi
}

# Function to start services
start_services() {
    log "Starting all services..."
    
    cd "${PROJECT_ROOT}"
    
    # Start all services
    docker-compose up -d
    
    # Wait for services to be ready
    local services=("redis" "saas_manager" "odoo_master" "nginx")
    
    for service in "${services[@]}"; do
        log "Waiting for $service to be ready..."
        
        local max_attempts=60
        local attempt=1
        
        while [ $attempt -le $max_attempts ]; do
            if docker-compose ps | grep -q "$service.*Up"; then
                success "$service is ready"
                break
            fi
            
            sleep 2
            ((attempt++))
        done
        
        if [ $attempt -gt $max_attempts ]; then
            error "$service failed to start"
            exit 1
        fi
    done
    
    success "All services started successfully"
}

# Function to run health checks
health_check() {
    log "Running health checks..."
    
    local failed_checks=0
    
    # Check PostgreSQL
    if docker-compose exec -T postgres pg_isready -h localhost -U odoo_master >/dev/null 2>&1; then
        success "PostgreSQL health check passed"
    else
        error "PostgreSQL health check failed"
        ((failed_checks++))
    fi
    
    # Check Redis
    if docker-compose exec -T redis redis-cli ping | grep -q "PONG"; then
        success "Redis health check passed"
    else
        error "Redis health check failed"
        ((failed_checks++))
    fi
    
    # Check Nginx
    if docker-compose exec -T nginx curl -f http://localhost >/dev/null 2>&1; then
        success "Nginx health check passed"
    else
        warning "Nginx health check failed (this might be normal if upstream is not ready)"
    fi
    
    # Check Odoo Master
    sleep 5 # Give Odoo time to start
    if curl -f http://localhost:8069/web/database/selector >/dev/null 2>&1; then
        success "Odoo Master health check passed"
    else
        warning "Odoo Master health check failed (this might be normal during initial startup)"
    fi
    
    return $failed_checks
}

# Function to setup cron jobs
setup_cron() {
    log "Setting up cron jobs..."
    
    # Create cron job for backups
    local cron_entry="0 2 * * * ${SCRIPT_DIR}/backup.sh >> ${BACKUP_DIR}/logs/cron.log 2>&1"
    
    # Check if cron job already exists
    if ! crontab -l 2>/dev/null | grep -q "${SCRIPT_DIR}/backup.sh"; then
        # Add cron job
        (crontab -l 2>/dev/null; echo "$cron_entry") | crontab -
        success "Backup cron job added"
    else
        info "Backup cron job already exists"
    fi
    
    # Create cron job for auto-scaling (optional)
    local scale_cron="*/5 * * * * ${SCRIPT_DIR}/scale.sh auto-scale >> ${BACKUP_DIR}/logs/scale.log 2>&1"
    
    if ! crontab -l 2>/dev/null | grep -q "${SCRIPT_DIR}/scale.sh"; then
        read -p "Do you want to enable auto-scaling every 5 minutes? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            (crontab -l 2>/dev/null; echo "$scale_cron") | crontab -
            success "Auto-scaling cron job added"
        fi
    fi
}

# Function to show deployment summary
show_summary() {
    info "=== Deployment Summary ==="
    echo
    success "Odoo SaaS System deployed successfully!"
    echo
    info "Services:"
    info "  - Nginx (Load Balancer): http://localhost"
    info "  - Odoo Master: http://localhost:8069"
    info "  - SaaS Manager: http://localhost:8000"
    info "  - PostgreSQL: localhost:5432"
    info "  - Redis: localhost:6379"
    info "  - Portainer: http://localhost:9000"
    echo
    info "Important files:"
    info "  - Environment: ${ENV_FILE}"
    info "  - Docker Compose: ${COMPOSE_FILE}"
    info "  - Backups: ${BACKUP_DIR}"
    echo
    info "Management scripts:"
    info "  - Backup: ${SCRIPT_DIR}/backup.sh"
    info "  - Scaling: ${SCRIPT_DIR}/scale.sh"
    echo
    warning "Next steps:"
    warning "1. Access Odoo Master at http://localhost:8069 to create your first database"
    warning "2. Configure your SaaS Manager at http://localhost:8000"
    warning "3. Review and customize nginx configuration for your domain"
    warning "4. Set up proper SSL certificates for production"
    warning "5. Configure monitoring and logging as needed"
    echo
}

# Function to cleanup on failure
cleanup_on_failure() {
    error "Deployment failed. Cleaning up..."
    
    cd "${PROJECT_ROOT}"
    docker-compose down --remove-orphans
    
    # Optionally remove volumes (uncomment if needed)
    # docker-compose down -v --remove-orphans
    
    error "Cleanup completed. Please check the logs and try again."
}

# Function to show usage
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo
    echo "Options:"
    echo "  --with-ssl          Enable SSL setup with self-signed certificates"
    echo "  --skip-build        Skip building custom Docker images"
    echo "  --skip-cron         Skip setting up cron jobs"
    echo "  --force             Force deployment even if services are already running"
    echo "  --help              Show this help message"
    echo
    echo "Examples:"
    echo "  $0                  # Basic deployment"
    echo "  $0 --with-ssl       # Deployment with SSL"
    echo "  $0 --skip-build     # Skip image building"
}

# Main deployment function
main() {
    local with_ssl=false
    local skip_build=false
    local skip_cron=false
    local force=false
    
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --with-ssl)
                with_ssl=true
                shift
                ;;
            --skip-build)
                skip_build=true
                shift
                ;;
            --skip-cron)
                skip_cron=true
                shift
                ;;
            --force)
                force=true
                shift
                ;;
            --help)
                usage
                exit 0
                ;;
            *)
                error "Unknown option: $1"
                usage
                exit 1
                ;;
        esac
    done
    
    # Set trap for cleanup on failure
    trap cleanup_on_failure ERR
    
    log "=== Starting Odoo SaaS System Deployment ==="
    
    # Check if already running
    if [ "$force" = false ] && docker-compose ps | grep -q "Up"; then
        warning "Services are already running. Use --force to redeploy."
        exit 1
    fi
    
    # Execute deployment steps
    check_requirements
    create_directories
    
    if [ ! -f "${ENV_FILE}" ]; then
        setup_environment
    else
        log "Environment file exists, skipping environment setup"
    fi
    
    setup_ssl "$with_ssl"
    
    if [ "$skip_build" = false ]; then
        build_images
    else
        log "Skipping image building"
    fi
    
    init_databases
    start_services
    
    # Wait a bit for services to fully initialize
    log "Waiting for services to fully initialize..."
    sleep 10
    
    health_check
    
    if [ "$skip_cron" = false ]; then
        setup_cron
    else
        log "Skipping cron setup"
    fi
    
    # Remove trap
    trap - ERR
    
    show_summary
    
    success "=== Deployment completed successfully! ==="
}

# Check if script is run as root for certain operations
if [ "$EUID" -eq 0 ]; then
    warning "Running as root. Some operations might behave differently."
fi

# Change to project root directory
cd "${PROJECT_ROOT}"

# Run main function with all arguments
main "$@"