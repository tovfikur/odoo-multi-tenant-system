#!/bin/bash

# Wildcard SSL Certificate Test Script
# Tests *.khudroo.com certificate functionality for multi-tenant Odoo system

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

# Configuration
DOMAIN="khudroo.com"
DOCKER_SSL_DIR="./ssl"
TEST_SUBDOMAINS=("www" "test" "demo" "tenant1" "tenant2" "admin" "api" "client123" "company-abc")
TEST_PORT="443"

# Test results
PASSED_TESTS=0
FAILED_TESTS=0
TOTAL_TESTS=0

# Banner
echo -e "${PURPLE}============================================${NC}"
echo -e "${PURPLE}   Wildcard SSL Certificate Test Suite    ${NC}"
echo -e "${PURPLE}   for *.khudroo.com                       ${NC}"
echo -e "${PURPLE}============================================${NC}"
echo

# Helper functions
log_success() {
    echo -e "${GREEN}✓ $1${NC}"
    ((PASSED_TESTS++))
}

log_error() {
    echo -e "${RED}✗ $1${NC}"
    ((FAILED_TESTS++))
}

log_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

log_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Test 1: Check certificate files exist
test_certificate_files() {
    echo -e "${BLUE}Test 1: Checking certificate files...${NC}"
    ((TOTAL_TESTS++))
    
    if [[ -f "$DOCKER_SSL_DIR/$DOMAIN.crt" && -f "$DOCKER_SSL_DIR/$DOMAIN.key" ]]; then
        log_success "Certificate files found in $DOCKER_SSL_DIR"
        
        # Check file permissions
        cert_perms=$(stat -c "%a" "$DOCKER_SSL_DIR/$DOMAIN.crt" 2>/dev/null || echo "unknown")
        key_perms=$(stat -c "%a" "$DOCKER_SSL_DIR/$DOMAIN.key" 2>/dev/null || echo "unknown")
        
        if [[ "$cert_perms" == "644" ]]; then
            log_success "Certificate permissions correct (644)"
        else
            log_warning "Certificate permissions: $cert_perms (expected 644)"
        fi
        
        if [[ "$key_perms" == "600" ]]; then
            log_success "Private key permissions correct (600)"
        else
            log_error "Private key permissions: $key_perms (expected 600)"
        fi
    else
        log_error "Certificate files not found in $DOCKER_SSL_DIR"
    fi
    echo
}

# Test 2: Validate certificate content
test_certificate_content() {
    echo -e "${BLUE}Test 2: Validating certificate content...${NC}"
    ((TOTAL_TESTS++))
    
    if [[ -f "$DOCKER_SSL_DIR/$DOMAIN.crt" ]]; then
        # Check if certificate is valid
        if openssl x509 -in "$DOCKER_SSL_DIR/$DOMAIN.crt" -noout -text >/dev/null 2>&1; then
            log_success "Certificate format is valid"
            
            # Check expiration
            exp_date=$(openssl x509 -in "$DOCKER_SSL_DIR/$DOMAIN.crt" -noout -enddate | cut -d= -f2)
            exp_timestamp=$(date -d "$exp_date" +%s)
            current_timestamp=$(date +%s)
            days_until_expiry=$(( (exp_timestamp - current_timestamp) / 86400 ))
            
            if [[ $days_until_expiry -gt 30 ]]; then
                log_success "Certificate valid for $days_until_expiry more days"
            elif [[ $days_until_expiry -gt 0 ]]; then
                log_warning "Certificate expires in $days_until_expiry days"
            else
                log_error "Certificate has expired!"
            fi
            
            # Check issuer
            issuer=$(openssl x509 -in "$DOCKER_SSL_DIR/$DOMAIN.crt" -noout -issuer | grep -o "Let's Encrypt" || echo "Other")
            if [[ "$issuer" == "Let's Encrypt" ]]; then
                log_success "Certificate issued by Let's Encrypt"
            else
                log_info "Certificate issuer: $(openssl x509 -in "$DOCKER_SSL_DIR/$DOMAIN.crt" -noout -issuer)"
            fi
            
        else
            log_error "Invalid certificate format"
        fi
    else
        log_error "Certificate file not found"
    fi
    echo
}

# Test 3: Check wildcard domains in certificate
test_wildcard_domains() {
    echo -e "${BLUE}Test 3: Checking wildcard domain coverage...${NC}"
    ((TOTAL_TESTS++))
    
    if [[ -f "$DOCKER_SSL_DIR/$DOMAIN.crt" ]]; then
        cert_content=$(openssl x509 -in "$DOCKER_SSL_DIR/$DOMAIN.crt" -noout -text)
        
        # Check for main domain
        if echo "$cert_content" | grep -q "DNS:$DOMAIN"; then
            log_success "Main domain ($DOMAIN) included in certificate"
        else
            log_error "Main domain ($DOMAIN) not found in certificate"
        fi
        
        # Check for wildcard domain
        if echo "$cert_content" | grep -q "DNS:\*\.$DOMAIN"; then
            log_success "Wildcard domain (*.$DOMAIN) included in certificate"
        else
            log_error "Wildcard domain (*.$DOMAIN) not found in certificate"
        fi
        
        # Show all domains in certificate
        echo -e "${BLUE}All domains in certificate:${NC}"
        echo "$cert_content" | grep -o "DNS:[^,]*" | sed 's/DNS:/  • /'
        
    else
        log_error "Certificate file not found"
    fi
    echo
}

