#!/bin/bash

# Enhanced Disaster Recovery Setup Script
# Sets up Google Drive integration and Backup Panel

set -euo pipefail

# Load configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/config"
source "$CONFIG_DIR/dr-config.env"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${RED}[ERROR]${NC} $1"
}

# Check if running on Windows
is_windows() {
    [[ "$OSTYPE" == "cygwin" || "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]
}

# Install Python dependencies
install_python_dependencies() {
    log "Installing Python dependencies for Google Drive integration..."
    
    # Check if pip is available
    if ! command -v pip3 &> /dev/null && ! command -v pip &> /dev/null; then
        log_error "pip not found. Please install Python and pip first."
        return 1
    fi
    
    local pip_cmd="pip3"
    if ! command -v pip3 &> /dev/null; then
        pip_cmd="pip"
    fi
    
    # Install required packages
    local packages=(
        "google-auth>=2.23.0"
        "google-auth-oauthlib>=1.1.0"
        "google-auth-httplib2>=0.1.0"
        "google-api-python-client>=2.103.0"
        "tenacity>=8.2.0"
        "flask>=2.3.0"
        "flask-login>=0.6.0"
    )
    
    for package in "${packages[@]}"; do
        log "Installing $package..."
        $pip_cmd install "$package" || {
            log_error "Failed to install $package"
            return 1
        }
    done
    
    log_success "Python dependencies installed successfully"
}

# Setup Google Drive API credentials
setup_google_drive_credentials() {
    log "Setting up Google Drive API credentials..."
    
    # Check if credentials are already configured
    if [ -n "$GDRIVE_CLIENT_ID" ] && [ -n "$GDRIVE_CLIENT_SECRET" ]; then
        log "Google Drive credentials found in configuration"
        return 0
    fi
    
    log_warning "Google Drive credentials not configured"
    echo
    echo "To configure Google Drive integration:"
    echo "1. Go to https://console.cloud.google.com/"
    echo "2. Create a new project or select existing project"
    echo "3. Enable the Google Drive API"
    echo "4. Create OAuth2 credentials (Desktop application)"
    echo "5. Download the credentials JSON file"
    echo "6. Update the configuration file with Client ID and Secret"
    echo
    
    read -p "Do you want to configure Google Drive credentials now? (y/N): " configure_now
    if [[ "$configure_now" =~ ^[Yy]$ ]]; then
        echo
        read -p "Enter Google Drive Client ID: " client_id
        read -p "Enter Google Drive Client Secret: " client_secret
        
        if [ -n "$client_id" ] && [ -n "$client_secret" ]; then
            # Update configuration file
            sed -i.bak "s/GDRIVE_CLIENT_ID=\"\"/GDRIVE_CLIENT_ID=\"$client_id\"/" "$CONFIG_DIR/dr-config.env"
            sed -i.bak "s/GDRIVE_CLIENT_SECRET=\"\"/GDRIVE_CLIENT_SECRET=\"$client_secret\"/" "$CONFIG_DIR/dr-config.env"
            
            log_success "Google Drive credentials updated in configuration"
        else
            log_warning "Credentials not provided, Google Drive integration will not be available"
        fi
    else
        log_warning "Skipping Google Drive credential configuration"
    fi
}

# Test Google Drive integration
test_google_drive() {
    log "Testing Google Drive integration..."
    
    local gdrive_script="$SCRIPT_DIR/scripts/gdrive-integration.py"
    
    if [ ! -f "$gdrive_script" ]; then
        log_error "Google Drive integration script not found"
        return 1
    fi
    
    # Test authentication
    if python3 "$gdrive_script" --config "$CONFIG_DIR/dr-config.env" --authenticate; then
        log_success "Google Drive authentication successful"
        
        # Test storage usage
        if python3 "$gdrive_script" --config "$CONFIG_DIR/dr-config.env" --storage; then
            log_success "Google Drive storage access confirmed"
        else
            log_warning "Google Drive storage access test failed"
        fi
    else
        log_error "Google Drive authentication failed"
        return 1
    fi
}

# Setup backup panel
setup_backup_panel() {
    log "Setting up Backup Panel..."
    
    local panel_dir="$SCRIPT_DIR/backup_panel"
    
    # Check if backup panel directory exists
    if [ ! -d "$panel_dir" ]; then
        log_error "Backup panel directory not found: $panel_dir"
        return 1
    fi
    
    # Install backup panel dependencies
    if [ -f "$panel_dir/requirements.txt" ]; then
        log "Installing backup panel dependencies..."
        pip3 install -r "$panel_dir/requirements.txt" || {
            log_error "Failed to install backup panel dependencies"
            return 1
        }
    fi
    
    # Create database if it doesn't exist
    log "Initializing backup panel database..."
    cd "$panel_dir"
    python3 -c "
from app import DatabaseManager
db = DatabaseManager()
print('Database initialized successfully')
" || {
        log_error "Failed to initialize backup panel database"
        return 1
    }
    
    log_success "Backup panel setup completed"
}

# Update Docker Compose configuration
update_docker_compose() {
    log "Checking Docker Compose configuration..."
    
    local docker_compose_file="$SCRIPT_DIR/../docker-compose.yml"
    
    if [ ! -f "$docker_compose_file" ]; then
        log_error "Docker Compose file not found: $docker_compose_file"
        return 1
    fi
    
    # Check if backup_panel service is already defined
    if grep -q "backup_panel:" "$docker_compose_file"; then
        log "Backup panel service already configured in Docker Compose"
    else
        log_warning "Backup panel service not found in Docker Compose"
        log "Please add the backup panel service to your docker-compose.yml file"
    fi
}

# Test enhanced backup system
test_enhanced_backup() {
    log "Testing enhanced backup system..."
    
    # Test configuration
    log "Validating configuration..."
    if [ ! -f "$CONFIG_DIR/dr-config.env" ]; then
        log_error "Configuration file not found"
        return 1
    fi
    
    # Test backup script
    local backup_script="$SCRIPT_DIR/scripts/enhanced-backup.sh"
    if [ ! -f "$backup_script" ]; then
        log_error "Enhanced backup script not found"
        return 1
    fi
    
    # Test script syntax
    if bash -n "$backup_script"; then
        log_success "Backup script syntax is valid"
    else
        log_error "Backup script has syntax errors"
        return 1
    fi
    
    # Test Google Drive integration if configured
    if [ -n "$GDRIVE_CLIENT_ID" ] && [ -n "$GDRIVE_CLIENT_SECRET" ]; then
        test_google_drive
    else
        log_warning "Google Drive not configured, skipping integration test"
    fi
}

# Create startup script for backup panel
create_startup_script() {
    log "Creating startup script for backup panel..."
    
    local startup_script="$SCRIPT_DIR/start-backup-panel.sh"
    
    cat > "$startup_script" << 'EOF'
#!/bin/bash

# Backup Panel Startup Script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PANEL_DIR="$SCRIPT_DIR/backup_panel"

# Change to panel directory
cd "$PANEL_DIR"

# Set environment variables
export FLASK_APP=app.py
export FLASK_ENV=production
export PYTHONPATH="$SCRIPT_DIR/scripts"

# Start the backup panel
echo "Starting Backup Panel..."
echo "Access the panel at: http://localhost:5000"
echo "Default login: admin / admin"
echo ""

python3 app.py
EOF
    
    chmod +x "$startup_script"
    log_success "Startup script created: $startup_script"
}

# Show post-installation instructions
show_instructions() {
    echo
    echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║                 Enhanced DR Setup Complete!                 ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo
    echo -e "${BLUE}What's been set up:${NC}"
    echo "✅ Google Drive integration for backup storage"
    echo "✅ Enhanced backup scripts with multi-destination support"
    echo "✅ Web-based Backup Panel for easy management"
    echo "✅ Updated configuration for multiple cloud providers"
    echo
    echo -e "${BLUE}Next steps:${NC}"
    echo
    echo -e "${YELLOW}1. Configure Google Drive (if not already done):${NC}"
    echo "   - Visit: https://console.cloud.google.com/"
    echo "   - Enable Google Drive API"
    echo "   - Create OAuth2 credentials"
    echo "   - Update dr-config.env with Client ID and Secret"
    echo
    echo -e "${YELLOW}2. Start the Backup Panel:${NC}"
    if is_windows; then
        echo "   bash $SCRIPT_DIR/start-backup-panel.sh"
    else
        echo "   ./start-backup-panel.sh"
    fi
    echo "   Or with Docker: docker-compose up backup_panel"
    echo
    echo -e "${YELLOW}3. Access the Backup Panel:${NC}"
    echo "   - URL: http://localhost:5000"
    echo "   - Default login: admin / admin"
    echo "   - Change password in Settings after first login"
    echo
    echo -e "${YELLOW}4. Test the enhanced backup system:${NC}"
    echo "   ./scripts/enhanced-backup.sh"
    echo
    echo -e "${YELLOW}5. Configure backup destinations:${NC}"
    echo "   - AWS S3: Update AWS credentials in dr-config.env"
    echo "   - Google Drive: Complete OAuth flow in Backup Panel"
    echo "   - Choose destinations in Backup Panel Settings"
    echo
    echo -e "${BLUE}Features available:${NC}"
    echo "• Multiple backup destinations (AWS S3 + Google Drive)"
    echo "• Web-based management interface"
    echo "• Real-time backup monitoring"
    echo "• Storage usage tracking"
    echo "• Manual backup triggering"
    echo "• Backup validation and testing"
    echo "• Automated scheduling and alerts"
    echo
    echo -e "${GREEN}For documentation, see:${NC}"
    echo "• README.md - Complete system overview"
    echo "• INSTALLATION.md - Detailed setup instructions"
    echo "• EMERGENCY-RUNBOOK.md - Crisis response procedures"
    echo
}

# Main setup function
main() {
    echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║             Enhanced Disaster Recovery Setup                ║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo
    
    log "Starting enhanced disaster recovery setup..."
    
    # Check prerequisites
    log "Checking prerequisites..."
    
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 is required but not installed"
        exit 1
    fi
    
    if ! command -v docker &> /dev/null; then
        log_warning "Docker not found - some features may not be available"
    fi
    
    # Install dependencies
    install_python_dependencies
    
    # Setup Google Drive
    setup_google_drive_credentials
    
    # Setup backup panel
    setup_backup_panel
    
    # Update Docker configuration
    update_docker_compose
    
    # Test system
    test_enhanced_backup
    
    # Create startup script
    create_startup_script
    
    # Show instructions
    show_instructions
    
    log_success "Enhanced disaster recovery setup completed successfully!"
}

# Check if running with appropriate permissions
if [ "$EUID" -eq 0 ]; then
    log_warning "Running as root. Consider using a dedicated user."
fi

# Run main function
main "$@"
