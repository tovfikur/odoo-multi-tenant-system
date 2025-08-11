#!/bin/bash

# Fix SSL configuration conflicts
set -e

cd ~/odoo-multi-tenant-system

echo "Fixing SSL configuration conflicts..."

# Disable the conflicting ssl.conf file
if [ -f "nginx/conf.d/ssl.conf" ]; then
    mv "nginx/conf.d/ssl.conf" "nginx/conf.d/ssl.conf.disabled.$(date +%s)"
    echo "✓ Disabled conflicting ssl.conf"
fi

# Disable any other conflicting configs
for config in nginx/conf.d/*.conf.disabled.*; do
    if [[ -f "$config" ]]; then
        echo "✓ Already disabled: $(basename "$config")"
    fi
done

# Test nginx configuration
echo "Testing nginx configuration..."
if docker-compose exec nginx nginx -t 2>&1; then
    echo "✓ Nginx configuration test passed"
    
    # Restart nginx
    echo "Restarting nginx..."
    docker-compose restart nginx
    sleep 5
    echo "✓ Nginx restarted successfully"
    
    # Test HTTPS
    echo "Testing HTTPS connectivity..."
    if curl -sSf -k "https://khudroo.com/health" &>/dev/null; then
        echo "✅ HTTPS is working!"
        echo "🌐 Test your wildcard SSL:"
        echo "   • https://khudroo.com"
        echo "   • https://kdoo_test2.khudroo.com"
        echo "   • https://any-subdomain.khudroo.com"
    else
        echo "⚠ HTTPS test failed, but configuration is valid"
    fi
    
else
    echo "✗ Nginx configuration test failed"
    docker-compose logs --tail=20 nginx
fi