# Test 4: Check Docker container status
test_docker_containers() {
    echo -e "${BLUE}Test 4: Checking Docker containers...${NC}"
    ((TOTAL_TESTS++))
    
    if command -v docker >/dev/null 2>&1; then
        # Check if nginx container is running
        nginx_container=$(docker ps --filter "name=nginx" --format "{{.Names}}" | head -1)
        if [[ -n "$nginx_container" ]]; then
            log_success "Nginx container '$nginx_container' is running"
            
            # Check if SSL files are mounted
            if docker exec "$nginx_container" ls /etc/nginx/ssl/ >/dev/null 2>&1; then
                log_success "SSL directory mounted in nginx container"
                
                # Check SSL files in container
                if docker exec "$nginx_container" ls "/etc/nginx/ssl/$DOMAIN.crt" >/dev/null 2>&1; then
                    log_success "Certificate file accessible in container"
                else
                    log_error "Certificate file not found in container"
                fi
                
                if docker exec "$nginx_container" ls "/etc/nginx/ssl/$DOMAIN.key" >/dev/null 2>&1; then
                    log_success "Private key file accessible in container"
                else
                    log_error "Private key file not found in container"
                fi
            else
                log_error "SSL directory not mounted in nginx container"
            fi
        else
            log_warning "Nginx container not running"
        fi
    else
        log_warning "Docker not available for testing"
    fi
    echo
}

# Test 5: Test SSL connectivity
test_ssl_connectivity() {
    echo -e "${BLUE}Test 5: Testing SSL connectivity...${NC}"
    
    for subdomain in "${TEST_SUBDOMAINS[@]}"; do
        ((TOTAL_TESTS++))
        test_domain="$subdomain.$DOMAIN"
        
        echo -e "${YELLOW}Testing: $test_domain${NC}"
        
        # Test SSL handshake
        if timeout 10 openssl s_client -connect "$test_domain:$TEST_PORT" -servername "$test_domain" </dev/null >/dev/null 2>&1; then
            log_success "SSL handshake successful for $test_domain"
        else
            # Check if it's a DNS issue or SSL issue
            if nslookup "$test_domain" >/dev/null 2>&1; then
                log_error "SSL handshake failed for $test_domain (SSL issue)"
            else
                log_warning "DNS resolution failed for $test_domain (add to /etc/hosts for testing)"
            fi
        fi
    done
    echo
}

# Test 6: Test certificate chain
test_certificate_chain() {
    echo -e "${BLUE}Test 6: Testing certificate chain...${NC}"
    ((TOTAL_TESTS++))
    
    if [[ -f "$DOCKER_SSL_DIR/$DOMAIN.crt" ]]; then
        # Check if certificate chain is complete
        chain_length=$(openssl x509 -in "$DOCKER_SSL_DIR/$DOMAIN.crt" -noout -text | grep -c "Certificate:" || echo "1")
        
        if [[ $chain_length -gt 1 ]]; then
            log_success "Certificate chain includes intermediate certificates"
        else
            # Check if it's a fullchain certificate
            if grep -q "END CERTIFICATE" "$DOCKER_SSL_DIR/$DOMAIN.crt" && [[ $(grep -c "END CERTIFICATE" "$DOCKER_SSL_DIR/$DOMAIN.crt") -gt 1 ]]; then
                log_success "Fullchain certificate detected"
            else
                log_warning "Certificate might be missing intermediate certificates"
            fi
        fi
        
        # Verify certificate against key
        cert_modulus=$(openssl x509 -noout -modulus -in "$DOCKER_SSL_DIR/$DOMAIN.crt" | openssl md5)
        key_modulus=$(openssl rsa -noout -modulus -in "$DOCKER_SSL_DIR/$DOMAIN.key" 2>/dev/null | openssl md5)
        
        if [[ "$cert_modulus" == "$key_modulus" ]]; then
            log_success "Certificate and private key match"
        else
            log_error "Certificate and private key do not match!"
        fi
    else
        log_error "Certificate file not found"
    fi
    echo
}

