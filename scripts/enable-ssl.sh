#!/bin/bash

# Script to enable SSL configuration when certificates are available
# Usage: ./enable-ssl.sh

SSL_CERT_PATH="/etc/nginx/ssl/khudroo.com.crt"
SSL_KEY_PATH="/etc/nginx/ssl/khudroo.com.key"
NGINX_CONF="/etc/nginx/nginx.conf"
SSL_CONF="/etc/nginx/ssl.conf"

echo "Checking for SSL certificates..."

# Check if SSL certificates exist
if [ -f "$SSL_CERT_PATH" ] && [ -f "$SSL_KEY_PATH" ]; then
    echo "✓ SSL certificates found!"
    echo "✓ Certificate: $SSL_CERT_PATH"
    echo "✓ Private Key: $SSL_KEY_PATH"
    
    # Check if SSL is already enabled
    if grep -q "include.*ssl.conf" "$NGINX_CONF"; then
        echo "✓ SSL is already enabled in nginx.conf"
    else
        echo "Enabling SSL configuration..."
        
        # Backup the current nginx.conf
        cp "$NGINX_CONF" "${NGINX_CONF}.backup.$(date +%Y%m%d_%H%M%S)"
        echo "✓ Backup created: ${NGINX_CONF}.backup.$(date +%Y%m%d_%H%M%S)"
        
        # Enable SSL by uncommenting the include line
        sed -i 's|# include /etc/nginx/conf.d/ssl.conf;|include /etc/nginx/ssl.conf;|' "$NGINX_CONF"
        echo "✓ SSL configuration enabled"
    fi
    
    # Test nginx configuration
    echo "Testing nginx configuration..."
    if nginx -t; then
        echo "✓ Nginx configuration is valid"
        echo "You can now restart nginx to enable SSL:"
        echo "  docker-compose restart nginx"
        echo ""
        echo "Or reload nginx configuration:"
        echo "  docker-compose exec nginx nginx -s reload"
    else
        echo "✗ Nginx configuration test failed"
        echo "Please check the SSL certificate paths and try again"
        exit 1
    fi
    
else
    echo "✗ SSL certificates not found!"
    echo "Expected locations:"
    echo "  Certificate: $SSL_CERT_PATH"
    echo "  Private Key: $SSL_KEY_PATH"
    echo ""
    echo "To set up SSL certificates:"
    echo "1. For production: Use Let's Encrypt or your SSL provider"
    echo "2. For development: Generate self-signed certificates"
    echo ""
    echo "The system will continue to run on HTTP (port 80) until SSL certificates are available."
    exit 1
fi
