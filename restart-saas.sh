#!/bin/bash

# Restart SaaS Manager to apply billing fix
echo "🔄 Restarting SaaS Manager to apply billing fix..."

# Stop the container completely
echo "Stopping SaaS Manager..."
docker-compose stop saas_manager

# Remove the container to force rebuild
echo "Removing old container..."
docker-compose rm -f saas_manager

# Rebuild and start with fresh code
echo "Rebuilding and starting SaaS Manager..."
docker-compose build saas_manager
docker-compose up -d saas_manager

# Wait for startup
echo "Waiting for container to start..."
sleep 15

# Check status
echo "Checking container status..."
docker-compose ps saas_manager

# Check for startup errors
echo "Checking startup logs..."
docker-compose logs --tail=30 saas_manager

echo "✅ SaaS Manager restarted with billing fix"
echo "🧪 The billing error should now be resolved"