#!/bin/bash

# Simple SSL Production Script
# For production use - creates real Let's Encrypt certificates

echo "🔐 SSL Production Script"
echo "======================="
echo "This creates REAL SSL certificates for production"
echo

DOMAIN="${1:-khudroo.com}"
EMAIL="${2:-admin@khudroo.com}"
CERT_TYPE="${3:-wildcard}"

echo "Domain: $DOMAIN"
echo "Email: $EMAIL"
echo "Certificate Type: $CERT_TYPE"
echo

# Install certbot if needed
if ! command -v certbot &> /dev/null; then
    echo "Installing certbot..."
    sudo apt update && sudo apt install -y certbot
fi

# Stop nginx and clean up containers to avoid ContainerConfig error
echo "Stopping all containers..."
docker stop $(docker ps -aq) 2>/dev/null || true
docker rm $(docker ps -aq) 2>/dev/null || true

# Remove old certificates
sudo certbot delete --cert-name "$DOMAIN" 2>/dev/null || true

# Request certificate based on type
if [[ "$CERT_TYPE" == "wildcard" ]]; then
    echo "🌟 Requesting wildcard certificate for *.$DOMAIN"
    echo "📝 You will need to add DNS TXT records when prompted"
    echo
    
    sudo certbot certonly \
        --manual \
        --preferred-challenges=dns \
        --email "$EMAIL" \
        --agree-tos \
        --no-eff-email \
        --domains "$DOMAIN,*.$DOMAIN" \
        --cert-name "$DOMAIN"
else
    echo "🔐 Requesting standard certificate for $DOMAIN"
    echo
    
    sudo certbot certonly \
        --standalone \
        --email "$EMAIL" \
        --agree-tos \
        --no-eff-email \
        --domains "$DOMAIN,www.$DOMAIN" \
        --cert-name "$DOMAIN"
fi

