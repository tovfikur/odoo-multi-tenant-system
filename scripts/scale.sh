#!/bin/bash

# Odoo SaaS System Scaling Script
# This script helps scale worker instances up or down based on demand

set -e

# Configuration
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
WORKER_PREFIX="odoo_worker"
MIN_WORKERS=2
MAX_WORKERS=10
LOAD_THRESHOLD=80

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Function to get current worker count
get_current_workers() {
    docker-compose -f "${COMPOSE_FILE}" ps --services | grep -c "${WORKER_PREFIX}" || echo "0"
}

# Function to get worker load
get_worker_load() {
    local worker_name=$1
    
    # Get CPU usage for the worker container
    local cpu_usage=$(docker stats --no-stream --format "table {{.CPUPerc}}" "${worker_name}" 2>/dev/null | tail -n 1 | sed 's/%//')
    
    if [ -n "${cpu_usage}" ] && [ "${cpu_usage}" != "CPUPerc" ]; then
        echo "${cpu_usage}"
    else
        echo "0"
    fi
}

# Function to scale up workers
scale_up() {
    local target_workers=$1
    local current_workers=$(get_current_workers)
    
    if [ "${target_workers}" -le "${current_workers}" ]; then
        warning "Already have ${current_workers} workers. No need to scale up to ${target_workers}."
        return 0
    fi
    
    if [ "${target_workers}" -gt "${MAX_WORKERS}" ]; then
        error "Cannot scale beyond maximum of ${MAX_WORKERS} workers"
        return 1
    fi
    
    log "Scaling up from ${current_workers} to ${target_workers} workers..."
    
    # Add new worker services to docker-compose
    for ((i=current_workers+1; i<=target_workers; i++)); do
        local worker_name="${WORKER_PREFIX}_${i}"
        log "Creating worker: ${worker_name}"
        
        # Create and start the new worker container
        docker-compose -f "${COMPOSE_FILE}" up -d --scale "${WORKER_PREFIX}=${target_workers}"
    done
    
    # Update nginx configuration to include new workers
    update_nginx_config
    
    success "Successfully scaled up to ${target_workers} workers"
}

# Function to scale down workers
scale_down() {
    local target_workers=$1
    local current_workers=$(get_current_workers)
    
    if [ "${target_workers}" -ge "${current_workers}" ]; then
        warning "Already have ${current_workers} workers. No need to scale down to ${target_workers}."
        return 0
    fi
    
    if [ "${target_workers}" -lt "${MIN_WORKERS}" ]; then
        error "Cannot scale below minimum of ${MIN_WORKERS} workers"
        return 1
    fi
    
    log "Scaling down from ${current_workers} to ${target_workers} workers..."
    
    # Stop and remove excess worker containers
    for ((i=target_workers+1; i<=current_workers; i++)); do
        local worker_name="${WORKER_PREFIX}_${i}"
        log "Removing worker: ${worker_name}"
        
        docker-compose -f "${COMPOSE_FILE}" stop "${worker_name}"
        docker-compose -f "${COMPOSE_FILE}" rm -f "${worker_name}"
    done
    
    # Update nginx configuration
    update_nginx_config
    
    success "Successfully scaled down to ${target_workers} workers"
}

