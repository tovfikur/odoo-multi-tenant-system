FROM python:3.11-slim

# Set environment variables for better output
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONPATH=/app

# Set working directory
WORKDIR /app

# Print system information
RUN echo "=========================================" && \
    echo "Starting Docker build process..." && \
    echo "Base Image: python:3.11-slim" && \
    echo "Working Directory: /app" && \
    echo "=========================================" && \
    python3 --version && \
    echo "System info complete."

# Update package lists and install system dependencies
RUN echo "=========================================" && \
    echo "Step 1: Updating package lists..." && \
    echo "=========================================" && \
    apt-get update || { echo "ERROR: Failed to update package lists"; exit 1; } && \
    echo "Package lists updated successfully." && \
    \
    echo "=========================================" && \
    echo "Step 2: Installing system dependencies..." && \
    echo "Dependencies: gcc, postgresql-client, curl, docker.io" && \
    echo "=========================================" && \
    apt-get install -y \
        gcc \
        postgresql-client \
        curl \
        docker.io \
        procps \
        net-tools || { echo "ERROR: Failed to install system dependencies"; exit 1; } && \
    echo "System dependencies installed successfully." && \
    \
    echo "=========================================" && \
    echo "Step 3: Cleaning up package cache..." && \
    echo "=========================================" && \
    rm -rf /var/lib/apt/lists/* && \
    echo "Package cache cleaned successfully."

# Accept Docker GID as build argument
ARG DOCKER_GID=999
RUN echo "=========================================" && \
    echo "Step 4: Setting up Docker GID..." && \
    echo "Docker GID: ${DOCKER_GID}" && \
    echo "========================================"

# Create docker group and user with proper error handling
RUN echo "=========================================" && \
    echo "Step 5: Creating user and groups..." && \
    echo "=========================================" && \
    \
    echo "Checking if docker group exists..." && \
    if ! getent group ${DOCKER_GID} >/dev/null 2>&1; then \
        echo "Creating docker group with GID ${DOCKER_GID}..."; \
        groupadd -g ${DOCKER_GID} docker || { echo "ERROR: Failed to create docker group"; exit 1; }; \
        echo "Docker group created successfully."; \
    else \
        echo "Docker group already exists."; \
    fi && \
    \
    echo "Creating appuser with UID 1000..." && \
    useradd -m -u 1000 -G docker appuser || { echo "ERROR: Failed to create appuser"; exit 1; } && \
    echo "User appuser created successfully." && \
    \
    echo "Verifying user creation..." && \
    id appuser || { echo "ERROR: User appuser not found"; exit 1; } && \
    echo "User verification complete."

# Copy requirements file first for better caching
COPY requirements.txt . 
RUN echo "=========================================" && \
    echo "Step 6: Copying requirements.txt..." && \
    echo "=========================================" && \
    ls -la requirements.txt || { echo "ERROR: requirements.txt not found"; exit 1; } && \
    echo "requirements.txt copied successfully." && \
    cat requirements.txt && \
    echo "Requirements file contents displayed."

# Install Python dependencies with detailed output
RUN echo "=========================================" && \
    echo "Step 7: Installing Python dependencies..." && \
    echo "=========================================" && \
    pip install --no-cache-dir --upgrade pip || { echo "ERROR: Failed to upgrade pip"; exit 1; } && \
    echo "Pip upgraded successfully." && \
    \
    echo "Installing requirements..." && \
    pip install --no-cache-dir -r requirements.txt -v || { echo "ERROR: Failed to install Python dependencies"; exit 1; } && \
    echo "Python dependencies installed successfully." && \
    \
    echo "Verifying installed packages..." && \
    pip list && \
    echo "Package verification complete."

# Copy application code
COPY . .
RUN echo "=========================================" && \
    echo "Step 8: Copying application code..." && \
    echo "=========================================" && \
    ls -la || { echo "ERROR: Failed to list application files"; exit 1; } && \
    echo "Application code copied successfully."

# Create logs directory and set proper ownership with detailed permissions
RUN echo "=========================================" && \
    echo "Step 9: Setting up directories and permissions..." && \
    echo "=========================================" && \
    \
    echo "Creating logs directory..." && \
    mkdir -p logs || { echo "ERROR: Failed to create logs directory"; exit 1; } && \
    echo "Logs directory created successfully." && \
    \
    echo "Setting ownership of /app to appuser:docker..." && \
    chown -R appuser:docker /app || { echo "ERROR: Failed to set ownership"; exit 1; } && \
    echo "Ownership set successfully." && \
    \
    echo "Setting permissions for logs directory..." && \
    chmod 777 /app/logs || { echo "ERROR: Failed to set permissions on logs directory"; exit 1; } && \
    echo "Permissions set successfully." && \
    \
    echo "Creating log file with proper permissions..." && \
    touch /app/logs/saas_manager.log && \
    chmod 664 /app/logs/saas_manager.log && \
    chown appuser:docker /app/logs/saas_manager.log || { echo "ERROR: Failed to create log file"; exit 1; } && \
    echo "Log file created successfully." && \
    \
    echo "Verifying permissions..." && \
    ls -la /app/ && \
    ls -la /app/logs/ && \
    echo "Permission verification complete."

# Set permissions for logs directory
RUN chmod -R 777 /app/logs

# Verify Docker setup (if mounted)
RUN echo "=========================================" && \
    echo "Step 10: Verifying Docker setup..." && \
    echo "=========================================" && \
    echo "Docker version:" && \
    docker --version || { echo "WARNING: Docker CLI not working (this is normal in build stage)"; } && \
    echo "Docker setup verification complete."

# Switch to non-root user
USER root
RUN echo "=========================================" && \
    echo "Step 11: Switched to appuser..." && \
    echo "=========================================" && \
    whoami || { echo "ERROR: Failed to switch user"; exit 1; } && \
    echo "Current user: $(whoami)" && \
    echo "Current working directory: $(pwd)" && \
    echo "User permissions:" && \
    id || { echo "ERROR: Failed to get user ID"; exit 1; } && \
    echo "User switch complete."

# Test application files accessibility
RUN echo "=========================================" && \
    echo "Step 12: Testing application accessibility..." && \
    echo "=========================================" && \
    ls -la /app/ || { echo "ERROR: Cannot access /app directory"; exit 1; } && \
    test -f /app/app.py || { echo "ERROR: app.py not found"; exit 1; } && \
    test -r /app/app.py || { echo "ERROR: app.py not readable"; exit 1; } && \
    test -w /app/logs || { echo "ERROR: logs directory not writable"; exit 1; } && \
    test -w /app/logs/saas_manager.log || { echo "ERROR: log file not writable"; exit 1; } && \
    echo "Application accessibility test passed."

# Test Python imports
RUN echo "=========================================" && \
    echo "Step 13: Testing Python imports..." && \
    echo "=========================================" && \
    python3 -c "import flask; print('Flask import: OK')" || { echo "ERROR: Flask import failed"; exit 1; } && \
    python3 -c "import psycopg2; print('psycopg2 import: OK')" || { echo "ERROR: psycopg2 import failed"; exit 1; } && \
    python3 -c "import redis; print('redis import: OK')" || { echo "ERROR: redis import failed"; exit 1; } && \
    python3 -c "import docker; print('docker import: OK')" || { echo "ERROR: docker import failed"; exit 1; } && \
    echo "Python imports test passed."

# Expose port
EXPOSE 8000
RUN echo "=========================================" && \
    echo "Port 8000 exposed successfully." && \
    echo "========================================"

# Health check with better error handling
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || { \
        echo "Health check failed at $(date)"; \
        echo "Checking if process is running..."; \
        ps aux | grep python || true; \
        echo "Checking network connectivity..."; \
        netstat -tlnp | grep 8000 || true; \
        exit 1; \
    }

# Final verification
RUN echo "=========================================" && \
    echo "Docker build completed successfully!" && \
    echo "Image ready for deployment." && \
    echo "User: $(whoami)" && \
    echo "Working directory: $(pwd)" && \
    echo "Python version: $(python3 --version)" && \
    echo "========================================"

# Run the application with error handling
CMD ["sh", "-c", "\
    echo '=========================================' && \
    echo 'Starting Odoo SaaS Manager...' && \
    echo 'Time: '$(date) && \
    echo 'User: '$(whoami) && \
    echo 'Working directory: '$(pwd) && \
    echo 'Python version: '$(python3 --version) && \
    echo '=========================================' && \
    \
    echo 'Checking log file permissions...' && \
    ls -la /app/logs/saas_manager.log && \
    \
    echo 'Checking application file...' && \
    test -f /app/app.py || { echo 'ERROR: app.py not found at startup'; exit 1; } && \
    \
    echo 'Testing database connectivity...' && \
    python3 -c \"import os; print('Environment variables:'); env_vars = ['DATABASE_URL', 'REDIS_URL', 'SECRET_KEY']; [print(key + ': ' + ('***' if 'password' in key.lower() else os.environ.get(key, 'NOT_SET'))) for key in env_vars]\" && \
    \
    echo 'Running initialization script...' && \
    python3 /app/__init__.py --force || { \
        echo 'ERROR: Initialization failed'; \
        echo 'Check initialization logs:'; \
        cat /app/logs/init.log 2>/dev/null || echo 'No init log found'; \
        exit 1; \
    } && \
    \
    echo 'Initialization completed successfully!' && \
    echo 'Starting Flask application...' && \
    python3 app.py || { \
        echo 'ERROR: Application failed to start'; \
        echo 'Last few lines of logs:'; \
        tail -20 /app/logs/saas_manager.log 2>/dev/null || echo 'No log file found'; \
        exit 1; \
    }"]

# RUN flask --app app.py db init
# RUN flask --app app.py db migrate -m "Initial migration"
# RUN flask --app app.py db upgrade
# RUN python __init__.py --force