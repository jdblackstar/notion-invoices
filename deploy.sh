#!/bin/bash

# Colors for better readability
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}Deploying Notion-Invoices services...${NC}"

# Create logs directory
mkdir -p logs

# Set directory variables
HOME_DIR="$HOME"
PROJECT_DIR="$(pwd)"

# Part 1: Deploy FastAPI Service
echo -e "${BLUE}1. Deploying Notion-Invoices service...${NC}"

# Unload existing service if it exists
launchctl bootout gui/$UID ~/Library/LaunchAgents/com.user.notion-invoices.plist 2>/dev/null || true

# Generate plist from template
echo -e "   Generating plist from template..."
sed -e "s|{{HOME_DIR}}|$HOME_DIR|g" \
    -e "s|{{PROJECT_DIR}}|$PROJECT_DIR|g" \
    com.user.notion-invoices.plist.template > com.user.notion-invoices.plist

# Copy the plist file to LaunchAgents directory
cp com.user.notion-invoices.plist ~/Library/LaunchAgents/

# Fix permissions
chmod 644 ~/Library/LaunchAgents/com.user.notion-invoices.plist

# Load the service
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.user.notion-invoices.plist

if [ $? -eq 0 ]; then
    echo -e "${GREEN}   FastAPI application started successfully!${NC}"
else
    echo -e "${RED}   Failed to start FastAPI application${NC}"
    exit 1
fi

# Part 2: Deploy Cloudflared (if needed)
echo -e "${BLUE}2. Checking Cloudflare Tunnel...${NC}"

# Check if cloudflared is installed
if ! command -v cloudflared &> /dev/null; then
    echo -e "${BLUE}   Cloudflared not found. Installing...${NC}"
    brew install cloudflared
    
    # Prompt for tunnel setup
    read -p "   Do you want to set up a new Cloudflare Tunnel? (y/n): " setup_tunnel
    if [[ $setup_tunnel == "y" ]]; then
        # Authenticate
        echo -e "${BLUE}   Please authenticate with Cloudflare in your browser...${NC}"
        cloudflared tunnel login
        
        # Create a tunnel
        echo -e "${BLUE}   Creating a new tunnel...${NC}"
        cloudflared tunnel create notion-invoices
        
        # Get tunnel ID
        TUNNEL_ID=$(cloudflared tunnel list | grep notion-invoices | awk '{print $1}')
        echo -e "${GREEN}   Tunnel created with ID: $TUNNEL_ID${NC}"
        
        # Create config file
        mkdir -p ~/.cloudflared
        cat > ~/.cloudflared/config.yml << EOF
tunnel: $TUNNEL_ID
credentials-file: $HOME_DIR/.cloudflared/${TUNNEL_ID}.json
ingress:
  - hostname: notion-invoices.yourdomain.com
    service: http://localhost:8080
  - service: http_status:404
EOF
        echo -e "${BLUE}   Update the hostname in ~/.cloudflared/config.yml with your actual domain${NC}"
        echo -e "${BLUE}   Then, create a CNAME record for notion-invoices.yourdomain.com pointing to ${TUNNEL_ID}.cfargotunnel.com${NC}"
    fi
fi

# Generate cloudflared plist from template if it exists
if [ -f "com.user.cloudflared.plist.template" ]; then
    echo -e "${BLUE}   Deploying Cloudflared service...${NC}"
    
    # Unload existing service if it exists
    launchctl bootout gui/$UID ~/Library/LaunchAgents/com.user.cloudflared.plist 2>/dev/null || true
    
    # Generate plist from template
    sed -e "s|{{HOME_DIR}}|$HOME_DIR|g" \
        -e "s|{{PROJECT_DIR}}|$PROJECT_DIR|g" \
        com.user.cloudflared.plist.template > com.user.cloudflared.plist
    
    # Copy the plist file to LaunchAgents directory
    cp com.user.cloudflared.plist ~/Library/LaunchAgents/
    
    # Fix permissions
    chmod 644 ~/Library/LaunchAgents/com.user.cloudflared.plist
    
    # Load the service
    launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.user.cloudflared.plist
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}   Cloudflared service started successfully!${NC}"
    else
        echo -e "${RED}   Failed to start Cloudflared service${NC}"
    fi
fi

# Display service status
echo -e "${BLUE}3. Service Status:${NC}"
echo -e "${BLUE}   FastAPI Process:${NC} $(launchctl list | grep notion-invoices)"

if command -v cloudflared &> /dev/null; then
    echo -e "${BLUE}   Cloudflare Tunnel Process:${NC} $(ps -ef | grep cloudflared | grep -v grep | head -1)"
    echo -e "${BLUE}   Public URL:${NC} https://notion-invoices.yourdomain.com/health"
    echo -e "${BLUE}   Webhook URL:${NC} https://notion-invoices.yourdomain.com/api/webhooks/stripe"
fi

echo -e "${BLUE}   Internal URL:${NC} http://localhost:8080/health"

echo -e "${GREEN}Deployment complete!${NC}"
echo -e "${BLUE}View logs with:${NC}"
echo "  tail -f logs/notion-invoices.log       # FastAPI logs"

if command -v cloudflared &> /dev/null; then
    echo "  tail -f logs/cloudflared.log           # Cloudflare Tunnel logs"
fi

echo -e "${BLUE}Useful commands:${NC}"
echo "  ./status.sh                           # Check sync status"
echo "  ./restart.sh                          # Restart services" 