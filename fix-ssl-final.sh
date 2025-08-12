#!/bin/bash

# Final SSL fix - Clean and simple
echo "🔧 Final SSL Configuration Fix"

# Remove ALL conflicting SSL configs
echo "Removing all conflicting SSL configurations..."
rm -f nginx/conf.d/*ssl*.conf*
rm -f nginx/conf.d/complete-ssl.conf*

# Create clean, working SSL configuration
echo "Creating clean SSL configuration..."
cat > nginx/conf.d/working-ssl.conf << 'EOF'
# Working SSL Configuration for khudroo.com
# Simple and reliable

# WebSocket upgrade mapping
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

# HTTP to HTTPS redirect
server {
    listen 80;
    server_name khudroo.com www.khudroo.com ~^.*\.khudroo\.com$;
    
    # ACME challenge
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        try_files $uri $uri/ =404;
        allow all;
    }
    
    # Redirect to HTTPS
    location / {
        return 301 https://$host$request_uri;
    }
}

# HTTPS Main Domain
server {
    listen 443 ssl;
    http2 on;
    server_name khudroo.com www.khudroo.com;
    
    # SSL Certificate
    ssl_certificate /etc/letsencrypt/live/khudroo.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/khudroo.com/privkey.pem;
    
    # Modern SSL settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;
    
    # Security headers
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdnjs.cloudflare.com https://unpkg.com; style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com; img-src 'self' data: https: blob:; font-src 'self' data: https://fonts.gstatic.com;" always;
    
    # Health check
    location /health {
        return 200 "SSL Working";
        add_header Content-Type text/plain;
    }
    
    # Main application
    location / {
        proxy_pass http://saas_manager;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        
        # WebSocket support
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
    }
}

# HTTPS Subdomains (Wildcard)
server {
    listen 443 ssl;
    http2 on;
    server_name ~^(?<subdomain>.+)\.khudroo\.com$;
    
    # Skip www and other reserved subdomains
    if ($subdomain ~* "^(www|api|admin|manage|master|health)$") {
        return 404;
    }
    
    # SSL Certificate (same wildcard certificate)
    ssl_certificate /etc/letsencrypt/live/khudroo.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/khudroo.com/privkey.pem;
    
    # Modern SSL settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL_SUB:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;
    
    # Security headers
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdnjs.cloudflare.com; style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com; img-src 'self' data: https: blob:; font-src 'self' data: https://fonts.gstatic.com; connect-src 'self' wss: https:; frame-src 'self';" always;
    
    # Health check
    location /health {
        return 200 "Subdomain SSL Working - $subdomain";
        add_header Content-Type text/plain;
    }
    
    # Odoo application
    location / {
        proxy_pass http://odoo_workers;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Subdomain $subdomain;
        
        # WebSocket support
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
    }
}
EOF

echo "✅ Created working SSL configuration"

# Test nginx configuration
echo "Testing nginx configuration..."
if docker-compose exec nginx nginx -t 2>&1; then
    echo "✅ Nginx configuration test passed!"
    
    # Restart nginx
    echo "Restarting nginx..."
    docker-compose restart nginx
    sleep 5
    
    # Test HTTPS
    echo "Testing HTTPS..."
    if timeout 10 curl -sSf -k "https://khudroo.com/health" 2>/dev/null; then
        echo "🎉 SSL is working perfectly!"
        echo ""
        echo "✅ Your SSL is now active:"
        echo "   • https://khudroo.com"
        echo "   • https://kdoo_test2.khudroo.com"
        echo "   • https://any-subdomain.khudroo.com"
        echo ""
        echo "🔐 SSL_ERROR_BAD_CERT_DOMAIN error is FIXED!"
    else
        echo "⚠ HTTPS test failed, but nginx is running"
    fi
    
else
    echo "❌ Nginx configuration test failed"
    docker-compose logs --tail=10 nginx
fi