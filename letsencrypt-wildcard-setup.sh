#!/bin/bash

# Let's Encrypt Wildcard SSL Certificate Setup for Odoo Multi-Tenant System
# Specifically designed for *.khudroo.com with automatic subdomain generation

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
DOMAIN="khudroo.com"
WILDCARD_DOMAIN="*.khudroo.com"
EMAIL="admin@khudroo.com"
DOCKER_SSL_DIR="./ssl"
SYSTEM_SSL_DIR="/etc/nginx/ssl"

# Test subdomains for validation
TEST_SUBDOMAINS=("test" "demo" "tenant1" "tenant2" "admin" "api")

# Banner
show_banner() {
    echo -e "${PURPLE}============================================${NC}"
    echo -e "${PURPLE}   Let's Encrypt Wildcard SSL Setup       ${NC}"
    echo -e "${PURPLE}   for Odoo Multi-Tenant System           ${NC}"
    echo -e "${PURPLE}   Domain: *.khudroo.com                   ${NC}"
    echo -e "${PURPLE}============================================${NC}"
    echo
}

# Check prerequisites
check_prerequisites() {
    echo -e "${BLUE}Checking prerequisites...${NC}"
    
    # Check if running as non-root
    if [[ $EUID -eq 0 ]]; then
        echo -e "${RED}Please don't run this script as root. Use sudo when prompted.${NC}"
        exit 1
    fi
    
    # Check internet connectivity
    if ! ping -c 1 google.com &> /dev/null; then
        echo -e "${RED}No internet connection detected. Please check your network.${NC}"
        exit 1
    fi
    
    # Check domain DNS
    echo -e "${YELLOW}Checking DNS configuration for $DOMAIN...${NC}"
    if ! nslookup "$DOMAIN" &> /dev/null; then
        echo -e "${RED}Warning: DNS lookup for $DOMAIN failed.${NC}"
        echo -e "${YELLOW}Make sure your domain is properly configured before proceeding.${NC}"
        read -p "Continue anyway? (y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    else
        echo -e "${GREEN}✓ DNS lookup for $DOMAIN successful${NC}"
    fi
    
    echo -e "${GREEN}✓ Prerequisites check completed${NC}"
    echo
}

# Install Certbot
install_certbot() {
    echo -e "${BLUE}Installing/Updating Certbot...${NC}"
    
    if ! command -v certbot &> /dev/null; then
        # Install snapd if not available
        if ! command -v snap &> /dev/null; then
            echo -e "${YELLOW}Installing snapd...${NC}"
            sudo apt update
            sudo apt install -y snapd
            sudo systemctl enable --now snapd.socket
            sudo ln -sf /var/lib/snapd/snap /snap
            
            # Wait for snapd to be ready
            echo -e "${YELLOW}Waiting for snapd to initialize...${NC}"
            sleep 10
        fi
        
        # Remove any old certbot installations
        sudo apt remove -y certbot python3-certbot-nginx &> /dev/null || true
        
        # Install certbot via snap (recommended method)
        echo -e "${YELLOW}Installing Certbot via snap...${NC}"
        sudo snap install --classic certbot
        sudo ln -sf /snap/bin/certbot /usr/bin/certbot
        
        # Verify installation
        if certbot --version &> /dev/null; then
            echo -e "${GREEN}✓ Certbot installed successfully${NC}"
        else
            echo -e "${RED}✗ Certbot installation failed${NC}"
            exit 1
        fi
    else
        echo -e "${GREEN}✓ Certbot already installed${NC}"
        certbot --version
    fi
    
    echo
}

# Create directories
create_directories() {
    echo -e "${BLUE}Creating SSL directories...${NC}"
    
    # Create system SSL directory
    sudo mkdir -p "$SYSTEM_SSL_DIR"
    sudo chmod 755 "$SYSTEM_SSL_DIR"
    
    # Create Docker SSL directory
    mkdir -p "$DOCKER_SSL_DIR"
    chmod 755 "$DOCKER_SSL_DIR"
    
    echo -e "${GREEN}✓ SSL directories created${NC}"
    echo -e "${BLUE}  System: $SYSTEM_SSL_DIR${NC}"
    echo -e "${BLUE}  Docker: $DOCKER_SSL_DIR${NC}"
    echo
}