# Test 7: Check nginx configuration
test_nginx_config() {
    echo -e "${BLUE}Test 7: Testing nginx configuration...${NC}"
    ((TOTAL_TESTS++))
    
    if command -v docker >/dev/null 2>&1; then
        nginx_container=$(docker ps --filter "name=nginx" --format "{{.Names}}" | head -1)
        if [[ -n "$nginx_container" ]]; then
            # Test nginx configuration
            if docker exec "$nginx_container" nginx -t >/dev/null 2>&1; then
                log_success "Nginx configuration is valid"
                
                # Check if SSL is configured
                if docker exec "$nginx_container" nginx -T 2>/dev/null | grep -q "ssl_certificate.*$DOMAIN"; then
                    log_success "SSL certificate configured in nginx"
                else
                    log_warning "SSL certificate configuration not found in nginx"
                fi
                
                # Check SSL protocols
                if docker exec "$nginx_container" nginx -T 2>/dev/null | grep -q "ssl_protocols.*TLSv1.3"; then
                    log_success "Modern SSL protocols (TLS 1.3) configured"
                else
                    log_info "Check SSL protocol configuration"
                fi
            else
                log_error "Nginx configuration has errors"
            fi
        else
            log_warning "Nginx container not available"
        fi
    else
        log_warning "Docker not available for nginx testing"
    fi
    echo
}

# Test 8: Test HTTP to HTTPS redirects
test_https_redirects() {
    echo -e "${BLUE}Test 8: Testing HTTP to HTTPS redirects...${NC}"
    
    test_urls=("$DOMAIN" "www.$DOMAIN" "test.$DOMAIN")
    
    for url in "${test_urls[@]}"; do
        ((TOTAL_TESTS++))
        echo -e "${YELLOW}Testing redirect: $url${NC}"
        
        # Test HTTP redirect to HTTPS
        if command -v curl >/dev/null 2>&1; then
            response=$(curl -s -I "http://$url" --max-time 10 | head -1 || echo "FAILED")
            
            if echo "$response" | grep -q "301\|302"; then
                location=$(curl -s -I "http://$url" --max-time 10 | grep -i "location:" | head -1)
                if echo "$location" | grep -q "https://"; then
                    log_success "HTTP to HTTPS redirect working for $url"
                else
                    log_warning "Redirect found but not to HTTPS for $url"
                fi
            else
                log_warning "No redirect found for $url (may be DNS issue)"
            fi
        else
            log_warning "curl not available for redirect testing"
        fi
    done
    echo
}

# Test 9: Check renewal configuration
test_renewal_config() {
    echo -e "${BLUE}Test 9: Checking certificate renewal configuration...${NC}"
    ((TOTAL_TESTS++))
    
    # Check if certbot is installed
    if command -v certbot >/dev/null 2>&1; then
        log_success "Certbot is installed"
        
        # Check renewal configuration
        if sudo test -f "/etc/letsencrypt/renewal/$DOMAIN.conf"; then
            log_success "Renewal configuration exists"
            
            # Check renewal timer
            if systemctl is-enabled certbot-khudroo.timer >/dev/null 2>&1; then
                log_success "Automatic renewal timer is enabled"
                
                if systemctl is-active certbot-khudroo.timer >/dev/null 2>&1; then
                    log_success "Renewal timer is active"
                else
                    log_warning "Renewal timer is not active"
                fi
            else
                log_warning "Automatic renewal timer not found"
            fi
        else
            log_warning "Renewal configuration not found"
        fi
    else
        log_warning "Certbot not installed"
    fi
    echo
}

# Test 10: Generate test report
generate_test_report() {
    echo -e "${PURPLE}============================================${NC}"
    echo -e "${PURPLE}   Test Results Summary                   ${NC}"
    echo -e "${PURPLE}============================================${NC}"
    echo
    
    echo -e "${BLUE}Total Tests: $TOTAL_TESTS${NC}"
    echo -e "${GREEN}Passed: $PASSED_TESTS${NC}"
    echo -e "${RED}Failed: $FAILED_TESTS${NC}"
    
    success_rate=$(( (PASSED_TESTS * 100) / TOTAL_TESTS ))
    echo -e "${BLUE}Success Rate: $success_rate%${NC}"
    echo
    
    if [[ $FAILED_TESTS -eq 0 ]]; then
        echo -e "${GREEN}🎉 All tests passed! Your wildcard SSL setup is working perfectly.${NC}"
        echo -e "${GREEN}✅ Your Odoo multi-tenant system is ready for HTTPS.${NC}"
    elif [[ $success_rate -ge 80 ]]; then
        echo -e "${YELLOW}⚠ Most tests passed. Minor issues detected.${NC}"
        echo -e "${YELLOW}🔧 Check the failed tests above and fix if necessary.${NC}"
    else
        echo -e "${RED}❌ Several tests failed. SSL setup needs attention.${NC}"
        echo -e "${RED}🚨 Review the configuration and fix issues before production use.${NC}"
    fi
    
    echo
    echo -e "${BLUE}Next steps:${NC}"
    echo "1. Start Docker containers: docker-compose up -d"
    echo "2. Test in browser: https://khudroo.com"
    echo "3. Test tenant URLs: https://[tenant-name].khudroo.com"
    echo "4. Monitor renewal: systemctl status certbot-khudroo.timer"
    echo
}

# Main execution
main() {
    test_certificate_files
    test_certificate_content
    test_wildcard_domains
    test_docker_containers
    test_ssl_connectivity
    test_certificate_chain
    test_nginx_config
    test_https_redirects
    test_renewal_config
    generate_test_report
}

# Run the tests
main "$@"
