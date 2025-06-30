#!/bin/bash

# Colors for better readability
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}Setting up Notion-Invoices for system restart...${NC}"

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo -e "${RED}Please don't run this script as root. Run as the user who will manage the service.${NC}"
    exit 1
fi

# Get current directory
CURRENT_DIR=$(pwd)
PROJECT_DIR=$(realpath "$CURRENT_DIR/..")

echo -e "${BLUE}Project directory: $PROJECT_DIR${NC}"

# Check if we're in the system-restart directory
if [ ! -f "notion-invoices.service" ]; then
    echo -e "${RED}Please run this script from the system-restart directory${NC}"
    exit 1
fi

# Check if docker-compose.yml exists in parent directory
if [ ! -f "$PROJECT_DIR/docker-compose.yml" ]; then
    echo -e "${RED}docker-compose.yml not found in $PROJECT_DIR${NC}"
    echo -e "${RED}Make sure you're running this from the system-restart subdirectory${NC}"
    exit 1
fi

# Create the systemd service file
echo -e "${BLUE}Creating systemd service file...${NC}"
SERVICE_FILE="/tmp/notion-invoices.service"

cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Notion-Invoices Docker Service
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$PROJECT_DIR
ExecStart=/usr/bin/docker-compose up -d
ExecStop=/usr/bin/docker-compose down
TimeoutStartSec=0
User=$USER
Group=$USER

[Install]
WantedBy=multi-user.target
EOF

# Install the service file
echo -e "${BLUE}Installing systemd service...${NC}"
sudo cp "$SERVICE_FILE" /etc/systemd/system/notion-invoices.service
sudo systemctl daemon-reload

# Enable the service
echo -e "${BLUE}Enabling service for auto-start...${NC}"
sudo systemctl enable notion-invoices.service

echo -e "${GREEN}System restart setup complete!${NC}"
echo ""
echo -e "${BLUE}Service commands:${NC}"
echo "  sudo systemctl start notion-invoices    # Start the service"
echo "  sudo systemctl stop notion-invoices     # Stop the service"
echo "  sudo systemctl restart notion-invoices  # Restart the service"
echo "  sudo systemctl status notion-invoices   # Check service status"
echo "  sudo systemctl disable notion-invoices  # Disable auto-start"
echo ""
echo -e "${BLUE}The service will now automatically start on system boot.${NC}"
echo -e "${YELLOW}Note: Make sure Docker is installed and configured to start on boot.${NC}"

# Clean up
rm "$SERVICE_FILE"