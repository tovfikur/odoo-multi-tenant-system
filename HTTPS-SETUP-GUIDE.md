# HTTPS Setup Guide for Odoo Multi-Tenant System

## Overview

Your Odoo Multi-Tenant System has been configured to work with HTTPS using **Let's Encrypt wildcard SSL certificates** for `*.khudroo.com`. This setup ensures that all automatically generated tenant subdomains work perfectly with HTTPS.

## Why Wildcard SSL?

In your multi-tenant system:
- **Tenants get automatic subdomains**: `tenant1.khudroo.com`, `client-abc.khudroo.com`, etc.
- **Wildcard certificate covers ALL subdomains**: `*.khudroo.com`
- **No manual certificate management** needed for new tenants
- **Single certificate** for unlimited subdomains

## What's Been Done

✅ **Nginx Configuration Updated**: The nginx configuration now includes:
- HTTP to HTTPS redirects for all domains
- Wildcard SSL certificate support for `*.khudroo.com`
- Enhanced security headers (HSTS, CSP, etc.)
- Modern SSL protocols (TLS 1.2, 1.3)

✅ **Application Code Updated**: Fixed HTTP URLs to use HTTPS in:
- Template files (registration status pages)
- Billing payment URLs
- Tenant URL generation
- Session management

✅ **Let's Encrypt Scripts Created**: 
- `letsencrypt-wildcard-setup.sh` - Complete wildcard SSL setup
- `test-wildcard-ssl.sh` - Comprehensive SSL testing
- `DNS-VALIDATION-GUIDE.md` - Step-by-step DNS validation

## Quick Setup Steps

### 🚀 Production Setup (Let's Encrypt Wildcard) - RECOMMENDED

#### Step 1: Run the Let's Encrypt Setup
```bash
# Make script executable
chmod +x letsencrypt-wildcard-setup.sh

# Run the setup (this will guide you through everything)
./letsencrypt-wildcard-setup.sh
```

#### Step 2: DNS Validation (Required)
The script will prompt you to add DNS TXT records. Follow the [DNS Validation Guide](DNS-VALIDATION-GUIDE.md):

1. **Script shows TXT record**: `_acme-challenge.khudroo.com` with a specific value
2. **Add to your DNS provider**: Cloudflare, GoDaddy, Namecheap, etc.
3. **Wait for propagation**: Usually 1-5 minutes
4. **Continue in script**: Press Enter to validate

#### Step 3: Automatic Setup Completion
The script will:
- ✅ Obtain wildcard certificate from Let's Encrypt
- ✅ Copy certificates to Docker directory
- ✅ Set up automatic renewal (twice daily)
- ✅ Test certificate functionality

### 🔧 Development Setup (Self-Signed)

For local development only:
```bash
# On Windows
generate-ssl-windows.bat

# On Linux/WSL
chmod +x ssl-setup.sh
./ssl-setup.sh
# Choose option 2 (Self-signed certificate)
```

### 2. Manual SSL Certificate Setup (Alternative)

If you prefer manual setup, create the SSL certificates:

**For Development (Self-signed):**
```bash
# Create SSL directory
sudo mkdir -p /etc/nginx/ssl

# Generate khudroo.com certificate
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/nginx/ssl/khudroo.com.key \
  -out /etc/nginx/ssl/khudroo.com.crt \
  -subj "/C=BD/ST=Dhaka/L=Dhaka/O=Khudroo/CN=khudroo.com" \
  -extensions v3_req \
  -config <(cat /etc/ssl/openssl.cnf <(printf "[v3_req]\nsubjectAltName=DNS:khudroo.com,DNS:*.khudroo.com"))

# Generate localhost certificate
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/nginx/ssl/localhost.key \
  -out /etc/nginx/ssl/localhost.crt \
  -subj "/C=BD/ST=Dhaka/L=Dhaka/O=Khudroo Dev/CN=localhost" \
  -extensions v3_req \
  -config <(cat /etc/ssl/openssl.cnf <(printf "[v3_req]\nsubjectAltName=DNS:localhost,DNS:*.localhost,IP:127.0.0.1"))

# Set proper permissions
sudo chmod 644 /etc/nginx/ssl/*.crt
sudo chmod 600 /etc/nginx/ssl/*.key
```

### 3. Docker Configuration

Your Docker setup already supports SSL with the volume mount:
```yaml
volumes:
  - ./ssl:/etc/nginx/ssl
```

Make sure you have an `ssl` directory in your project root:
```bash
mkdir ssl
```

### 4. DNS Configuration

For production, ensure your DNS has:
```
khudroo.com.        A    YOUR_SERVER_IP
www.khudroo.com.    A    YOUR_SERVER_IP
*.khudroo.com.      A    YOUR_SERVER_IP
```

For development, add to your hosts file (`C:\Windows\System32\drivers\etc\hosts` on Windows):
```
127.0.0.1 localhost
127.0.0.1 khudroo.com
127.0.0.1 www.khudroo.com
127.0.0.1 test.khudroo.com
127.0.0.1 any-subdomain.khudroo.com
```

### 5. Test Your Setup

1. **Start the services:**
   ```bash
   docker-compose up -d
   ```

2. **Test HTTPS access:**
   - Main site: `https://khudroo.com`
   - Subdomains: `https://any-subdomain.khudroo.com`
   - Localhost: `https://localhost`

3. **Verify SSL certificate:**
   ```bash
   openssl s_client -connect khudroo.com:443 -servername khudroo.com
   ```

## Troubleshooting

### Common Issues

1. **Certificate not found errors:**
   - Ensure SSL certificates are in the correct location: `./ssl/` directory
   - Check file permissions and naming

2. **Browser security warnings:**
   - Expected for self-signed certificates
   - Click "Advanced" → "Proceed to site" to continue

3. **Mixed content warnings:**
   - Check for any remaining HTTP resources
   - Update any hardcoded HTTP URLs to HTTPS

4. **Connection refused on HTTPS:**
   - Check if nginx container is running: `docker-compose ps`
   - Verify port 443 is exposed and not blocked by firewall

### SSL Certificate Files Required

Your setup expects these files:
```
ssl/
├── khudroo.com.crt     # Wildcard certificate for *.khudroo.com
├── khudroo.com.key     # Private key for khudroo.com
├── localhost.crt       # Certificate for localhost development
└── localhost.key       # Private key for localhost
```

### Environment Variables

Make sure these environment variables are set correctly:
```bash
DOMAIN=khudroo.com                    # Your main domain
ODOO_MASTER_URL=http://odoo_master:8069   # Internal communication stays HTTP
SECRET_KEY=your-secret-key            # Flask secret key
```

## Security Notes

1. **Private Keys**: Keep your private key files secure and never commit them to version control
2. **Production Certificates**: Use Let's Encrypt or commercial certificates for production
3. **Certificate Renewal**: Set up automatic renewal for Let's Encrypt certificates
4. **Firewall**: Ensure ports 80 and 443 are open in your firewall

## Monitoring

1. **Certificate Expiration**: The SSL setup script includes monitoring
2. **Health Checks**: Available at `https://health.khudroo.com/health`
3. **Logs**: Check nginx logs for SSL-related issues:
   ```bash
   docker-compose logs nginx
   ```

## Production Checklist

- [ ] Valid SSL certificates installed
- [ ] DNS wildcard record configured
- [ ] Firewall ports 80/443 open
- [ ] Certificate auto-renewal configured
- [ ] Security headers enabled
- [ ] HSTS enabled
- [ ] All HTTP URLs updated to HTTPS
- [ ] Mixed content issues resolved

Your Odoo Multi-Tenant System is now ready for HTTPS! 🚀
