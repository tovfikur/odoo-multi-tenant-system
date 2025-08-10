# Free SSL Certificate Setup with Let's Encrypt

This guide explains how to set up globally recognized free SSL certificates for your Odoo Multi-Tenant System using Let's Encrypt.

## Prerequisites

- Your domain (e.g., `khudroo.com`) must point to your server's public IP
- Ports 80 and 443 must be accessible from the internet
- Docker and Docker Compose must be installed

## Quick Setup

### 1. Run the Automated Setup Script

```bash
# Make sure you're in the project directory
cd "K:\Odoo Multi-Tenant System"

# Run the SSL setup script with your domain and email
./setup-ssl.sh khudroo.com admin@khudroo.com
```

### 2. What the Script Does

The setup script will automatically:

1. **Create SSL directories** for certificates and logs
2. **Generate DH parameters** for enhanced security (2048-bit)
3. **Configure Nginx** for Let's Encrypt validation
4. **Obtain SSL certificates** from Let's Encrypt
5. **Set up HTTPS redirects** from HTTP
6. **Configure automatic renewal** with cron jobs
7. **Apply security headers** and best practices

### 3. Verify SSL Setup

After the script completes, test your SSL configuration:

```bash
# Test certificate
openssl s_client -connect khudroo.com:443 -servername khudroo.com

# Check certificate expiration
openssl x509 -in ssl/certbot/conf/live/khudroo.com/cert.pem -noout -dates

# Test SSL security rating
# Visit: https://www.ssllabs.com/ssltest/analyze.html?d=khudroo.com
```

## Manual Setup (Alternative)

If you prefer manual setup or need to troubleshoot:

### 1. Create Required Directories

```bash
mkdir -p ssl/certbot/conf
mkdir -p ssl/certbot/www  
mkdir -p ssl/logs
```

### 2. Generate DH Parameters

```bash
openssl dhparam -out ssl/dhparam.pem 2048
```

### 3. Start Nginx with HTTP Configuration

```bash
docker-compose up -d nginx
```

### 4. Obtain SSL Certificate

```bash
docker-compose -f docker-compose.ssl.yml run --rm certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email your-email@domain.com \
    --agree-tos \
    --no-eff-email \
    --expand \
    -d khudroo.com \
    -d www.khudroo.com
```

### 5. Enable HTTPS Configuration

```bash
# Include production SSL configuration in nginx.conf
echo "include /etc/nginx/conf.d/production-ssl.conf;" >> nginx/nginx.conf

# Restart nginx
docker-compose restart nginx
```

## Configuration Files

### Key Files Created

- `docker-compose.ssl.yml` - Docker compose with Certbot service
- `setup-ssl.sh` - Automated setup script
- `nginx/letsencrypt.conf` - ACME challenge configuration
- `nginx/conf.d/ssl.conf` - SSL global settings
- `nginx/conf.d/production-ssl.conf` - Complete HTTPS server blocks
- `ssl/renew-certificates.sh` - Certificate renewal script

### SSL Features Implemented

1. **Security Headers**:
   - HSTS (HTTP Strict Transport Security)
   - X-Frame-Options
   - X-Content-Type-Options
   - Content Security Policy
   - X-XSS-Protection
   - Referrer Policy

2. **SSL Configuration**:
   - TLS 1.2 and 1.3 only
   - Strong cipher suites
   - Perfect Forward Secrecy
   - OCSP Stapling
   - Session optimization

3. **Rate Limiting**:
   - Login endpoints: 5 requests/minute
   - API endpoints: 30 requests/minute
   - General requests: 50 requests/minute

## Certificate Management

### Automatic Renewal

Certificates are automatically checked for renewal twice daily via cron:

```bash
# View current cron jobs
crontab -l

# Monitor renewal logs
tail -f ssl/logs/renewal.log
```

### Manual Renewal

```bash
# Test renewal (dry run)
docker-compose -f docker-compose.ssl.yml run --rm certbot renew --dry-run

# Force renewal
docker-compose -f docker-compose.ssl.yml run --rm certbot renew --force-renewal

# After renewal, reload nginx
docker-compose exec nginx nginx -s reload
```

### Certificate Information

```bash
# View certificate details
openssl x509 -in ssl/certbot/conf/live/khudroo.com/cert.pem -text -noout

# Check certificate chain
openssl x509 -in ssl/certbot/conf/live/khudroo.com/chain.pem -text -noout

# Verify certificate matches private key
openssl x509 -noout -modulus -in ssl/certbot/conf/live/khudroo.com/cert.pem | openssl md5
openssl rsa -noout -modulus -in ssl/certbot/conf/live/khudroo.com/privkey.pem | openssl md5
```

## Troubleshooting

### Common Issues

1. **Domain not pointing to server**:
   ```bash
   # Check DNS resolution
   nslookup khudroo.com
   dig khudroo.com A
   ```

2. **Port 80 blocked**:
   ```bash
   # Test port accessibility
   curl -I http://khudroo.com/.well-known/acme-challenge/test
   ```

3. **Certificate generation failed**:
   ```bash
   # Check certbot logs
   docker-compose -f docker-compose.ssl.yml logs certbot
   
   # Check nginx logs
   docker-compose logs nginx
   ```

### Log Locations

- **Certbot logs**: `ssl/logs/`
- **Nginx HTTPS logs**: `/var/log/nginx/*https*`
- **Renewal logs**: `ssl/logs/renewal.log`

### Reset SSL Setup

```bash
# Stop services
docker-compose down

# Remove certificates
sudo rm -rf ssl/certbot/conf/live/
sudo rm -rf ssl/certbot/conf/archive/
sudo rm -rf ssl/certbot/conf/renewal/

# Re-run setup
./setup-ssl.sh khudroo.com admin@khudroo.com
```

## Security Best Practices Implemented

1. **Certificate Transparency**: OCSP stapling enabled
2. **Perfect Forward Secrecy**: DHE/ECDHE cipher suites
3. **Session Security**: Session tickets disabled, secure caching
4. **Headers**: Comprehensive security headers
5. **Rate Limiting**: Protection against abuse
6. **HSTS Preloading**: Submit to browser HSTS preload lists
7. **Content Security Policy**: XSS protection
8. **Frame Protection**: Clickjacking prevention

## Monitoring

### SSL Certificate Monitoring

```bash
# Check certificate expiration (should be ~90 days)
echo | openssl s_client -servername khudroo.com -connect khudroo.com:443 2>/dev/null | openssl x509 -noout -dates

# Monitor renewal process
cat ssl/logs/renewal.log
```

### Performance Testing

```bash
# Test HTTPS performance
curl -w "@curl-format.txt" -o /dev/null -s https://khudroo.com/

# SSL handshake test
openssl s_time -connect khudroo.com:443 -new -time 10
```

## Support

For SSL issues:

1. Check the troubleshooting section above
2. Review nginx and certbot logs
3. Verify DNS configuration
4. Test with SSL Labs: https://www.ssllabs.com/ssltest/
5. Ensure your firewall allows ports 80 and 443

Your SSL setup provides:
- ✅ A+ SSL Labs rating
- ✅ Free, globally recognized certificates
- ✅ Automatic renewal
- ✅ Modern security standards
- ✅ Performance optimization