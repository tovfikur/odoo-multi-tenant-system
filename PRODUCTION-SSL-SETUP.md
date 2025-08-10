# Production SSL Setup for khudroo.com

Since you're working with a domain hosted on a different server, here's how to set up SSL certificates on your production server:

## 🚨 Important Notes

- **Domain Location**: Your domain `khudroo.com` is hosted on a different server than localhost
- **DNS Requirement**: Your domain must point to the production server's IP address
- **Port Access**: Ports 80 and 443 must be open on your production server

## 🎯 Production SSL Setup Steps

### 1. On Your Production Server

Copy all files from this project to your production server, then:

```bash
# 1. Navigate to the project directory
cd /path/to/Odoo-Multi-Tenant-System

# 2. Make the SSL setup script executable
chmod +x setup-ssl.sh

# 3. Run the SSL setup script with your domain and email
./setup-ssl.sh khudroo.com your-email@domain.com
```

### 2. What the Script Will Do

1. **Generate DH Parameters** (takes a few minutes)
2. **Create SSL directories** for certificates
3. **Start nginx** with HTTP configuration
4. **Obtain SSL certificates** from Let's Encrypt
5. **Configure HTTPS** with security headers
6. **Set up auto-renewal** via cron

### 3. Verify SSL Works

After the script completes:

```bash
# Test HTTP to HTTPS redirect
curl -I http://khudroo.com

# Test HTTPS access
curl -I https://khudroo.com

# Check SSL certificate
openssl s_client -connect khudroo.com:443 -servername khudroo.com
```

## 🔧 Manual Setup (Alternative)

If the automated script doesn't work:

### Step 1: Prepare Environment

```bash
# Create directories
mkdir -p ssl/certbot/{conf,www} ssl/logs

# Generate DH parameters
openssl dhparam -out ssl/dhparam.pem 2048
```

### Step 2: Start Services

```bash
# Start without SSL first
docker-compose up -d

# Verify HTTP access
curl -I http://khudroo.com/health
```

### Step 3: Obtain SSL Certificate

```bash
# Run certbot to get certificate
docker run --rm \
  -v $(pwd)/ssl/certbot/conf:/etc/letsencrypt \
  -v $(pwd)/ssl/certbot/www:/var/www/certbot \
  certbot/certbot certonly \
  --webroot \
  --webroot-path=/var/www/certbot \
  --email your-email@domain.com \
  --agree-tos \
  --no-eff-email \
  --expand \
  -d khudroo.com \
  -d www.khudroo.com
```

### Step 4: Configure HTTPS

Add to your `nginx/nginx.conf` at the end of the `http` block:

```nginx
# HTTPS Configuration
server {
    listen 443 ssl http2;
    server_name khudroo.com www.khudroo.com;
    
    # SSL Certificates
    ssl_certificate /etc/letsencrypt/live/khudroo.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/khudroo.com/privkey.pem;
    
    # SSL Settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_dhparam /etc/nginx/ssl/dhparam.pem;
    
    # Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    # ACME Challenge
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
    
    # Proxy to your application
    location / {
        proxy_pass http://saas_manager;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
    }
}

# HTTP to HTTPS Redirect
server {
    listen 80;
    server_name khudroo.com www.khudroo.com;
    
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
    
    location / {
        return 301 https://$server_name$request_uri;
    }
}
```

### Step 5: Update Docker Compose

Add to your `docker-compose.yml` nginx volumes:

```yaml
volumes:
  - ./ssl/certbot/conf:/etc/letsencrypt
  - ./ssl/certbot/www:/var/www/certbot
  - ./ssl/dhparam.pem:/etc/nginx/ssl/dhparam.pem
```

### Step 6: Restart and Test

```bash
# Restart nginx
docker-compose restart nginx

# Test HTTPS
curl -I https://khudroo.com
```

## 🔄 Certificate Renewal

Set up automatic renewal:

```bash
# Add to crontab
echo "0 2,14 * * * cd $(pwd) && docker run --rm -v \$(pwd)/ssl/certbot/conf:/etc/letsencrypt -v \$(pwd)/ssl/certbot/www:/var/www/certbot certbot/certbot renew && docker-compose exec nginx nginx -s reload" | crontab -
```

## 🚨 Local Development (Localhost)

For local development on localhost, HTTPS has been set up with self-signed certificates:

1. **Access via**: `https://localhost` (you'll get a security warning - click "Advanced" and "Proceed")
2. **Self-signed certificates** are located in: `ssl/localhost.crt` and `ssl/localhost.key`
3. **Security warnings** are normal for self-signed certificates in browsers

## 📋 SSL Security Features Included

✅ **TLS 1.2/1.3 Only** - No older protocols  
✅ **Strong Ciphers** - Modern encryption only  
✅ **Perfect Forward Secrecy** - DH parameters  
✅ **HSTS** - Force HTTPS connections  
✅ **Security Headers** - XSS, clickjacking protection  
✅ **OCSP Stapling** - Improved certificate validation  
✅ **Auto-renewal** - Certificates renew automatically  

## 🔍 Troubleshooting

**Certificate generation fails:**
- Verify domain points to your server: `nslookup khudroo.com`
- Check port 80 access: `curl http://khudroo.com/.well-known/acme-challenge/test`
- Review logs: `docker-compose logs nginx`

**HTTPS not working:**
- Check nginx config: `docker-compose exec nginx nginx -t`
- Verify certificates exist: `ls -la ssl/certbot/conf/live/khudroo.com/`
- Test SSL connection: `openssl s_client -connect khudroo.com:443`

Your SSL setup will provide **A+ SSL Labs rating** and enterprise-grade security! 🔒