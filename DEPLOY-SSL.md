# 🚀 Deploy SSL to Production Server

## Quick Deployment Guide

After pulling the latest code to your production server, follow these steps:

### Step 1: Git Pull on Production Server
```bash
cd /home/kendroo/odoo-multi-tenant-system
git pull origin main
```

### Step 2: Run the Automated SSL Setup
```bash
# NEW: Comprehensive automated setup (RECOMMENDED)
./ssl-auto-setup.sh khudroo.com admin@khudroo.com

# Alternative options:
./get-ssl-main.sh khudroo.com admin@khudroo.com    # Main domain only
./setup-production-ssl.sh khudroo.com admin@khudroo.com    # Production focused
```

### Step 3: Verify SSL is Working
```bash
# Test HTTPS
curl -I https://khudroo.com

# Check certificate
openssl s_client -connect khudroo.com:443 -servername khudroo.com
```

## What's Been Fixed

✅ **Comprehensive SSL Script**: New automated setup with bulletproof error handling  
✅ **Smart Certificate Detection**: Handles Let's Encrypt suffix naming (-0001, -0002)  
✅ **Docker Network Detection**: Multiple fallback methods for network discovery  
✅ **Production Config**: Modern SSL configuration with security headers  
✅ **Auto-renewal**: Cron job configured for certificate renewal  
✅ **Logging**: Comprehensive logging and debug modes  

## Files Updated

- `ssl-auto-setup.sh` - **NEW** comprehensive automated SSL setup
- `get-ssl-main.sh` - Main domain only setup (working)
- `setup-production-ssl.sh` - Production-focused comprehensive setup
- `docker-compose.yml` - Added SSL volume mounts
- `nginx/conf.d/` - SSL configurations ready for production

## Expected Results

After running the script successfully:

🔒 **HTTPS Active**: https://khudroo.com  
🌟 **A+ SSL Rating**: SSL Labs test  
🔄 **Auto-renewal**: Certificates renew automatically  
🛡️ **Security Headers**: HSTS, XSS protection, etc.  

## Troubleshooting

### If SSL setup fails:

1. **Check domain DNS**: `nslookup khudroo.com`
2. **Verify containers**: `docker-compose ps`
3. **Check nginx logs**: `docker-compose logs nginx`
4. **Test port 80**: `curl -I http://khudroo.com/health`

### Common issues:
- **Rate limit**: Wait 1 hour and try again
- **DNS not pointing**: Update DNS records
- **Firewall**: Open ports 80 and 443
- **Docker network**: Check `docker network ls`

## Manual Commands (if needed)

```bash
# Create directories
mkdir -p ssl/certbot/conf ssl/certbot/www ssl/logs

# Restart containers
docker-compose up -d

# Get certificate manually
NETWORK_NAME=$(docker network ls | grep odoo | awk '{print $2}' | head -1)
docker run --rm \
  -v $(pwd)/ssl/certbot/conf:/etc/letsencrypt \
  -v $(pwd)/ssl/certbot/www:/var/www/certbot \
  --network $NETWORK_NAME \
  certbot/certbot certonly \
  --webroot \
  --webroot-path=/var/www/certbot \
  --email admin@khudroo.com \
  --agree-tos \
  --no-eff-email \
  -d khudroo.com \
  -d www.khudroo.com
```

## Success Indicators

✅ **Script completes without errors**  
✅ **https://khudroo.com loads with green lock**  
✅ **Browser shows "Secure" or lock icon**  
✅ **SSL Labs test shows A+ rating**  
✅ **Auto-renewal cron job is active**  

Your Odoo Multi-Tenant System will be fully secured with globally recognized SSL certificates! 🎉