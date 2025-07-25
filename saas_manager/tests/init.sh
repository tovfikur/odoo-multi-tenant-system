#!/bin/bash

# Check if setup is already complete
if [ -f /var/log/setup-complete ]; then
    echo "Setup already complete, starting SSH service..."
    service ssh start
    exit 0
fi

echo "Starting initial setup..."

# Update package list
apt-get update

# Install required packages
apt-get install -y openssh-server sudo nano vim curl wget net-tools htop

# Configure SSH
mkdir -p /var/run/sshd
sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config

# Create admin user if doesn't exist
if ! id admin >/dev/null 2>&1; then
    useradd -m -s /bin/bash admin
    echo 'admin:admin' | chpasswd
    usermod -aG sudo admin
    echo 'admin ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers
    echo "Admin user created successfully"
else
    echo "Admin user already exists"
fi

# Set root password (optional)
echo 'root:root' | chpasswd

# Start SSH service
service ssh start

# Mark setup as complete
touch /var/log/setup-complete

echo "Setup complete! SSH service started."
echo "You can now connect via SSH:"
echo "  ssh admin@localhost -p [PORT]"
echo "  Username: admin"
echo "  Password: admin"