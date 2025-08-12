#!/bin/bash

# Manual SSL Completion Script
# Completes SSL setup after certificate is obtained

echo "🔐 Completing SSL Setup Manually"
echo "================================="

DOMAIN="khudroo.com"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    echo -e "$1"
}

# Step 1: Clean up Docker containers manually
cleanup_docker() {
    log "${BLUE}[1/6] Cleaning up Docker containers...${NC}"
    
    # Stop all containers
    docker stop $(docker ps -aq) 2>/dev/null || true
    
    # Remove problematic containers
    docker rm $(docker ps -aq) 2>/dev/null || true
    
    # Clean up volumes and networks
    docker system prune -f
    docker volume prune -f
    
    log "${GREEN}✅ Docker cleanup completed${NC}"
}

# Step 2: Update docker-compose.yml for SSL
update_docker_compose() {
    log "${BLUE}[2/6] Updating docker-compose.yml for SSL...${NC}"
    
    # Backup current docker-compose.yml
    cp docker-compose.yml docker-compose.yml.backup.$(date +%s)
    
    # Check if SSL mount already exists
    if ! grep -q "/etc/letsencrypt" docker-compose.yml; then
        # Add SSL certificate mount to nginx service
        sed -i '/volumes:/,/networks:/ {
            /- \.\/ssl\/dhparam\.pem:\/etc\/nginx\/ssl\/dhparam\.pem/a\      - /etc/letsencrypt:/etc/letsencrypt:ro
        }' docker-compose.yml
        
        log "${GREEN}✅ Added SSL certificate mount${NC}"
    else
        log "${GREEN}✅ SSL mount already configured${NC}"
    fi
}

