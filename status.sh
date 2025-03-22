#!/bin/bash

# Colors for better readability
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Parse command-line arguments
RESTART=false
SHOW_HELP=false

for arg in "$@"; do
  case $arg in
    -r|--restart)
      RESTART=true
      shift
      ;;
    -h|--help)
      SHOW_HELP=true
      shift
      ;;
    *)
      # Unknown option
      ;;
  esac
done

if [ "$SHOW_HELP" = true ]; then
  echo -e "${BLUE}Notion-Invoices Status Utility${NC}"
  echo ""
  echo "Usage: ./status.sh [options]"
  echo ""
  echo "Options:"
  echo "  -r, --restart    Restart services after checking status"
  echo "  -h, --help       Show this help message"
  exit 0
fi

# If restart flag is set, perform restart first
if [ "$RESTART" = true ]; then
  echo -e "${YELLOW}Restarting Notion-Invoices services...${NC}"
  
  # 1. Restart FastAPI application
  echo -e "${BLUE}1. Restarting FastAPI application...${NC}"
  launchctl bootout gui/$UID ~/Library/LaunchAgents/com.user.notion-invoices.plist 2>/dev/null || true
  sleep 1
  launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.user.notion-invoices.plist
  
  if [ $? -eq 0 ]; then
    echo -e "${GREEN}   FastAPI application restarted successfully!${NC}"
  else
    echo -e "${RED}   Failed to restart FastAPI application${NC}"
    exit 1
  fi
  
  # 2. Restart Cloudflared if it exists
  if [ -f ~/Library/LaunchAgents/com.user.cloudflared.plist ]; then
    echo -e "${BLUE}2. Restarting Cloudflared service...${NC}"
    launchctl bootout gui/$UID ~/Library/LaunchAgents/com.user.cloudflared.plist 2>/dev/null || true
    sleep 1
    launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.user.cloudflared.plist
    
    if [ $? -eq 0 ]; then
      echo -e "${GREEN}   Cloudflared restarted successfully!${NC}"
    else
      echo -e "${RED}   Failed to restart Cloudflared${NC}"
    fi
  fi
  
  echo -e "${GREEN}Restart complete${NC}"
  echo ""
fi

# Check service status
echo -e "${BLUE}Notion-Invoices Status Check${NC}"

# 1. Service status
echo -e "${BLUE}1. Service Status:${NC}"
NOTION_SERVICE=$(launchctl list | grep notion-invoices)
if [ -n "$NOTION_SERVICE" ]; then
  echo -e "${GREEN}   Service is running: $NOTION_SERVICE${NC}"
else
  echo -e "${RED}   Service is not running!${NC}"
fi

# Check Cloudflared if it exists
if [ -f ~/Library/LaunchAgents/com.user.cloudflared.plist ]; then
  CLOUDFLARED_SERVICE=$(launchctl list | grep cloudflared)
  if [ -n "$CLOUDFLARED_SERVICE" ]; then
    echo -e "${GREEN}   Cloudflare Tunnel is running: $CLOUDFLARED_SERVICE${NC}"
  else
    echo -e "${RED}   Cloudflare Tunnel is not running!${NC}"
  fi
fi

# 2. Health endpoint check
echo -e "${BLUE}2. Health Check:${NC}"
HEALTH_CHECK=$(curl -s http://localhost:8080/health)
if [ "$HEALTH_CHECK" == '{"status":"ok"}' ]; then
  echo -e "${GREEN}   Health endpoint is responding correctly${NC}"
else
  echo -e "${RED}   Health endpoint is not responding correctly: $HEALTH_CHECK${NC}"
fi

# 3. Recent sync logs
echo -e "${BLUE}3. Recent Sync Activity:${NC}"
if [ -f logs/notion-invoices.log ]; then
  echo -e "${BLUE}   Last 10 sync operations:${NC}"
  grep -a "sync completed\|BILLING PERIOD SYNC: Completed\|Immediate startup sync completed" logs/notion-invoices.log | tail -10
else
  echo -e "${RED}   No log file found at logs/notion-invoices.log${NC}"
fi

# 4. Recent billing period syncs
echo -e "${BLUE}4. Recent Billing Period Syncs:${NC}"
if [ -f logs/notion-invoices.log ]; then
  echo -e "${BLUE}   Last 5 billing period updates:${NC}"
  grep -a "Syncing billing period for Notion invoice" logs/notion-invoices.log | tail -5
else
  echo -e "${RED}   No log file found at logs/notion-invoices.log${NC}"
fi

# 5. Recent errors
echo -e "${BLUE}5. Any Recent Errors:${NC}"
if [ -f logs/notion-invoices.log ]; then
  ERROR_COUNT=$(grep -a "ERROR" logs/notion-invoices.log | wc -l | tr -d ' ')
  if [ "$ERROR_COUNT" -gt 0 ]; then
    echo -e "${RED}   Found $ERROR_COUNT errors in log file. Last 5:${NC}"
    grep -a "ERROR" logs/notion-invoices.log | tail -5
  else
    echo -e "${GREEN}   No errors found in log file${NC}"
  fi
else
  echo -e "${RED}   No log file found at logs/notion-invoices.log${NC}"
fi

echo -e "${GREEN}Check complete!${NC}"
echo -e "${BLUE}Useful commands:${NC}"
echo "  ./status.sh --restart         # Restart all services"
echo "  tail -f logs/notion-invoices.log   # View live logs" 