# DNS validation guide
show_dns_guide() {
    echo -e "${CYAN}=========================================${NC}"
    echo -e "${CYAN}   DNS Validation Guide                 ${NC}"
    echo -e "${CYAN}=========================================${NC}"
    echo
    echo -e "${YELLOW}For wildcard certificates, you need to add DNS TXT records.${NC}"
    echo -e "${YELLOW}Certbot will provide you with specific values to add.${NC}"
    echo
    echo -e "${BLUE}Steps to follow:${NC}"
    echo "1. Certbot will show you TXT record details"
    echo "2. Log into your DNS provider (Cloudflare, GoDaddy, etc.)"
    echo "3. Add the TXT record with name: _acme-challenge.khudroo.com"
    echo "4. Wait 1-5 minutes for DNS propagation"
    echo "5. Press Enter in certbot to continue validation"
    echo
    echo -e "${YELLOW}Common DNS providers:${NC}"
    echo "• Cloudflare: DNS tab → Add Record → TXT"
    echo "• GoDaddy: DNS Management → Add Record → TXT"
    echo "• Namecheap: Domain List → Manage → Advanced DNS"
    echo
    echo -e "${BLUE}You can test DNS propagation with:${NC}"
    echo "nslookup -type=TXT _acme-challenge.khudroo.com"
    echo
}

# Request Let's Encrypt certificate
request_certificate() {
    echo -e "${GREEN}Starting Let's Encrypt certificate request...${NC}"
    echo
    
    # Get email for notifications
    echo -e "${BLUE}Certificate will be issued for:${NC}"
    echo -e "  • $DOMAIN"
    echo -e "  • $WILDCARD_DOMAIN"
    echo
    
    read -p "Enter your email for Let's Encrypt notifications [$EMAIL]: " user_email
    if [[ -n "$user_email" ]]; then
        EMAIL="$user_email"
    fi
    
    echo
    echo -e "${YELLOW}Important: Keep this terminal open during the process!${NC}"
    echo -e "${YELLOW}You'll need to add DNS TXT records when prompted.${NC}"
    echo
    read -p "Ready to start certificate request? (y/n): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${BLUE}Requesting wildcard certificate...${NC}"
        echo
        
        # Request certificate with manual DNS validation
        sudo certbot certonly \
            --manual \
            --preferred-challenges=dns \
            --email "$EMAIL" \
            --agree-tos \
            --no-eff-email \
            --domains "$DOMAIN,$WILDCARD_DOMAIN" \
            --cert-name "$DOMAIN" \
            --verbose
        
        if [[ $? -eq 0 ]]; then
            echo
            echo -e "${GREEN}🎉 Certificate obtained successfully!${NC}"
            copy_certificates
            setup_auto_renewal
            test_wildcard_certificate
        else
            echo
            echo -e "${RED}❌ Certificate request failed!${NC}"
            echo -e "${YELLOW}Common issues:${NC}"
            echo "• DNS TXT record not added correctly"
            echo "• DNS propagation not complete (wait longer)"
            echo "• Domain ownership verification failed"
            echo
            exit 1
        fi
    else
        echo -e "${YELLOW}Certificate request cancelled.${NC}"
        exit 0
    fi
}

