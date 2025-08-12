#!/bin/bash

# SSL Master Auto-Renewal Script
cd "$(dirname "$0")/.."

DOMAIN="khudroo.com"
LOG_FILE="ssl/logs/renewal.log"
NETWORK=$(docker network ls --format "{{.Name}}" | grep -E "(odoo|multi.*tenant)" | head -1)

echo "$(date): SSL Master - Starting certificate renewal..." >> "$LOG_FILE"

# Renew certificates
if docker run --rm \
    -v "$(pwd)/ssl/certbot/conf:/etc/letsencrypt" \
    -v "$(pwd)/ssl/certbot/www:/var/www/certbot" \
    --network "${NETWORK:-default}" \
    certbot/certbot renew --quiet; then
    
    echo "$(date): SSL Master - Certificate renewal completed successfully" >> "$LOG_FILE"
    
    # Reload nginx
    if docker-compose exec nginx nginx -s reload 2>/dev/null; then
        echo "$(date): SSL Master - Nginx reloaded successfully" >> "$LOG_FILE"
    else
        echo "$(date): SSL Master - Nginx reload failed, restarting container" >> "$LOG_FILE"
        docker-compose restart nginx
    fi
    
    echo "$(date): SSL Master - Renewal process completed" >> "$LOG_FILE"
else
    echo "$(date): SSL Master - ERROR: Certificate renewal failed" >> "$LOG_FILE"
    exit 1
fi
