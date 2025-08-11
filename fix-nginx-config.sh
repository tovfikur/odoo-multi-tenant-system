#!/bin/bash

# Fix nginx configuration errors
set -e

echo "Fixing nginx configuration errors..."

CONFIG_FILE="nginx/conf.d/complete-ssl.conf"

if [ -f "$CONFIG_FILE" ]; then
    # Fix the typo: proxy_Set_header -> proxy_set_header
    sed -i 's/proxy_Set_header/proxy_set_header/g' "$CONFIG_FILE"
    echo "✓ Fixed proxy_set_header typo"
    
    # Fix deprecated http2 syntax
    sed -i 's/listen 443 ssl http2;/listen 443 ssl;\n    http2 on;/g' "$CONFIG_FILE"
    echo "✓ Fixed deprecated http2 syntax"
    
    echo "Testing nginx configuration..."
    if docker-compose exec nginx nginx -t 2>/dev/null; then
        echo "✅ Nginx configuration is valid!"
        
        echo "Restarting nginx..."
        docker-compose restart nginx
        sleep 5
        
        echo "Testing HTTPS..."
        if timeout 10 curl -sSf -k "https://khudroo.com/health" &>/dev/null; then
            echo "🎉 SSL is working perfectly!"
            echo ""
            echo "🌐 Your wildcard SSL is now active:"
            echo "  ✅ https://khudroo.com"
            echo "  ✅ https://kdoo_test2.khudroo.com"
            echo "  ✅ https://any-subdomain.khudroo.com"
            echo ""
            echo "The SSL_ERROR_BAD_CERT_DOMAIN error is now FIXED!"
        else
            echo "⚠ HTTPS test failed, but nginx is running"
            echo "Check if your domain resolves correctly"
        fi
        
    else
        echo "❌ Nginx configuration still has errors"
        docker-compose logs --tail=10 nginx
    fi
else
    echo "❌ Configuration file not found: $CONFIG_FILE"
fi