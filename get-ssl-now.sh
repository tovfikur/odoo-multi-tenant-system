#!/bin/bash

# Quick SSL Certificate Setup
# Simplified version that bypasses complex network detection

set -e

DOMAIN="khudroo.com"
EMAIL="admin@khudroo.com"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== Quick SSL Setup for $DOMAIN ===${NC}"

# Override domain/email if provided
if [ $# -gt 0 ]; then DOMAIN=$1; fi
if [ $# -gt 1 ]; then EMAIL=$2; fi

# Create directories
echo "Creating SSL directories..."
mkdir -p ssl/certbot/conf ssl/certbot/www ssl/logs

# Get network name directly
echo "Finding Docker network..."
NETWORK_NAME=$(docker network ls --format "{{.Name}}" | grep "odoo-multi-tenant-system" | head -1)

if [ -z "$NETWORK_NAME" ]; then
    echo "Available networks:"
    docker network ls
    echo -e "${RED}Please copy the correct network name and run:${NC}"
    echo "NETWORK_NAME=\"your-network-name\" ./get-ssl-now.sh"
    exit 1
fi

echo -e "${GREEN}Using network: $NETWORK_NAME${NC}"

# Restart nginx to mount volumes
echo "Restarting nginx..."
docker-compose restart nginx
sleep 5

# Test nginx
if curl -s --max-time 5 http://localhost/health > /dev/null; then
    echo -e "${GREEN}✓ Nginx is responding locally${NC}"
else
    echo -e "${YELLOW}⚠ Nginx not responding locally, but continuing...${NC}"
fi

# Get SSL certificate
echo -e "${GREEN}Getting SSL certificate from Let's Encrypt...${NC}"
echo -e "${YELLOW}This validates your domain from the internet${NC}"

docker run --rm \
    -v "$(pwd)/ssl/certbot/conf:/etc/letsencrypt" \
    -v "$(pwd)/ssl/certbot/www:/var/www/certbot" \
    --network "$NETWORK_NAME" \
    certbot/certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    --keep-until-expiring \
    --expand \
    --non-interactive \
    -d "$DOMAIN" \
    -d "www.$DOMAIN"

# Check if certificate was obtained
if [ -f "ssl/certbot/conf/live/$DOMAIN/fullchain.pem" ]; then
    echo -e "${GREEN}✅ SSL Certificate obtained successfully!${NC}"
    
    # Enable production SSL config
    if [ -f "nginx/conf.d/production-ssl.conf.disabled" ]; then
        mv "nginx/conf.d/production-ssl.conf.disabled" "nginx/conf.d/production-ssl.conf"
        echo -e "${GREEN}✓ Production SSL config enabled${NC}"
    fi
    
    # Disable localhost config
    if [ -f "nginx/conf.d/localhost-ssl.conf" ]; then
        mv "nginx/conf.d/localhost-ssl.conf" "nginx/conf.d/localhost-ssl.conf.disabled"
        echo -e "${GREEN}✓ Localhost SSL config disabled${NC}"
    fi
    
    # Add include to nginx.conf if not present
    if ! grep -q "include /etc/nginx/conf.d/\*.conf;" nginx/nginx.conf; then
        sed -i '/^}$/i\    include /etc/nginx/conf.d/*.conf;' nginx/nginx.conf
        echo -e "${GREEN}✓ Added conf.d include to nginx.conf${NC}"
    fi
    
    # Test nginx config
    if docker-compose exec nginx nginx -t; then
        echo -e "${GREEN}✓ Nginx config test passed${NC}"
        
        # Restart nginx
        docker-compose restart nginx
        echo -e "${GREEN}✓ Nginx restarted${NC}"
        
        echo ""
        echo -e "${GREEN}🎉 SSL SETUP COMPLETED!${NC}"
        echo -e "${GREEN}✅ Your site: https://$DOMAIN${NC}"
        echo -e "${GREEN}✅ SSL Certificate: Let's Encrypt (globally trusted)${NC}"
        echo -e "${GREEN}✅ Test SSL: https://www.ssllabs.com/ssltest/analyze.html?d=$DOMAIN${NC}"
        
        # Setup auto-renewal
        cat > ssl/renew.sh << 'EOF'
#!/bin/bash
cd "$(dirname "$0")/.."
NETWORK=$(docker network ls --format "{{.Name}}" | grep "odoo-multi-tenant-system" | head -1)
docker run --rm \
    -v "$(pwd)/ssl/certbot/conf:/etc/letsencrypt" \
    -v "$(pwd)/ssl/certbot/www:/var/www/certbot" \
    --network "$NETWORK" \
    certbot/certbot renew
docker-compose exec nginx nginx -s reload
EOF
        chmod +x ssl/renew.sh
        
        # Add to cron
        (crontab -l 2>/dev/null | grep -v "ssl/renew.sh"; echo "0 2,14 * * * cd $(pwd) && ./ssl/renew.sh >> ssl/logs/renewal.log 2>&1") | crontab -
        
        echo -e "${GREEN}✅ Auto-renewal setup complete${NC}"
        
    else
        echo -e "${RED}✗ Nginx config test failed${NC}"
        docker-compose logs nginx --tail=10
    fi
    
else
    echo -e "${RED}✗ SSL certificate generation failed${NC}"
    echo -e "${YELLOW}Common issues:${NC}"
    echo -e "${YELLOW}1. Domain doesn't point to this server's public IP${NC}"
    echo -e "${YELLOW}2. Firewall blocking port 80${NC}"
    echo -e "${YELLOW}3. Let's Encrypt rate limit${NC}"
fi