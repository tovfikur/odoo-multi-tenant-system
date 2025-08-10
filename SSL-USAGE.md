# 🔒 SSL Auto-Setup Script Usage Guide

## Quick Start

The `ssl-auto-setup.sh` script provides comprehensive SSL certificate setup with bulletproof error handling and smart certificate path detection.

### Basic Usage

```bash
# Use defaults (khudroo.com, admin@khudroo.com)
./ssl-auto-setup.sh

# Specify domain and email
./ssl-auto-setup.sh yourdomain.com admin@yourdomain.com

# Enable debug mode for troubleshooting
./ssl-auto-setup.sh --debug yourdomain.com admin@yourdomain.com

# Force certificate renewal even if valid certificate exists
./ssl-auto-setup.sh --force yourdomain.com admin@yourdomain.com

# Skip connectivity tests (useful for NAT/router environments)
./ssl-auto-setup.sh --skip-tests yourdomain.com admin@yourdomain.com
```

### Command Line Options

| Option | Description |
|--------|-------------|
| `-h, --help` | Show help message and usage examples |
| `-d, --debug` | Enable verbose debug logging |
| `-f, --force` | Force certificate renewal even if valid certificate exists |
| `-s, --skip-tests` | Skip local connectivity tests |
| `--version` | Show script version |

### Environment Variables

You can also use environment variables:

```bash
export SSL_DOMAIN="yourdomain.com"
export SSL_EMAIL="admin@yourdomain.com"
export SSL_DEBUG="true"
./ssl-auto-setup.sh
```

## Key Features

### 🎯 Smart Certificate Path Detection
- Automatically finds certificates even with Let's Encrypt suffix naming (-0001, -0002)
- Handles multiple certificate directories
- Verifies certificate validity and expiration

### 🔧 Comprehensive Error Handling
- Lock mechanism prevents concurrent runs
- Detailed logging with timestamps
- Automatic cleanup on script failure
- Helpful error messages with solutions

### 🐳 Docker Integration
- Multiple methods for Docker network detection
- Automatic container management and health checks
- Nginx configuration validation and testing

### 🔐 Modern SSL Configuration
- TLS 1.2 and 1.3 only
- Perfect Forward Secrecy
- HSTS with preload support
- Comprehensive security headers
- OCSP stapling enabled

### 🔄 Auto-Renewal Setup
- Automatic cron job creation
- Certificates checked twice daily (2 AM and 2 PM)
- Nginx reload after successful renewal
- Detailed renewal logging

## Script Workflow

The script follows these steps:

1. **System Checks** - Validate prerequisites and project structure
2. **Directory Setup** - Create SSL directories with proper permissions
3. **Docker Management** - Detect network and start/restart containers
4. **Connectivity Tests** - Verify local nginx is responding
5. **Certificate Preparation** - Generate DH parameters if needed
6. **Certificate Acquisition** - Request SSL certificate from Let's Encrypt
7. **Certificate Verification** - Validate certificate files and expiration
8. **Nginx Configuration** - Create modern SSL configuration
9. **Service Restart** - Restart nginx with SSL configuration
10. **Auto-Renewal Setup** - Configure automatic certificate renewal
11. **Final Testing** - Test HTTPS connectivity (if not skipped)

## Log Files

- **Setup Log**: `ssl/logs/ssl-setup.log` - Complete setup process log
- **Renewal Log**: `ssl/logs/renewal.log` - Auto-renewal process log

## Troubleshooting

### Common Issues

1. **Domain DNS not pointing to server**
   ```bash
   # Check DNS resolution
   nslookup yourdomain.com
   dig yourdomain.com
   ```

2. **Firewall blocking ports 80/443**
   ```bash
   # Check if ports are open
   sudo ufw status
   sudo iptables -L
   ```

3. **Docker containers not running**
   ```bash
   # Check container status
   docker-compose ps
   docker-compose logs
   ```

4. **Let's Encrypt rate limits**
   - Wait 1 hour between failed attempts
   - Use staging environment for testing

### Debug Mode

Run with `--debug` flag for verbose output:

```bash
./ssl-auto-setup.sh --debug yourdomain.com admin@yourdomain.com
```

This provides detailed information about:
- Network detection process
- Certificate path searches
- Docker commands executed
- Configuration file changes

### Manual Certificate Check

After successful setup, verify your certificate:

```bash
# Check certificate expiration
openssl x509 -in ssl/certbot/conf/live/yourdomain.com/cert.pem -noout -dates

# Test SSL connection
openssl s_client -connect yourdomain.com:443 -servername yourdomain.com

# Check SSL rating
curl -I https://yourdomain.com
```

## NAT/Router Environments

If your server is behind NAT/router (like the user's khudroo.com setup):

1. Use `--skip-tests` to skip local connectivity tests
2. Ensure domain DNS points to your public IP
3. Configure router port forwarding for ports 80 and 443
4. Test HTTPS access from external network

```bash
./ssl-auto-setup.sh --skip-tests khudroo.com admin@khudroo.com
```

## Success Indicators

✅ **Script completes without errors**  
✅ **Green success messages throughout**  
✅ **https://yourdomain.com loads with green lock**  
✅ **SSL Labs test shows A+ rating**  
✅ **Auto-renewal cron job is active**  

## Next Steps After Success

1. **Visit your site**: https://yourdomain.com
2. **Test SSL rating**: https://www.ssllabs.com/ssltest/analyze.html?d=yourdomain.com
3. **Monitor renewals**: `tail -f ssl/logs/renewal.log`
4. **Check certificate expiry**: Use OpenSSL commands above

Your Odoo Multi-Tenant System is now secured with globally trusted SSL certificates! 🎉