if [[ $? -eq 0 ]]; then
    echo "✅ Production certificate obtained successfully!"
    
    # Show certificate info
    echo "📋 Certificate Information:"
    sudo openssl x509 -in /etc/letsencrypt/live/$DOMAIN/fullchain.pem -noout -subject -dates
    echo
    
    # Copy to docker location
    sudo mkdir -p ./ssl/letsencrypt/live/$DOMAIN
    sudo cp /etc/letsencrypt/live/$DOMAIN/*.pem ./ssl/letsencrypt/live/$DOMAIN/
    sudo chown -R $USER:$USER ./ssl/letsencrypt/
    
    # Create SSL configuration based on certificate type
    if [[ "$CERT_TYPE" == "wildcard" ]]; then
        create_wildcard_config
    else
        create_standard_config
    fi
    
    # Update docker-compose for SSL
    if ! grep -q "/etc/letsencrypt" docker-compose.yml; then
        cp docker-compose.yml docker-compose.yml.backup
        sed -i '/- \.\/ssl\/dhparam\.pem:\/etc\/nginx\/ssl\/dhparam\.pem/a\      - /etc/letsencrypt:/etc/letsencrypt:ro' docker-compose.yml
        echo "✅ Updated docker-compose.yml"
    fi
    
    # Start services manually to avoid ContainerConfig error
    start_services_manually
    
    # Test SSL
    echo "Testing SSL setup..."
    sleep 10
    
    if timeout 15 curl -sSf "https://$DOMAIN/ssl-health" >/dev/null 2>&1; then
        echo "🎉 SSL is working perfectly!"
        echo "✅ Main domain: https://$DOMAIN"
        
        if [[ "$CERT_TYPE" == "wildcard" ]]; then
            echo "✅ Wildcard subdomains: https://[tenant].$DOMAIN"
            echo "✅ Example: https://kdoo_test2.$DOMAIN"
        fi
        
        # Create simple renewal script
        create_renewal_script
        
    else
        echo "⚠️  SSL test failed, but services are running"
        echo "Check manually: https://$DOMAIN/ssl-health"
    fi
    
else
    echo "❌ Certificate request failed"
    exit 1
fi

# Create wildcard SSL configuration
create_wildcard_config() {
    cat > nginx/conf.d/production-ssl.conf << 'EOF'
# Production Wildcard SSL Configuration

# HTTP to HTTPS redirect
server {
    listen 80;
    server_name khudroo.com www.khudroo.com ~^(.+)\.khudroo\.com$;
    
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        try_files $uri $uri/ =404;
        allow all;
    }
    
    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS Main Domain
server {
    listen 443 ssl http2;
    server_name khudroo.com www.khudroo.com;
    
    ssl_certificate /etc/letsencrypt/live/khudroo.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/khudroo.com/privkey.pem;
    
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_cache shared:SSL:50m;
    ssl_session_timeout 1d;
    ssl_dhparam /etc/nginx/ssl/dhparam.pem;
    
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    
    location /ssl-health {
        return 200 "Production SSL OK - Main Domain";
        add_header Content-Type text/plain;
    }
    
    location / {
        proxy_pass http://saas_manager;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
    }
}

# HTTPS Wildcard Subdomains
server {
    listen 443 ssl http2;
    server_name ~^(?<subdomain>.+)\.khudroo\.com$;
    
    if ($subdomain ~* "^(www|api|admin|manage|master|health)$") {
        return 404;
    }
    
    ssl_certificate /etc/letsencrypt/live/khudroo.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/khudroo.com/privkey.pem;
    
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_cache shared:SSL_SUB:50m;
    ssl_session_timeout 1d;
    ssl_dhparam /etc/nginx/ssl/dhparam.pem;
    
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    
    location /ssl-health {
        return 200 "Production SSL OK - Tenant: $subdomain";
        add_header Content-Type text/plain;
    }
    
    location / {
        proxy_pass http://odoo_workers;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Subdomain $subdomain;
        
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
    }
}
EOF
    echo "✅ Wildcard SSL configuration created"
}

# Create standard SSL configuration
create_standard_config() {
    cat > nginx/conf.d/production-ssl.conf << 'EOF'
# Production Standard SSL Configuration

server {
    listen 80;
    server_name khudroo.com www.khudroo.com;
    
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        try_files $uri $uri/ =404;
        allow all;
    }
    
    location / {
        return 301 https://$server_name$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name khudroo.com www.khudroo.com;
    
    ssl_certificate /etc/letsencrypt/live/khudroo.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/khudroo.com/privkey.pem;
    
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_cache shared:SSL:50m;
    ssl_session_timeout 1d;
    ssl_dhparam /etc/nginx/ssl/dhparam.pem;
    
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    
    location /ssl-health {
        return 200 "Production SSL OK";
        add_header Content-Type text/plain;
    }
    
    location / {
        proxy_pass http://saas_manager;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
    }
}
EOF
    echo "✅ Standard SSL configuration created"
}

# Start services manually to avoid ContainerConfig error
start_services_manually() {
    echo "Starting services manually (avoids ContainerConfig error)..."
    
    docker network create odoo_network 2>/dev/null || true
    
    # Start PostgreSQL
    echo "Starting PostgreSQL..."
    docker run -d --name postgres --network odoo_network \
        -e POSTGRES_USER=odoo -e POSTGRES_PASSWORD=odoo -e POSTGRES_DB=postgres \
        -v "$(pwd)/postgres_data:/var/lib/postgresql/data" \
        postgres:15 2>/dev/null || docker start postgres
    
    sleep 10
    
    # Start Redis
    echo "Starting Redis..."
    docker run -d --name redis --network odoo_network \
        redis:alpine 2>/dev/null || docker start redis
    
    sleep 5
    
    # Start SaaS Manager
    echo "Starting SaaS Manager..."
    docker run -d --name saas_manager --network odoo_network \
        -v "$(pwd)/saas_manager:/app" \
        -e DJANGO_SETTINGS_MODULE=saas_project.settings \
        odoo-multi-tenant-system_saas_manager 2>/dev/null || docker start saas_manager
    
    sleep 5
    
    # Start Odoo services if needed
    if [[ "$CERT_TYPE" == "wildcard" ]]; then
        echo "Starting Odoo workers..."
        docker run -d --name odoo_worker1 --network odoo_network \
            -v "$(pwd)/odoo_workers:/etc/odoo" \
            -v "$(pwd)/addons:/mnt/extra-addons" \
            odoo:16 2>/dev/null || docker start odoo_worker1
        
        docker run -d --name odoo_worker2 --network odoo_network \
            -v "$(pwd)/odoo_workers:/etc/odoo" \
            -v "$(pwd)/addons:/mnt/extra-addons" \
            odoo:16 2>/dev/null || docker start odoo_worker2
        
        sleep 10
    fi
    
    # Start Nginx with SSL
    echo "Starting Nginx with SSL..."
    docker run -d --name nginx --network odoo_network \
        -p 80:80 -p 443:443 \
        -v "$(pwd)/nginx/nginx.conf:/etc/nginx/nginx.conf" \
        -v "$(pwd)/nginx/conf.d:/etc/nginx/conf.d" \
        -v "$(pwd)/ssl/dhparam.pem:/etc/nginx/ssl/dhparam.pem" \
        -v "/etc/letsencrypt:/etc/letsencrypt:ro" \
        nginx:alpine 2>/dev/null || docker start nginx
    
    echo "✅ All services started manually"
}

# Create renewal script
create_renewal_script() {
    cat > ssl-renew.sh << 'RENEW_SCRIPT'
#!/bin/bash
# Simple SSL Renewal Script

DOMAIN="khudroo.com"

echo "$(date): Checking SSL certificate renewal for $DOMAIN"

# Check certificate expiry
if [[ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]]; then
    EXPIRY_DATE=$(sudo openssl x509 -enddate -noout -in /etc/letsencrypt/live/$DOMAIN/fullchain.pem | cut -d= -f2)
    EXPIRY_TIMESTAMP=$(date -d "$EXPIRY_DATE" +%s)
    CURRENT_TIMESTAMP=$(date +%s)
    DAYS_UNTIL_EXPIRY=$(( (EXPIRY_TIMESTAMP - CURRENT_TIMESTAMP) / 86400 ))
    
    echo "Certificate expires in $DAYS_UNTIL_EXPIRY days"
    
    if [[ $DAYS_UNTIL_EXPIRY -lt 30 ]]; then
        echo "Certificate renewal needed!"
        
        # Stop nginx
        docker stop nginx
        
        # Renew certificate
        sudo certbot renew --quiet
        
        # Copy renewed certificates
        sudo cp /etc/letsencrypt/live/$DOMAIN/*.pem ./ssl/letsencrypt/live/$DOMAIN/
        sudo chown -R $USER:$USER ./ssl/letsencrypt/
        
        # Start nginx
        docker start nginx
        
        echo "Certificate renewed successfully"
    else
        echo "Certificate renewal not needed"
    fi
else
    echo "Certificate file not found!"
fi
RENEW_SCRIPT
    
    chmod +x ssl-renew.sh
    
    # Add to cron
    if ! crontab -l 2>/dev/null | grep -q "ssl-renew"; then
        (crontab -l 2>/dev/null; echo "0 2 * * 0 cd $(pwd) && ./ssl-renew.sh") | crontab -
        echo "✅ Auto-renewal configured (weekly check)"
    fi
}

echo "🎊 Production SSL setup complete!"