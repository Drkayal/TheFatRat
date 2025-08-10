#!/bin/bash

# TheFatRat Phase 1 Setup Script
# Advanced APK Upload and Processing Infrastructure

echo "🚀 Setting up TheFatRat Phase 1 - APK Upload Infrastructure"
echo "================================================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[⚠]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

print_info() {
    echo -e "${BLUE}[ℹ]${NC} $1"
}

# Check if running as root
if [[ $EUID -eq 0 ]]; then
    print_error "This script should not be run as root for security reasons"
    exit 1
fi

# Update system packages
print_info "Updating system packages..."
sudo apt-get update -qq

# Install system dependencies
print_info "Installing system dependencies..."
sudo apt-get install -y \
    python3-dev \
    python3-pip \
    python3-venv \
    libmagic1 \
    libmagic-dev \
    openjdk-11-jdk \
    sqlite3 \
    curl \
    wget \
    unzip \
    build-essential \
    libssl-dev \
    libffi-dev

# Install Python dependencies for bot
print_info "Installing Python dependencies for Telegram bot..."
cd /workspace/bot
pip3 install -r requirements.txt

# Install Python dependencies for orchestrator  
print_info "Installing Python dependencies for orchestrator..."
cd /workspace/orchestrator
pip3 install fastapi uvicorn sqlite3

# Create necessary directories
print_info "Creating directory structure..."
mkdir -p /workspace/uploads
mkdir -p /workspace/temp
mkdir -p /workspace/logs
mkdir -p /workspace/tasks

# Set proper permissions
print_info "Setting directory permissions..."
chmod 755 /workspace/uploads
chmod 755 /workspace/temp
chmod 755 /workspace/logs
chmod 755 /workspace/tasks

# Initialize database
print_info "Initializing database..."
cd /workspace/orchestrator
python3 -c "from database import db_manager; print('Database initialized successfully')"

# Create environment file template
print_info "Creating environment configuration template..."
cat > /workspace/.env.template << 'EOF'
# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_OWNER_ID=your_telegram_user_id

# Orchestrator Configuration
ORCH_URL=http://127.0.0.1:8000
ORCH_USE_DOCKER=false

# File Upload Configuration
MAX_FILE_SIZE=104857600
UPLOAD_CLEANUP_HOURS=24

# Security Configuration
ENABLE_AUDIT=true
LOG_LEVEL=INFO
EOF

# Check if .env exists, if not copy template
if [ ! -f /workspace/.env ]; then
    print_warning "Creating .env file from template - please configure it!"
    cp /workspace/.env.template /workspace/.env
fi

# Create systemd service for orchestrator
print_info "Creating systemd service for orchestrator..."
sudo tee /etc/systemd/system/fatrat-orchestrator.service > /dev/null << 'EOF'
[Unit]
Description=TheFatRat Orchestrator Service
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/workspace/orchestrator
Environment=PATH=/usr/local/bin:/usr/bin:/bin
ExecStart=/usr/bin/python3 -m uvicorn app:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Create systemd service for bot
print_info "Creating systemd service for Telegram bot..."
sudo tee /etc/systemd/system/fatrat-bot.service > /dev/null << 'EOF'
[Unit]
Description=TheFatRat Telegram Bot Service
After=network.target fatrat-orchestrator.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/workspace/bot
Environment=PATH=/usr/local/bin:/usr/bin:/bin
ExecStart=/usr/bin/python3 bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
sudo systemctl daemon-reload

# Create startup script
print_info "Creating startup script..."
cat > /workspace/start_services.sh << 'EOF'
#!/bin/bash
echo "Starting TheFatRat Phase 1 Services..."

# Start orchestrator
echo "Starting orchestrator..."
sudo systemctl start fatrat-orchestrator
sudo systemctl enable fatrat-orchestrator

# Wait for orchestrator to start
sleep 5

# Start bot
echo "Starting Telegram bot..."
sudo systemctl start fatrat-bot
sudo systemctl enable fatrat-bot

echo "Services started successfully!"
echo "Check status with: sudo systemctl status fatrat-orchestrator fatrat-bot"
EOF

chmod +x /workspace/start_services.sh

# Create status check script
print_info "Creating status check script..."
cat > /workspace/check_status.sh << 'EOF'
#!/bin/bash
echo "TheFatRat Phase 1 Status Check"
echo "============================="

echo -e "\n🔧 System Services:"
sudo systemctl status fatrat-orchestrator --no-pager -l
sudo systemctl status fatrat-bot --no-pager -l

echo -e "\n📊 Database Statistics:"
cd /workspace/orchestrator
python3 -c "
from database import db_manager
import json
stats = db_manager.get_statistics()
print(json.dumps(stats, indent=2))
"

echo -e "\n📁 Directory Status:"
ls -la /workspace/uploads/
ls -la /workspace/temp/
ls -la /workspace/logs/

echo -e "\n🌐 API Health Check:"
curl -s http://127.0.0.1:8000/health || echo "API not responding"

EOF

chmod +x /workspace/check_status.sh

# Create cleanup script
print_info "Creating cleanup script..."
cat > /workspace/cleanup.sh << 'EOF'
#!/bin/bash
echo "Cleaning up TheFatRat temporary files..."

# Clean old uploaded files
find /workspace/uploads -type f -mtime +1 -delete
find /workspace/temp -type f -mtime +1 -delete

# Clean database records
cd /workspace/orchestrator
python3 -c "
from database import db_manager
db_manager.cleanup_old_records(days=7)
print('Database cleanup completed')
"

echo "Cleanup completed"
EOF

chmod +x /workspace/cleanup.sh

# Create cron job for cleanup
print_info "Setting up automatic cleanup..."
(crontab -l 2>/dev/null; echo "0 2 * * * /workspace/cleanup.sh") | crontab -

# Test installation
print_info "Testing installation..."

# Test database
cd /workspace/orchestrator
if python3 -c "from database import db_manager; db_manager.get_statistics()" &>/dev/null; then
    print_status "Database system working correctly"
else
    print_error "Database system test failed"
fi

# Test orchestrator import
if python3 -c "from app import app" &>/dev/null; then
    print_status "Orchestrator system working correctly"
else
    print_error "Orchestrator system test failed"
fi

# Test bot import
cd /workspace/bot
if python3 -c "from bot import APKValidator, SecureFileManager" &>/dev/null; then
    print_status "Bot system working correctly"
else
    print_error "Bot system test failed"
fi

echo ""
print_status "Phase 1 installation completed successfully!"
echo ""
print_info "Next steps:"
echo "1. Configure your .env file with Telegram bot token and owner ID"
echo "2. Run: /workspace/start_services.sh"
echo "3. Check status: /workspace/check_status.sh"
echo "4. Test the new APK upload feature in Telegram"
echo ""
print_warning "Remember to configure the .env file before starting services!"
echo ""
print_info "Phase 1 Features Implemented:"
echo "✅ Advanced APK file upload via Telegram"
echo "✅ Comprehensive file validation and analysis"
echo "✅ Secure file storage with progress tracking"
echo "✅ Database-backed audit trail system"
echo "✅ Async task processing pipeline"
echo "✅ Advanced error handling and logging"
echo "✅ Automated cleanup and maintenance"
echo ""
echo "🎯 Ready for Phase 2: Advanced APK Modification Engine"