# Step 3: Disable conflicting SSL configs
disable_old_configs() {
    log "${BLUE}[3/6] Disabling old SSL configurations...${NC}"
    
    # Disable any existing SSL configs that might conflict
    for config in nginx/conf.d/*ssl*.conf; do
        if [[ -f "$config" && "$config" != *"production-ssl.conf" && "$config" != *"disabled" ]]; then
            mv "$config" "$config.disabled.$(date +%s)"
            log "${GREEN}✅ Disabled: $(basename "$config")${NC}"
        fi
    done
}

# Step 4: Start services step by step
start_services_carefully() {
    log "${BLUE}[4/6] Starting services step by step...${NC}"
    
    # Start network first
    docker network create odoo_network 2>/dev/null || true
    
    # Start database services first
    log "${YELLOW}Starting PostgreSQL...${NC}"
    docker run -d \
        --name postgres \
        --network odoo_network \
        -e POSTGRES_USER=odoo \
        -e POSTGRES_PASSWORD=odoo \
        -e POSTGRES_DB=postgres \
        -v "$(pwd)/postgres_data:/var/lib/postgresql/data" \
        postgres:15
    
    log "${YELLOW}Starting Redis...${NC}"
    docker run -d \
        --name redis \
        --network odoo_network \
        redis:alpine
    
    sleep 5
    
    # Start application services
    log "${YELLOW}Starting SaaS Manager...${NC}"
    docker run -d \
        --name saas_manager \
        --network odoo_network \
        -v "$(pwd)/saas_manager:/app" \
        -e DJANGO_SETTINGS_MODULE=saas_project.settings \
        odoo-multi-tenant-system_saas_manager:latest
    
    log "${YELLOW}Starting Odoo Master...${NC}"
    docker run -d \
        --name odoo_master \
        --network odoo_network \
        -v "$(pwd)/odoo_master:/etc/odoo" \
        -v "$(pwd)/addons:/mnt/extra-addons" \
        odoo:16
    
    log "${YELLOW}Starting Odoo Workers...${NC}"
    docker run -d \
        --name odoo_worker1 \
        --network odoo_network \
        -v "$(pwd)/odoo_workers:/etc/odoo" \
        -v "$(pwd)/addons:/mnt/extra-addons" \
        odoo:16
    
    docker run -d \
        --name odoo_worker2 \
        --network odoo_network \
        -v "$(pwd)/odoo_workers:/etc/odoo" \
        -v "$(pwd)/addons:/mnt/extra-addons" \
        odoo:16
    
    sleep 10
    
    log "${GREEN}✅ Application services started${NC}"
}

# Step 5: Start nginx with SSL
start_nginx_with_ssl() {
    log "${BLUE}[5/6] Starting nginx with SSL...${NC}"
    
    # Start nginx with proper mounts
    docker run -d \
        --name nginx \
        --network odoo_network \
        -p 80:80 \
        -p 443:443 \
        -v "$(pwd)/nginx/nginx.conf:/etc/nginx/nginx.conf" \
        -v "$(pwd)/nginx/conf.d:/etc/nginx/conf.d" \
        -v "$(pwd)/nginx/errors:/usr/share/nginx/html/errors" \
        -v "$(pwd)/ssl/dhparam.pem:/etc/nginx/ssl/dhparam.pem" \
        -v "/etc/letsencrypt:/etc/letsencrypt:ro" \
        -v "$(pwd)/ssl/certbot/www:/var/www/certbot" \
        nginx:alpine
    
    sleep 5
    
    # Test nginx configuration
    if docker exec nginx nginx -t; then
        log "${GREEN}✅ Nginx configuration is valid${NC}"
    else
        log "${RED}❌ Nginx configuration error${NC}"
        docker logs nginx --tail=20
        return 1
    fi
}

# Step 6: Test SSL setup
test_ssl() {
    log "${BLUE}[6/6] Testing SSL setup...${NC}"
    
    # Wait for services to be ready
    sleep 10
    
    # Test HTTPS connectivity
    if timeout 10 curl -sSf "https://$DOMAIN/ssl-health" >/dev/null 2>&1; then
        log "${GREEN}🎉 SSL is working perfectly!${NC}"
        log "${GREEN}✅ https://$DOMAIN is now secure${NC}"
        
        # Test certificate details
        log "${BLUE}Certificate Information:${NC}"
        echo | openssl s_client -servername $DOMAIN -connect $DOMAIN:443 2>/dev/null | openssl x509 -noout -subject -issuer -dates
        
        return 0
    else
        log "${YELLOW}⚠️  Direct SSL test failed, checking manually...${NC}"
        
        # Show nginx status
        log "${BLUE}Nginx container status:${NC}"
        docker ps | grep nginx
        
        # Show nginx logs
        log "${BLUE}Recent nginx logs:${NC}"
        docker logs nginx --tail=10
        
        return 1
    fi
}

# Setup auto-renewal (simplified)
setup_renewal() {
    log "${BLUE}Setting up certificate renewal...${NC}"
    
    cat > ssl-renew-simple.sh << 'EOF'
#!/bin/bash
# Simple SSL Renewal Script

DOMAIN="khudroo.com"

# Stop nginx
docker stop nginx

# Renew certificate
sudo certbot renew --quiet

# Restart nginx
docker start nginx

echo "$(date): SSL renewal completed for $DOMAIN"
EOF
    
    chmod +x ssl-renew-simple.sh
    
    # Add to cron if not exists
    if ! crontab -l 2>/dev/null | grep -q "ssl-renew-simple"; then
        (crontab -l 2>/dev/null; echo "0 2 * * 0 cd $(pwd) && ./ssl-renew-simple.sh") | crontab -
        log "${GREEN}✅ Simple auto-renewal configured${NC}"
    fi
}

# Main execution
main() {
    cleanup_docker
    update_docker_compose
    disable_old_configs
    start_services_carefully
    start_nginx_with_ssl
    
    if test_ssl; then
        setup_renewal
        
        echo
        log "${GREEN}🎉 SSL Setup Completed Successfully!${NC}"
        log "${GREEN}✅ Certificate: Let's Encrypt (expires 2025-11-09)${NC}"
        log "${GREEN}✅ Main site: https://$DOMAIN${NC}"
        log "${GREEN}✅ Subdomains: https://kdoo_test2.$DOMAIN${NC}"
        log "${BLUE}📋 Renewal script: ./ssl-renew-simple.sh${NC}"
        echo
        log "${YELLOW}🔍 Test your sites:${NC}"
        log "${YELLOW}   • https://$DOMAIN/ssl-health${NC}"
        log "${YELLOW}   • https://$DOMAIN/dashboard${NC}"
        log "${YELLOW}   • https://kdoo_test2.$DOMAIN${NC}"
    else
        log "${RED}❌ SSL test failed, but services are running${NC}"
        log "${BLUE}You can check the configuration manually${NC}"
    fi
}

# Run main function
main "$@"