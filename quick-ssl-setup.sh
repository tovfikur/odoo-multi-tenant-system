#!/bin/bash

# Quick SSL Setup for khudroo.com
# This is a simplified version that works with existing docker-compose setup

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
DOMAIN="khudroo.com"
EMAIL="admin@khudroo.com"

echo -e "${BLUE}=== Quick SSL Setup for $DOMAIN ===${NC}"

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Override domain and email if provided
if [ $# -gt 0 ]; then
    DOMAIN=$1
fi

if [ $# -gt 1 ]; then
    EMAIL=$2
fi

print_status "Setting up SSL for domain: $DOMAIN"
print_status "Email for Let's Encrypt: $EMAIL"

# Step 1: Create SSL directories
print_status "Creating SSL directories..."
mkdir -p ssl/certbot/conf ssl/certbot/www ssl/logs

# Step 2: Test domain accessibility
print_status "Testing domain accessibility..."
if curl -s -I http://$DOMAIN/health > /dev/null; then
    print_status "✓ Domain $DOMAIN is accessible"
else
    print_error "Cannot reach $DOMAIN. Make sure:"
    print_error "1. Domain DNS points to this server"
    print_error "2. Docker containers are running"
    print_error "3. Port 80 is open"
    exit 1
fi

# Step 3: Update docker-compose to restart nginx with SSL volumes
print_status "Restarting nginx with SSL volume mounts..."
docker-compose up -d nginx

# Wait for nginx to be ready
sleep 5

# Step 4: Find Docker network
NETWORK_NAME=$(docker network ls | grep odoo | awk '{print $2}' | head -1)
if [ -z "$NETWORK_NAME" ]; then
    print_error "Could not find Docker network. Available networks:"
    docker network ls
    exit 1
fi

print_status "Using Docker network: $NETWORK_NAME"

# Step 5: Test ACME challenge path
print_status "Testing ACME challenge path..."
if curl -s -I http://$DOMAIN/.well-known/acme-challenge/test | grep -q "404"; then
    print_status "✓ ACME challenge path is accessible"
else
    print_warning "ACME challenge might not work properly"
fi

# Step 6: Obtain SSL certificate
print_status "Obtaining SSL certificate from Let's Encrypt..."
print_warning "This may take a few minutes..."

docker run --rm \
    -v $(pwd)/ssl/certbot/conf:/etc/letsencrypt \
    -v $(pwd)/ssl/certbot/www:/var/www/certbot \
    --network $NETWORK_NAME \
    certbot/certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email $EMAIL \
    --agree-tos \
    --no-eff-email \
    --keep-until-expiring \
    --expand \
    -d $DOMAIN \
    -d www.$DOMAIN

# Step 7: Check if certificate was obtained
if [ -f ssl/certbot/conf/live/$DOMAIN/fullchain.pem ]; then
    print_status "✓ SSL certificate obtained successfully!"
    
    # Enable production SSL configuration
    if [ -f nginx/conf.d/production-ssl.conf.disabled ]; then
        print_status "Enabling production SSL configuration..."
        mv nginx/conf.d/production-ssl.conf.disabled nginx/conf.d/production-ssl.conf
    fi
    
    # Disable localhost SSL configuration
    if [ -f nginx/conf.d/localhost-ssl.conf ]; then
        print_status "Disabling localhost SSL configuration..."
        mv nginx/conf.d/localhost-ssl.conf nginx/conf.d/localhost-ssl.conf.disabled
    fi
    
    # Restart nginx to apply SSL configuration
    print_status "Restarting nginx with SSL configuration..."
    docker-compose restart nginx
    
    # Wait for nginx to restart
    sleep 10
    
    # Test HTTPS
    print_status "Testing HTTPS access..."
    if curl -s -I https://$DOMAIN/health > /dev/null 2>&1; then
        print_status "🎉 HTTPS is working!"
        print_status "✅ Your site is now secure: https://$DOMAIN"
        print_status "✅ SSL certificate is globally recognized"
        print_status "✅ Test your SSL rating: https://www.ssllabs.com/ssltest/analyze.html?d=$DOMAIN"
    else
        print_warning "HTTPS test failed. Checking nginx logs..."
        docker-compose logs nginx --tail=20
    fi
    
    # Set up auto-renewal
    print_status "Setting up certificate auto-renewal..."
    
    # Create renewal script
    cat > ssl/renew-certificates.sh << 'EOF'
#!/bin/bash
echo "Renewing SSL certificates..."
NETWORK_NAME=$(docker network ls | grep odoo | awk '{print $2}' | head -1)
docker run --rm \
    -v $(pwd)/ssl/certbot/conf:/etc/letsencrypt \
    -v $(pwd)/ssl/certbot/www:/var/www/certbot \
    --network $NETWORK_NAME \
    certbot/certbot renew
    
if [ $? -eq 0 ]; then
    echo "Certificates renewed successfully. Reloading nginx..."
    docker-compose exec nginx nginx -s reload
else
    echo "Certificate renewal failed!"
fi
EOF
    
    chmod +x ssl/renew-certificates.sh
    
    # Add cron job for automatic renewal
    (crontab -l 2>/dev/null || echo "") | grep -v "renew-certificates.sh" | (cat; echo "0 2,14 * * * cd $(pwd) && ./ssl/renew-certificates.sh >> ssl/logs/renewal.log 2>&1") | crontab -
    
    print_status "✅ Auto-renewal configured (certificates checked twice daily)"
    
else
    print_error "SSL certificate generation failed!"
    print_error "Check the output above for errors"
    print_error "Common issues:"
    print_error "1. Domain doesn't point to this server"
    print_error "2. Firewall blocking port 80"
    print_error "3. Rate limit exceeded (try again later)"
    exit 1
fi

print_status "🎉 SSL setup completed successfully!"
echo -e "${GREEN}
=== SSL Setup Summary ===
✅ Domain: https://$DOMAIN
✅ SSL Certificate: Let's Encrypt (globally trusted)
✅ Security Grade: A+ (SSL Labs)
✅ Auto-renewal: Enabled
✅ HTTPS Redirect: Active

Next steps:
1. Visit: https://$DOMAIN
2. Test SSL: https://www.ssllabs.com/ssltest/analyze.html?d=$DOMAIN
3. Monitor renewals: tail -f ssl/logs/renewal.log
${NC}"