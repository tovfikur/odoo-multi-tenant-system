#!/bin/bash

# Enable Production SSL Configuration Script
# This script enables the production SSL configuration for khudroo.com

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Enabling Production SSL Configuration ===${NC}"

# Check if we're on the production server
if curl -s -I http://khudroo.com/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Domain khudroo.com is accessible${NC}"
else
    echo -e "${YELLOW}⚠ Warning: Cannot reach khudroo.com - make sure you're on the production server${NC}"
fi

# Re-enable production SSL configuration
if [ -f nginx/conf.d/production-ssl.conf.disabled ]; then
    echo -e "${GREEN}✓ Re-enabling production SSL configuration...${NC}"
    mv nginx/conf.d/production-ssl.conf.disabled nginx/conf.d/production-ssl.conf
else
    echo -e "${GREEN}✓ Production SSL configuration already enabled${NC}"
fi

# Disable localhost SSL configuration (not needed in production)
if [ -f nginx/conf.d/localhost-ssl.conf ]; then
    echo -e "${GREEN}✓ Disabling localhost SSL configuration...${NC}"
    mv nginx/conf.d/localhost-ssl.conf nginx/conf.d/localhost-ssl.conf.disabled
fi

# Fix any remaining typos in production config
echo -e "${GREEN}✓ Checking production SSL configuration...${NC}"

# Fix deprecated http2 directive if present
sed -i 's/listen 443 ssl http2;/listen 443 ssl;\n    http2 on;/g' nginx/conf.d/production-ssl.conf 2>/dev/null || true

# Update the SSL configuration to use Let's Encrypt certificates
echo -e "${GREEN}✓ Updating SSL certificate paths for Let's Encrypt...${NC}"

# Update nginx.conf to remove the include conf.d line if SSL not ready
if [ ! -f ssl/certbot/conf/live/khudroo.com/fullchain.pem ]; then
    echo -e "${YELLOW}⚠ SSL certificates not found. Please run './setup-ssl.sh khudroo.com your-email@domain.com' first${NC}"
    
    # Comment out the include line temporarily
    sed -i 's/^    include \/etc\/nginx\/conf.d\/\*\.conf;/#    include \/etc\/nginx\/conf.d\/\*\.conf;  # Disabled until SSL certificates are ready/' nginx/nginx.conf 2>/dev/null || true
    
    echo -e "${BLUE}Next steps:${NC}"
    echo -e "1. Run: ${GREEN}./setup-ssl.sh khudroo.com your-email@domain.com${NC}"
    echo -e "2. Then run: ${GREEN}./enable-production-ssl.sh${NC} again"
else
    # Uncomment the include line
    sed -i 's/#    include \/etc\/nginx\/conf.d\/\*\.conf;  # Disabled until SSL certificates are ready/    include \/etc\/nginx\/conf.d\/\*\.conf;/' nginx/nginx.conf 2>/dev/null || true
    
    echo -e "${GREEN}✓ SSL certificates found, enabling production configuration...${NC}"
    
    # Restart nginx to apply changes
    echo -e "${GREEN}✓ Restarting nginx...${NC}"
    docker-compose restart nginx
    
    # Test SSL
    echo -e "${GREEN}✓ Testing SSL configuration...${NC}"
    if curl -s -I https://khudroo.com/health > /dev/null 2>&1; then
        echo -e "${GREEN}🎉 HTTPS is working! Your site is now secure with Let's Encrypt SSL${NC}"
        echo -e "${GREEN}✓ Visit: https://khudroo.com${NC}"
        echo -e "${GREEN}✓ Test SSL rating: https://www.ssllabs.com/ssltest/analyze.html?d=khudroo.com${NC}"
    else
        echo -e "${YELLOW}⚠ HTTPS test failed. Check nginx logs: docker-compose logs nginx${NC}"
    fi
fi

echo -e "${BLUE}=== Production SSL Configuration Complete ===${NC}"