# Function to update nginx configuration
update_nginx_config() {
    log "Updating nginx configuration..."
    
    local current_workers=$(get_current_workers)
    local nginx_config="/tmp/nginx_upstream.conf"
    
    # Generate upstream configuration
    cat > "${nginx_config}" << EOF
upstream odoo_workers {
    least_conn;
EOF
    
    for ((i=1; i<=current_workers; i++)); do
        echo "    server ${WORKER_PREFIX}${i}:8069;" >> "${nginx_config}"
    done
    
    echo "}" >> "${nginx_config}"
    
    # Copy to nginx container and reload
    docker cp "${nginx_config}" nginx:/etc/nginx/conf.d/upstream.conf
    docker-compose -f "${COMPOSE_FILE}" exec nginx nginx -s reload
    
    rm -f "${nginx_config}"
    success "Nginx configuration updated"
}

# Function to auto-scale based on load
auto_scale() {
    log "Checking system load for auto-scaling..."
    
    local current_workers=$(get_current_workers)
    local total_load=0
    local active_workers=0
    
    # Calculate average load across all workers
    for ((i=1; i<=current_workers; i++)); do
        local worker_name="${WORKER_PREFIX}${i}"
        local load=$(get_worker_load "${worker_name}")
        
        if [ "${load}" != "0" ]; then
            total_load=$((total_load + ${load%.*})) # Remove decimal part
            ((active_workers++))
        fi
    done
    
    if [ "${active_workers}" -eq 0 ]; then
        warning "No active workers found"
        return 1
    fi
    
    local avg_load=$((total_load / active_workers))
    log "Average worker load: ${avg_load}%"
    
    # Scale up if load is high
    if [ "${avg_load}" -gt "${LOAD_THRESHOLD}" ] && [ "${current_workers}" -lt "${MAX_WORKERS}" ]; then
        local new_workers=$((current_workers + 1))
        log "High load detected (${avg_load}%). Scaling up to ${new_workers} workers."
        scale_up "${new_workers}"
    
    # Scale down if load is low
    elif [ "${avg_load}" -lt 30 ] && [ "${current_workers}" -gt "${MIN_WORKERS}" ]; then
        local new_workers=$((current_workers - 1))
        log "Low load detected (${avg_load}%). Scaling down to ${new_workers} workers."
        scale_down "${new_workers}"
    else
        log "Load is within acceptable range. No scaling needed."
    fi
}

# Function to show current status
show_status() {
    log "=== Odoo SaaS Worker Status ==="
    
    local current_workers=$(get_current_workers)
    echo "Current workers: ${current_workers}"
    echo "Min workers: ${MIN_WORKERS}"
    echo "Max workers: ${MAX_WORKERS}"
    echo ""
    
    echo "Worker Load:"
    for ((i=1; i<=current_workers; i++)); do
        local worker_name="${WORKER_PREFIX}${i}"
        local load=$(get_worker_load "${worker_name}")
        local status=$(docker inspect --format="{{.State.Status}}" "${worker_name}" 2>/dev/null || echo "not found")
        echo "  ${worker_name}: ${load}% CPU (${status})"
    done
}

# Function to check worker health
health_check() {
    log "Performing health check on all workers..."
    
    local current_workers=$(get_current_workers)
    local unhealthy_workers=0
    
    for ((i=1; i<=current_workers; i++)); do
        local worker_name="${WORKER_PREFIX}${i}"
        
        # Check if container is running
        if ! docker inspect --format="{{.State.Running}}" "${worker_name}" 2>/dev/null | grep -q "true"; then
            error "Worker ${worker_name} is not running"
            ((unhealthy_workers++))
            continue
        fi
        
        # Check if Odoo is responding
        if ! docker exec "${worker_name}" curl -f http://localhost:8069/web/health 2>/dev/null >/dev/null; then
            error "Worker ${worker_name} is not responding to health checks"
            ((unhealthy_workers++))
        else
            success "Worker ${worker_name} is healthy"
        fi
    done
    
    if [ "${unhealthy_workers}" -eq 0 ]; then
        success "All workers are healthy"
        return 0
    else
        error "${unhealthy_workers} workers are unhealthy"
        return 1
    fi
}

# Show usage
usage() {
    echo "Usage: $0 {scale-up|scale-down|auto-scale|status|health-check} [number]"
    echo ""
    echo "Commands:"
    echo "  scale-up [N]     Scale up to N workers"
    echo "  scale-down [N]   Scale down to N workers"
    echo "  auto-scale       Automatically scale based on load"
    echo "  status           Show current worker status"
    echo "  health-check     Check health of all workers"
    echo ""
    echo "Examples:"
    echo "  $0 scale-up 5     # Scale up to 5 workers"
    echo "  $0 scale-down 2   # Scale down to 2 workers"
    echo "  $0 auto-scale     # Auto-scale based on current load"
    echo "  $0 status         # Show current status"
}

# Main script logic
case "${1:-}" in
    "scale-up")
        if [ -z "${2}" ]; then
            error "Please specify the number of workers"
            usage
            exit 1
        fi
        scale_up "${2}"
        ;;
    "scale-down")
        if [ -z "${2}" ]; then
            error "Please specify the number of workers"
            usage
            exit 1
        fi
        scale_down "${2}"
        ;;
    "auto-scale")
        auto_scale
        ;;
    "status")
        show_status
        ;;
    "health-check")
        health_check
        ;;
    *)
        usage
        exit 1
        ;;
esac