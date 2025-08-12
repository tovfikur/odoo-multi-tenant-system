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
