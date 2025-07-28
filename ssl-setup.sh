#!/bin/bash

# SSL Certificate Setup Script for *.khudroo.com
# This script helps you set up SSL certificates for your domain

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
DOMAIN="khudroo.com"
WILDCARD_DOMAIN="*.khudroo.com"
SSL_DIR="/etc/nginx/ssl"
EMAIL="admin@khudroo.com"  # Replace with your email
DOCKER_SSL_DIR="./ssl"  # Local SSL directory for Docker

# Create SSL directory
create_ssl_directory() {
    echo -e "${BLUE}Creating SSL directory...${NC}"
    sudo mkdir -p $SSL_DIR
    sudo chmod 700 $SSL_DIR
}

# Option 1: Let's Encrypt with Certbot (Recommended for production)
setup_letsencrypt() {
    echo -e "${GREEN}Setting up Let's Encrypt SSL Certificate for *.khudroo.com...${NC}"
    
    # Install certbot if not already installed
    if ! command -v certbot &> /dev/null; then
        echo -e "${YELLOW}Installing Certbot...${NC}"
        sudo apt update
        
        # Install snapd if not available
        if ! command -v snap &> /dev/null; then
            sudo apt install -y snapd
            sudo systemctl enable --now snapd.socket
            sudo ln -sf /var/lib/snapd/snap /snap
        fi
        
        # Install certbot via snap (recommended method)
        sudo snap install --classic certbot
        sudo ln -sf /snap/bin/certbot /usr/bin/certbot
        
        # Install DNS plugin for automated renewal
        sudo snap set certbot trust-plugin-with-root=ok
        sudo snap install certbot-dns-cloudflare
    fi
    
    echo -e "${YELLOW}=========================================${NC}"
    echo -e "${YELLOW}  Let's Encrypt Wildcard Certificate Setup${NC}"
    echo -e "${YELLOW}=========================================${NC}"
    echo
    echo -e "${BLUE}For wildcard certificates (*.khudroo.com), you need DNS validation.${NC}"
    echo -e "${BLUE}This requires creating DNS TXT records manually.${NC}"
    echo
    echo -e "${YELLOW}Steps you'll need to follow:${NC}"
    echo "1. Certbot will provide DNS TXT record values"
    echo "2. Add these TXT records to your DNS provider"
    echo "3. Wait for DNS propagation (usually 1-5 minutes)"
    echo "4. Press Enter to continue the validation"
    echo
    
    read -p "Enter your email address for Let's Encrypt notifications: " user_email
    if [[ -n "$user_email" ]]; then
        EMAIL="$user_email"
    fi
    
    echo
    read -p "Do you want to proceed with Let's Encrypt wildcard certificate? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${BLUE}Starting certificate request...${NC}"
        echo
        
        # Request wildcard certificate with manual DNS validation
        sudo certbot certonly \
            --manual \
            --preferred-challenges=dns \
            --email "$EMAIL" \
            --agree-tos \
            --no-eff-email \
            --manual-public-ip-logging-ok \
            --domains "$DOMAIN,$WILDCARD_DOMAIN" \
            --cert-name "$DOMAIN"
        
        if [[ $? -eq 0 ]]; then
            echo -e "${GREEN}Certificate obtained successfully!${NC}"
            
            # Create Docker SSL directory
            mkdir -p "$DOCKER_SSL_DIR"
            
            # Copy certificates to both system and Docker directories
            sudo cp "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" "$SSL_DIR/$DOMAIN.crt"
            sudo cp "/etc/letsencrypt/live/$DOMAIN/privkey.pem" "$SSL_DIR/$DOMAIN.key"
            sudo cp "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" "$DOCKER_SSL_DIR/$DOMAIN.crt"
            sudo cp "/etc/letsencrypt/live/$DOMAIN/privkey.pem" "$DOCKER_SSL_DIR/$DOMAIN.key"
            
            # Set proper permissions
            sudo chmod 644 "$SSL_DIR/$DOMAIN.crt" "$DOCKER_SSL_DIR/$DOMAIN.crt"
            sudo chmod 600 "$SSL_DIR/$DOMAIN.key" "$DOCKER_SSL_DIR/$DOMAIN.key"
            sudo chown $USER:$USER "$DOCKER_SSL_DIR"/*
            
            echo -e "${GREEN}Certificates installed successfully!${NC}"
            echo -e "${BLUE}System certificates: $SSL_DIR/${NC}"
            echo -e "${BLUE}Docker certificates: $DOCKER_SSL_DIR/${NC}"
            
            # Setup auto-renewal
            setup_certbot_renewal
            
            # Test certificate
            test_wildcard_domains
        else
            echo -e "${RED}Certificate request failed!${NC}"
            return 1
        fi
    fi
}

# Setup automatic certificate renewal
setup_certbot_renewal() {
    echo -e "${BLUE}Setting up automatic certificate renewal...${NC}"
    
    # Create renewal hook script for both system and Docker
    sudo mkdir -p /etc/letsencrypt/renewal-hooks/deploy
    sudo tee /etc/letsencrypt/renewal-hooks/deploy/nginx-reload.sh > /dev/null << EOF
#!/bin/bash
# Copy renewed certificates to nginx directories
DOMAIN="khudroo.com"
DOCKER_SSL_DIR="$(pwd)/ssl"

# Copy to system nginx directory
cp "/etc/letsencrypt/live/\$DOMAIN/fullchain.pem" "/etc/nginx/ssl/\$DOMAIN.crt"
cp "/etc/letsencrypt/live/\$DOMAIN/privkey.pem" "/etc/nginx/ssl/\$DOMAIN.key"
chmod 644 "/etc/nginx/ssl/\$DOMAIN.crt"
chmod 600 "/etc/nginx/ssl/\$DOMAIN.key"

# Copy to Docker SSL directory if it exists
if [[ -d "\$DOCKER_SSL_DIR" ]]; then
    cp "/etc/letsencrypt/live/\$DOMAIN/fullchain.pem" "\$DOCKER_SSL_DIR/\$DOMAIN.crt"
    cp "/etc/letsencrypt/live/\$DOMAIN/privkey.pem" "\$DOCKER_SSL_DIR/\$DOMAIN.key"
    chmod 644 "\$DOCKER_SSL_DIR/\$DOMAIN.crt"
    chmod 600 "\$DOCKER_SSL_DIR/\$DOMAIN.key"
    chown \$USER:\$USER "\$DOCKER_SSL_DIR"/*
fi

# Reload nginx (both system and Docker)
if systemctl is-active --quiet nginx; then
    systemctl reload nginx
fi

# Reload Docker nginx container if running
if command -v docker &> /dev/null; then
    NGINX_CONTAINER=\$(docker ps --filter "name=nginx" --format "{{.Names}}" | head -1)
    if [[ -n "\$NGINX_CONTAINER" ]]; then
        docker exec "\$NGINX_CONTAINER" nginx -s reload
    fi
fi

echo "Certificate renewal completed: \$(date)"
EOF
    
    sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/nginx-reload.sh
    
    # Create systemd timer for renewal (more reliable than cron)
    sudo tee /etc/systemd/system/certbot-renewal.service > /dev/null << 'EOF'
[Unit]
Description=Certbot Renewal
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/certbot renew --quiet
EOF
    
    sudo tee /etc/systemd/system/certbot-renewal.timer > /dev/null << 'EOF'
[Unit]
Description=Run certbot twice daily
Requires=certbot-renewal.service

[Timer]
OnCalendar=*-*-* 00,12:00:00
RandomizedDelaySec=3600
Persistent=true

[Install]
WantedBy=timers.target
EOF
    
    # Enable and start the timer
    sudo systemctl daemon-reload
    sudo systemctl enable certbot-renewal.timer
    sudo systemctl start certbot-renewal.timer
    
    # Test renewal
    echo -e "${YELLOW}Testing certificate renewal...${NC}"
    sudo certbot renew --dry-run
    
    if [[ $? -eq 0 ]]; then
        echo -e "${GREEN}✓ Certificate renewal test passed!${NC}"
        echo -e "${GREEN}✓ Auto-renewal setup complete!${NC}"
        echo -e "${BLUE}Renewal will run twice daily automatically.${NC}"
        echo -e "${BLUE}Check status with: systemctl status certbot-renewal.timer${NC}"
    else
        echo -e "${RED}✗ Certificate renewal test failed!${NC}"
    fi
}

# Option 2: Self-signed certificate (for development/testing)
setup_selfsigned() {
    echo -e "${GREEN}Creating self-signed SSL certificate...${NC}"
    
    # Generate private key
    sudo openssl genrsa -out $SSL_DIR/$DOMAIN.key 2048
    
    # Create certificate signing request config
    sudo tee $SSL_DIR/$DOMAIN.conf > /dev/null << EOF
[req]
default_bits = 2048
prompt = no
default_md = sha256
distinguished_name = dn
req_extensions = v3_req

[dn]
C=BD
ST=Dhaka
L=Dhaka
O=Khudroo
OU=IT Department
CN=$DOMAIN

[v3_req]
basicConstraints = CA:FALSE
keyUsage = nonRepudiation, digitalSignature, keyEncipherment
subjectAltName = @alt_names

[alt_names]
DNS.1 = $DOMAIN
DNS.2 = $WILDCARD_DOMAIN
DNS.3 = localhost
DNS.4 = *.localhost
EOF
    
    # Generate certificate
    sudo openssl req -new -x509 -key $SSL_DIR/$DOMAIN.key -out $SSL_DIR/$DOMAIN.crt -days 365 -config $SSL_DIR/$DOMAIN.conf -extensions v3_req
    
    # Set proper permissions
    sudo chmod 644 $SSL_DIR/$DOMAIN.crt
    sudo chmod 600 $SSL_DIR/$DOMAIN.key
    
    echo -e "${GREEN}Self-signed certificate created successfully!${NC}"
    echo -e "${YELLOW}Note: Browsers will show security warnings for self-signed certificates.${NC}"
}

# Generate localhost certificate for development
setup_localhost_cert() {
    echo -e "${BLUE}Creating localhost certificate for development...${NC}"
    
    # Generate private key for localhost
    sudo openssl genrsa -out $SSL_DIR/localhost.key 2048
    
    # Create localhost certificate config
    sudo tee $SSL_DIR/localhost.conf > /dev/null << EOF
[req]
default_bits = 2048
prompt = no
default_md = sha256
distinguished_name = dn
req_extensions = v3_req

[dn]
C=BD
ST=Dhaka
L=Dhaka
O=Khudroo Dev
OU=Development
CN=localhost

[v3_req]
basicConstraints = CA:FALSE
keyUsage = nonRepudiation, digitalSignature, keyEncipherment
subjectAltName = @alt_names

[alt_names]
DNS.1 = localhost
DNS.2 = *.localhost
IP.1 = 127.0.0.1
IP.2 = ::1
EOF
    
    # Generate localhost certificate
    sudo openssl req -new -x509 -key $SSL_DIR/localhost.key -out $SSL_DIR/localhost.crt -days 365 -config $SSL_DIR/localhost.conf -extensions v3_req
    
    # Set proper permissions
    sudo chmod 644 $SSL_DIR/localhost.crt
    sudo chmod 600 $SSL_DIR/localhost.key
    
    echo -e "${GREEN}Localhost certificate created successfully!${NC}"
}

# Option 3: Use existing certificate
use_existing_cert() {
    echo -e "${GREEN}Using existing SSL certificate...${NC}"
    
    read -p "Enter path to your certificate file (.crt or .pem): " cert_path
    read -p "Enter path to your private key file (.key): " key_path
    
    if [[ -f "$cert_path" && -f "$key_path" ]]; then
        sudo cp "$cert_path" $SSL_DIR/$DOMAIN.crt
        sudo cp "$key_path" $SSL_DIR/$DOMAIN.key
        
        # Set proper permissions
        sudo chmod 644 $SSL_DIR/$DOMAIN.crt
        sudo chmod 600 $SSL_DIR/$DOMAIN.key
        
        echo -e "${GREEN}Existing certificate installed successfully!${NC}"
    else
        echo -e "${RED}Error: Certificate or key file not found!${NC}"
        exit 1
    fi
}

# Generate DH parameters for enhanced security
generate_dhparam() {
    echo -e "${BLUE}Generating DH parameters (this may take a while)...${NC}"
    
    if [[ ! -f $SSL_DIR/dhparam.pem ]]; then
        sudo openssl dhparam -out $SSL_DIR/dhparam.pem 2048
        sudo chmod 644 $SSL_DIR/dhparam.pem
        echo -e "${GREEN}DH parameters generated successfully!${NC}"
        
        # Add DH param to nginx config
        echo -e "${YELLOW}Add this line to your nginx.conf in the http block:${NC}"
        echo -e "${BLUE}ssl_dhparam $SSL_DIR/dhparam.pem;${NC}"
    else
        echo -e "${YELLOW}DH parameters already exist.${NC}"
    fi
}

# Test SSL certificate
test_certificate() {
    echo -e "${BLUE}Testing SSL certificate...${NC}"
    
    if [[ -f $SSL_DIR/$DOMAIN.crt && -f $SSL_DIR/$DOMAIN.key ]]; then
        # Check certificate validity
        echo -e "${YELLOW}Certificate information:${NC}"
        sudo openssl x509 -in $SSL_DIR/$DOMAIN.crt -text -noout | grep -E "(Subject:|DNS:|Not Before|Not After)"
        
        # Check if private key matches certificate
        cert_modulus=$(sudo openssl x509 -noout -modulus -in $SSL_DIR/$DOMAIN.crt | openssl md5)
        key_modulus=$(sudo openssl rsa -noout -modulus -in $SSL_DIR/$DOMAIN.key | openssl md5)
        
        if [[ "$cert_modulus" == "$key_modulus" ]]; then
            echo -e "${GREEN}✓ Certificate and private key match!${NC}"
        else
            echo -e "${RED}✗ Certificate and private key do not match!${NC}"
            exit 1
        fi
        
        echo -e "${GREEN}SSL certificate test passed!${NC}"
    else
        echo -e "${RED}SSL certificate or key file not found!${NC}"
        exit 1
    fi
}

# Test nginx configuration
test_nginx_config() {
    echo -e "${BLUE}Testing Nginx configuration...${NC}"
    
    if sudo nginx -t; then
        echo -e "${GREEN}✓ Nginx configuration is valid!${NC}"
        
        read -p "Do you want to reload Nginx now? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            sudo systemctl reload nginx
            echo -e "${GREEN}Nginx reloaded successfully!${NC}"
        fi
    else
        echo -e "${RED}✗ Nginx configuration has errors!${NC}"
        echo -e "${YELLOW}Please fix the configuration before proceeding.${NC}"
        exit 1
    fi
}

# Check certificate expiration and setup monitoring
setup_cert_monitoring() {
    echo -e "${BLUE}Setting up certificate expiration monitoring...${NC}"
    
    # Create certificate check script
    sudo tee /usr/local/bin/check-ssl-cert.sh > /dev/null << 'EOF'
#!/bin/bash

DOMAIN="khudroo.com"
CERT_FILE="/etc/nginx/ssl/$DOMAIN.crt"
DAYS_BEFORE_EXPIRY=30

if [[ -f "$CERT_FILE" ]]; then
    EXPIRY_DATE=$(openssl x509 -enddate -noout -in "$CERT_FILE" | cut -d= -f2)
    EXPIRY_TIMESTAMP=$(date -d "$EXPIRY_DATE" +%s)
    CURRENT_TIMESTAMP=$(date +%s)
    DAYS_UNTIL_EXPIRY=$(( (EXPIRY_TIMESTAMP - CURRENT_TIMESTAMP) / 86400 ))
    
    if [[ $DAYS_UNTIL_EXPIRY -le $DAYS_BEFORE_EXPIRY ]]; then
        echo "WARNING: SSL certificate for $DOMAIN expires in $DAYS_UNTIL_EXPIRY days!"
        # You can add email notification here
        # echo "SSL certificate expires in $DAYS_UNTIL_EXPIRY days" | mail -s "SSL Certificate Expiry Warning" admin@example.com
    else
        echo "SSL certificate for $DOMAIN is valid for $DAYS_UNTIL_EXPIRY more days."
    fi
else
    echo "ERROR: SSL certificate file not found!"
fi
EOF
    
    sudo chmod +x /usr/local/bin/check-ssl-cert.sh
    
    # Add to crontab (check daily at 9 AM)
    (crontab -l 2>/dev/null; echo "0 9 * * * /usr/local/bin/check-ssl-cert.sh") | crontab -
    
    echo -e "${GREEN}Certificate monitoring setup complete!${NC}"
    echo -e "${YELLOW}The system will check certificate expiry daily at 9 AM.${NC}"
}

# Display certificate information
show_cert_info() {
    echo -e "${BLUE}SSL Certificate Information:${NC}"
    echo "================================"
    
    if [[ -f $SSL_DIR/$DOMAIN.crt ]]; then
        echo -e "${YELLOW}Certificate file:${NC} $SSL_DIR/$DOMAIN.crt"
        echo -e "${YELLOW}Private key file:${NC} $SSL_DIR/$DOMAIN.key"
        echo
        
        # Show certificate details
        sudo openssl x509 -in $SSL_DIR/$DOMAIN.crt -text -noout | grep -E "(Subject:|Issuer:|DNS:|Not Before|Not After|Serial Number)"
        
        # Show certificate fingerprint
        echo -e "\n${YELLOW}Certificate SHA256 Fingerprint:${NC}"
        sudo openssl x509 -noout -fingerprint -sha256 -in $SSL_DIR/$DOMAIN.crt
        
    else
        echo -e "${RED}No certificate found at $SSL_DIR/$DOMAIN.crt${NC}"
    fi
}

# Main menu
show_menu() {
    echo
    echo -e "${GREEN}===================================${NC}"
    echo -e "${GREEN}   SSL Certificate Setup Script   ${NC}"
    echo -e "${GREEN}     for *.khudroo.com domain     ${NC}"
    echo -e "${GREEN}===================================${NC}"
    echo
    echo "1. Setup Let's Encrypt Certificate (Recommended for Production)"
    echo "2. Create Self-signed Certificate (Development/Testing)"
    echo "3. Use Existing Certificate"
    echo "4. Generate Localhost Certificate (Development)"
    echo "5. Generate DH Parameters"
    echo "6. Test SSL Certificate"
    echo "7. Test Nginx Configuration"
    echo "8. Setup Certificate Monitoring"
    echo "9. Show Certificate Information"
    echo "0. Exit"
    echo
}

# Main script execution
main() {
    # Check if running as root or with sudo
    if [[ $EUID -eq 0 ]]; then
        echo -e "${RED}Please don't run this script as root. Use sudo when prompted.${NC}"
        exit 1
    fi
    
    # Check if nginx is installed
    if ! command -v nginx &> /dev/null; then
        echo -e "${RED}Nginx is not installed. Please install nginx first.${NC}"
        exit 1
    fi
    
    # Create SSL directory
    create_ssl_directory
    
    while true; do
        show_menu
        read -p "Please select an option (0-9): " choice
        
        case $choice in
            1)
                setup_letsencrypt
                ;;
            2)
                setup_selfsigned
                ;;
            3)
                use_existing_cert
                ;;
            4)
                setup_localhost_cert
                ;;
            5)
                generate_dhparam
                ;;
            6)
                test_certificate
                ;;
            7)
                test_nginx_config
                ;;
            8)
                setup_cert_monitoring
                ;;
            9)
                show_cert_info
                ;;
            0)
                echo -e "${GREEN}Thank you for using the SSL setup script!${NC}"
                exit 0
                ;;
            *)
                echo -e "${RED}Invalid option. Please try again.${NC}"
                ;;
        esac
        
        echo
        read -p "Press Enter to continue..."
    done
}

# Run the main function
main "$@"
