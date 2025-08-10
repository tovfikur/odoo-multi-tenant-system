# 🚀 Deploy SSL to Production Server

## Quick Deployment Guide

After pulling the latest code to your production server, follow these steps:

### Step 1: Git Pull on Production Server
```bash
cd /home/kendroo/odoo-multi-tenant-system
git pull origin main
```

### Step 2: Run the Quick SSL Setup
```bash
# Option 1: Quick setup script (recommended)
./quick-ssl-setup.sh khudroo.com admin@khudroo.com

# Option 2: Original detailed setup script
./setup-ssl.sh khudroo.com admin@khudroo.com
```

### Step 3: Verify SSL is Working
```bash
# Test HTTPS
curl -I https://khudroo.com

# Check certificate
openssl s_client -connect khudroo.com:443 -servername khudroo.com
```

## What's Been Fixed

✅ **Docker Compose**: Added SSL certificate volumes  
✅ **SSL Scripts**: Fixed network detection and certificate paths  
✅ **Production Config**: Ready for Let's Encrypt certificates  
✅ **Auto-renewal**: Cron job configured for certificate renewal  

## Files Updated

- `docker-compose.yml` - Added SSL volume mounts
- `setup-ssl.sh` - Fixed network detection and paths
- `quick-ssl-setup.sh` - New simplified setup script
- `enable-production-ssl.sh` - Enhanced production configuration
- `nginx/conf.d/production-ssl.conf.disabled` - Ready for production

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