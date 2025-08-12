#!/bin/bash

# Fix billing error and restart SaaS Manager
echo "🔧 Fixing billing service error..."

echo "Restarting SaaS Manager container..."
docker-compose restart saas_manager

echo "Waiting for container to start..."
sleep 10

echo "Checking container status..."
docker-compose ps saas_manager

echo "Checking logs for any startup errors..."
docker-compose logs --tail=20 saas_manager

echo "✅ Billing fix applied and SaaS Manager restarted"
echo "🧪 Test database creation from the web interface"