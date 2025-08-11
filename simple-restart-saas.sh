#!/bin/bash

# Simple restart of just the SaaS Manager container
echo "🔄 Simple restart of SaaS Manager..."

# Check current status
echo "Current container status:"
docker-compose ps

# Just restart the saas_manager service
echo "Restarting only SaaS Manager..."
docker-compose up -d --force-recreate --no-deps saas_manager

# Wait for startup
echo "Waiting for container to start..."
sleep 10

# Check status
echo "New container status:"
docker-compose ps saas_manager

# Check for errors in logs
echo "Recent logs:"
docker-compose logs --tail=20 saas_manager

echo "✅ SaaS Manager restarted"
echo "🧪 Test the billing functionality now"