# Copy certificates to required locations
copy_certificates() {
    echo -e "${BLUE}Copying certificates to required locations...${NC}"
    
    if [[ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]]; then
        # Copy to system nginx directory
        sudo cp "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" "$SYSTEM_SSL_DIR/$DOMAIN.crt"
        sudo cp "/etc/letsencrypt/live/$DOMAIN/privkey.pem" "$SYSTEM_SSL_DIR/$DOMAIN.key"
        sudo chmod 644 "$SYSTEM_SSL_DIR/$DOMAIN.crt"
        sudo chmod 600 "$SYSTEM_SSL_DIR/$DOMAIN.key"
        
        # Copy to Docker SSL directory
        sudo cp "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" "$DOCKER_SSL_DIR/$DOMAIN.crt"
        sudo cp "/etc/letsencrypt/live/$DOMAIN/privkey.pem" "$DOCKER_SSL_DIR/$DOMAIN.key"
        sudo chmod 644 "$DOCKER_SSL_DIR/$DOMAIN.crt"
        sudo chmod 600 "$DOCKER_SSL_DIR/$DOMAIN.key"
        sudo chown $USER:$USER "$DOCKER_SSL_DIR"/*
        
        echo -e "${GREEN}✓ Certificates copied successfully${NC}"
        echo -e "${BLUE}  System: $SYSTEM_SSL_DIR/$DOMAIN.{crt,key}${NC}"
        echo -e "${BLUE}  Docker: $DOCKER_SSL_DIR/$DOMAIN.{crt,key}${NC}"
    else
        echo -e "${RED}✗ Certificate files not found!${NC}"
        exit 1
    fi
}

# Setup automatic renewal
setup_auto_renewal() {
    echo -e "${BLUE}Setting up automatic certificate renewal...${NC}"
    
    # Create renewal hook script
    sudo mkdir -p /etc/letsencrypt/renewal-hooks/deploy
    sudo tee /etc/letsencrypt/renewal-hooks/deploy/khudroo-renewal.sh > /dev/null << EOF
#!/bin/bash
# Automatic certificate renewal hook for khudroo.com
# This script runs after successful certificate renewal

DOMAIN="khudroo.com"
SYSTEM_SSL_DIR="$SYSTEM_SSL_DIR"
DOCKER_SSL_DIR="$(pwd)/ssl"

echo "=== Certificate Renewal Hook Executed at \$(date) ==="

# Copy to system nginx directory
if [[ -f "/etc/letsencrypt/live/\$DOMAIN/fullchain.pem" ]]; then
    cp "/etc/letsencrypt/live/\$DOMAIN/fullchain.pem" "\$SYSTEM_SSL_DIR/\$DOMAIN.crt"
    cp "/etc/letsencrypt/live/\$DOMAIN/privkey.pem" "\$SYSTEM_SSL_DIR/\$DOMAIN.key"
    chmod 644 "\$SYSTEM_SSL_DIR/\$DOMAIN.crt"
    chmod 600 "\$SYSTEM_SSL_DIR/\$DOMAIN.key"
    echo "✓ Certificates copied to system nginx directory"
fi

# Copy to Docker SSL directory if it exists
if [[ -d "\$DOCKER_SSL_DIR" ]]; then
    cp "/etc/letsencrypt/live/\$DOMAIN/fullchain.pem" "\$DOCKER_SSL_DIR/\$DOMAIN.crt"
    cp "/etc/letsencrypt/live/\$DOMAIN/privkey.pem" "\$DOCKER_SSL_DIR/\$DOMAIN.key"
    chmod 644 "\$DOCKER_SSL_DIR/\$DOMAIN.crt"
    chmod 600 "\$DOCKER_SSL_DIR/\$DOMAIN.key"
    chown \$USER:\$USER "\$DOCKER_SSL_DIR"/* 2>/dev/null || true
    echo "✓ Certificates copied to Docker directory"
fi

# Reload nginx if running
if systemctl is-active --quiet nginx; then
    systemctl reload nginx
    echo "✓ System nginx reloaded"
fi

# Reload Docker nginx container if running
if command -v docker &> /dev/null; then
    NGINX_CONTAINER=\$(docker ps --filter "name=nginx" --format "{{.Names}}" | head -1)
    if [[ -n "\$NGINX_CONTAINER" ]]; then
        docker exec "\$NGINX_CONTAINER" nginx -s reload 2>/dev/null || true
        echo "✓ Docker nginx container reloaded"
    fi
fi

echo "=== Certificate renewal hook completed successfully ==="
EOF
    
    sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/khudroo-renewal.sh
    
    # Create systemd service for renewal
    sudo tee /etc/systemd/system/certbot-khudroo.service > /dev/null << 'EOF'
[Unit]
Description=Certbot Renewal for khudroo.com
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/certbot renew --cert-name khudroo.com --quiet
User=root
EOF
    
    # Create systemd timer for automatic renewal
    sudo tee /etc/systemd/system/certbot-khudroo.timer > /dev/null << 'EOF'
[Unit]
Description=Run certbot renewal for khudroo.com twice daily
Requires=certbot-khudroo.service

[Timer]
OnCalendar=*-*-* 00,12:00:00
RandomizedDelaySec=3600
Persistent=true

[Install]
WantedBy=timers.target
EOF
    
    # Enable and start the timer
    sudo systemctl daemon-reload
    sudo systemctl enable certbot-khudroo.timer
    sudo systemctl start certbot-khudroo.timer
    
    # Test renewal
    echo -e "${YELLOW}Testing certificate renewal (dry run)...${NC}"
    if sudo certbot renew --cert-name "$DOMAIN" --dry-run; then
        echo -e "${GREEN}✓ Certificate renewal test passed!${NC}"
        echo -e "${GREEN}✓ Automatic renewal setup completed${NC}"
        echo -e "${BLUE}  Renewal runs twice daily automatically${NC}"
        echo -e "${BLUE}  Check status: systemctl status certbot-khudroo.timer${NC}"
    else
        echo -e "${RED}✗ Certificate renewal test failed!${NC}"
        echo -e "${YELLOW}Manual renewal may be required for future updates.${NC}"
    fi
    
    echo
}

# Test wildcard certificate
test_wildcard_certificate() {
    echo -e "${BLUE}Testing wildcard certificate functionality...${NC}"
    echo
    
    # Check certificate details
    echo -e "${YELLOW}Certificate Information:${NC}"
    if [[ -f "$DOCKER_SSL_DIR/$DOMAIN.crt" ]]; then
        openssl x509 -in "$DOCKER_SSL_DIR/$DOMAIN.crt" -text -noout | grep -E "(Subject:|DNS:|Not Before|Not After|Issuer:)"
        echo
        
        # Test certificate for main domain and wildcard
        echo -e "${YELLOW}Testing certificate validity:${NC}"
        
        # Test main domain
        if openssl verify -CAfile <(openssl x509 -in "$DOCKER_SSL_DIR/$DOMAIN.crt") "$DOCKER_SSL_DIR/$DOMAIN.crt" &>/dev/null; then
            echo -e "${GREEN}✓ Certificate is valid${NC}"
        else
            echo -e "${YELLOW}⚠ Certificate verification warning (normal for Let's Encrypt)${NC}"
        fi
        
        # Check if certificate includes wildcard
        if openssl x509 -in "$DOCKER_SSL_DIR/$DOMAIN.crt" -text -noout | grep -q "DNS:\*\.khudroo\.com"; then
            echo -e "${GREEN}✓ Wildcard domain (*.khudroo.com) included${NC}"
        else
            echo -e "${RED}✗ Wildcard domain not found in certificate${NC}"
        fi
        
        # Check if certificate includes main domain
        if openssl x509 -in "$DOCKER_SSL_DIR/$DOMAIN.crt" -text -noout | grep -q "DNS:khudroo\.com"; then
            echo -e "${GREEN}✓ Main domain (khudroo.com) included${NC}"
        else
            echo -e "${RED}✗ Main domain not found in certificate${NC}"
        fi
        
    else
        echo -e "${RED}✗ Certificate file not found!${NC}"
        return 1
    fi
    
    echo
    echo -e "${GREEN}🎉 Wildcard certificate setup completed successfully!${NC}"
    echo
}

# Show next steps
show_next_steps() {
    echo -e "${PURPLE}============================================${NC}"
    echo -e "${PURPLE}   Setup Complete! Next Steps:           ${NC}"
    echo -e "${PURPLE}============================================${NC}"
    echo
    echo -e "${GREEN}✅ Let's Encrypt wildcard certificate installed${NC}"
    echo -e "${GREEN}✅ Automatic renewal configured${NC}"
    echo -e "${GREEN}✅ Certificates copied to Docker directory${NC}"
    echo
    echo -e "${YELLOW}🚀 Start your Odoo Multi-Tenant System:${NC}"
    echo "   docker-compose up -d"
    echo
    echo -e "${YELLOW}🌐 Your SSL-enabled URLs:${NC}"
    echo "   • Main site: https://khudroo.com"
    echo "   • Any subdomain: https://[tenant].khudroo.com"
    echo "   • Examples:"
    echo "     - https://tenant1.khudroo.com"
    echo "     - https://demo.khudroo.com"
    echo "     - https://client123.khudroo.com"
    echo
    echo -e "${YELLOW}🔍 Monitor certificate status:${NC}"
    echo "   • Check renewal timer: systemctl status certbot-khudroo.timer"
    echo "   • Manual renewal test: sudo certbot renew --cert-name khudroo.com --dry-run"
    echo "   • View certificates: sudo certbot certificates"
    echo
    echo -e "${YELLOW}📋 Certificate Files:${NC}"
    echo "   • Docker: $DOCKER_SSL_DIR/$DOMAIN.{crt,key}"
    echo "   • System: $SYSTEM_SSL_DIR/$DOMAIN.{crt,key}"
    echo "   • Let's Encrypt: /etc/letsencrypt/live/$DOMAIN/"
    echo
    echo -e "${BLUE}💡 Tips:${NC}"
    echo "   • Certificate automatically renews every 60 days"
    echo "   • New tenant subdomains work automatically with wildcard"
    echo "   • Monitor logs: journalctl -u certbot-khudroo.timer"
    echo
}

# Main execution
main() {
    show_banner
    check_prerequisites
    install_certbot
    create_directories
    show_dns_guide
    request_certificate
    show_next_steps
}

# Run the script
main "$@"
