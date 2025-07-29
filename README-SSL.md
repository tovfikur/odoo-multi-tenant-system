# SSL Configuration Guide

The nginx configuration has been updated to run on HTTP by default and optionally support HTTPS when SSL certificates are available.

## Current Configuration

- **Default**: HTTP only (port 80)
- **Optional**: HTTPS (port 443) when SSL certificates are configured

## Running without SSL (Default)

The system is configured to run on HTTP by default:

```bash
# Start the system normally
docker-compose up -d

# Access the application
# Main app: http://localhost or http://khudroo.com
# Tenants: http://tenant.khudroo.com or http://tenant.localhost
```

## Enabling SSL

### 1. Production SSL (Let's Encrypt)

For production with a real domain:

```bash
# Use the wildcard SSL setup script
./letsencrypt-wildcard-setup.sh

# Or manually place certificates in ssl/ directory:
# ssl/khudroo.com.crt
# ssl/khudroo.com.key
```

### 2. Development SSL (Self-signed)

For local development:

```bash
# Generate self-signed certificates
./scripts/generate-dev-ssl.sh

# Or manually create them:
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ssl/localhost.key \
  -out ssl/localhost.crt \
  -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"
```

### 3. Enable SSL Configuration

Once certificates are available:

```bash
# Run the SSL enable script
./scripts/enable-ssl.sh

# Or manually edit nginx/nginx.conf and uncomment:
# include /etc/nginx/ssl.conf;

# Restart nginx
docker-compose restart nginx
```

## File Structure

```
nginx/
├── nginx.conf          # Main config (HTTP by default)
├── ssl.conf            # SSL config (loaded when enabled)
ssl/
├── khudroo.com.crt     # Production SSL certificate
├── khudroo.com.key     # Production SSL private key
├── localhost.crt       # Development SSL certificate
└── localhost.key       # Development SSL private key
```

## Checking SSL Status

```bash
# Check if SSL is enabled
grep -n "include.*ssl.conf" nginx/nginx.conf

# Test nginx configuration
docker-compose exec nginx nginx -t

# Check SSL certificate
openssl x509 -in ssl/khudroo.com.crt -text -noout
```

## Benefits of This Setup

1. **Works out of the box**: No SSL setup required for basic operation
2. **Flexible**: Easy to enable SSL when ready
3. **Development friendly**: Supports both localhost and domain testing
4. **Production ready**: Full SSL support with proper security headers
5. **Graceful fallback**: Falls back to HTTP if SSL certificates are missing

## Troubleshooting

### Issue: nginx fails to start
- Check if SSL is enabled but certificates are missing
- Run `./scripts/enable-ssl.sh` to verify certificate status
- Disable SSL by commenting out the include line in nginx.conf

### Issue: Mixed content warnings
- Ensure all internal links use relative URLs
- Check that proxy headers are set correctly
- Verify `X-Forwarded-Proto` header is passed to backend services

### Issue: Certificate errors
- Verify certificate files exist and are readable
- Check certificate validity: `openssl x509 -in ssl/khudroo.com.crt -dates -noout`
- Ensure certificate matches the domain name
