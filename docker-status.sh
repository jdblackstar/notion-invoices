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
  echo -e "${BLUE}Notion-Invoices Docker Status Utility${NC}"
  echo ""
  echo "Usage: ./docker-status.sh [options]"
  echo ""
  echo "Options:"
  echo "  -r, --restart    Restart services after checking status"
  echo "  -h, --help       Show this help message"
  exit 0
fi

# Check if Docker is running
if ! docker info >/dev/null 2>&1; then
    echo -e "${RED}Docker is not running! Please start Docker first.${NC}"
    exit 1
fi

# If restart flag is set, perform restart first
if [ "$RESTART" = true ]; then
  echo -e "${YELLOW}Restarting Notion-Invoices Docker services...${NC}"
  
  # Stop services
  echo -e "${BLUE}Stopping services...${NC}"
  docker-compose down
  
  # Start services
  echo -e "${BLUE}Starting services...${NC}"
  if [ -f cloudflared/config.yml ]; then
    docker-compose --profile tunnel up -d
  else
    docker-compose up -d notion-invoices
  fi
  
  if [ $? -eq 0 ]; then
    echo -e "${GREEN}Services restarted successfully!${NC}"
  else
    echo -e "${RED}Failed to restart services${NC}"
    exit 1
  fi
  
  # Wait for services to start
  sleep 5
  echo ""
fi

# Check service status
echo -e "${BLUE}Notion-Invoices Docker Status Check${NC}"

# 1. Container status
echo -e "${BLUE}1. Container Status:${NC}"

# Check notion-invoices container
NOTION_CONTAINER=$(docker ps --filter "name=notion-invoices" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | tail -n +2)
if [ -n "$NOTION_CONTAINER" ]; then
  echo -e "${GREEN}   ✓ Notion-invoices container: $NOTION_CONTAINER${NC}"
else
  echo -e "${RED}   ✗ Notion-invoices container is not running!${NC}"
  # Check if container exists but is stopped
  STOPPED_CONTAINER=$(docker ps -a --filter "name=notion-invoices" --filter "status=exited" --format "{{.Names}}")
  if [ -n "$STOPPED_CONTAINER" ]; then
    echo -e "${YELLOW}     Container exists but is stopped. Check logs with: docker-compose logs notion-invoices${NC}"
  fi
fi

# Check cloudflared container
CLOUDFLARED_CONTAINER=$(docker ps --filter "name=cloudflared-tunnel" --format "table {{.Names}}\t{{.Status}}" | tail -n +2)
if [ -n "$CLOUDFLARED_CONTAINER" ]; then
  echo -e "${GREEN}   ✓ Cloudflare tunnel container: $CLOUDFLARED_CONTAINER${NC}"
elif [ -f cloudflared/config.yml ]; then
  echo -e "${RED}   ✗ Cloudflare tunnel container is not running (but config exists)!${NC}"
else
  echo -e "${YELLOW}   - Cloudflare tunnel not configured${NC}"
fi

# 2. Health endpoint check
echo -e "${BLUE}2. Health Check:${NC}"
HEALTH_CHECK=$(curl -s http://localhost:8080/health 2>/dev/null || echo "failed")
if [ "$HEALTH_CHECK" == '{"status":"ok"}' ]; then
  echo -e "${GREEN}   ✓ Health endpoint is responding correctly${NC}"
else
  echo -e "${RED}   ✗ Health endpoint is not responding: $HEALTH_CHECK${NC}"
fi

# 3. Container resource usage
echo -e "${BLUE}3. Resource Usage:${NC}"
if docker ps --filter "name=notion-invoices" --format "{{.Names}}" | grep -q notion-invoices; then
  STATS=$(docker stats notion-invoices --no-stream --format "table {{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}" | tail -n +2)
  echo -e "${GREEN}   CPU/Memory usage: $STATS${NC}"
else
  echo -e "${RED}   Cannot get resource usage - container not running${NC}"
fi

# 4. Recent sync logs
echo -e "${BLUE}4. Recent Sync Activity:${NC}"
if docker ps --filter "name=notion-invoices" --format "{{.Names}}" | grep -q notion-invoices; then
  echo -e "${BLUE}   Last 10 sync operations:${NC}"
  docker logs notion-invoices 2>/dev/null | grep -a "sync completed\|BILLING PERIOD SYNC: Completed\|Immediate startup sync completed" | tail -10
  
  if [ $? -ne 0 ] || [ -z "$(docker logs notion-invoices 2>/dev/null | grep -a "sync completed\|BILLING PERIOD SYNC: Completed\|Immediate startup sync completed")" ]; then
    echo -e "${YELLOW}   No sync activity found in recent logs${NC}"
  fi
else
  echo -e "${RED}   Container not running - cannot check logs${NC}"
fi

# 5. Recent billing period syncs
echo -e "${BLUE}5. Recent Billing Period Syncs:${NC}"
if docker ps --filter "name=notion-invoices" --format "{{.Names}}" | grep -q notion-invoices; then
  echo -e "${BLUE}   Last 5 billing period updates:${NC}"
  BILLING_LOGS=$(docker logs notion-invoices 2>/dev/null | grep -a "Syncing billing period for Notion invoice" | tail -5)
  if [ -n "$BILLING_LOGS" ]; then
    echo "$BILLING_LOGS"
  else
    echo -e "${YELLOW}   No billing period sync activity found${NC}"
  fi
else
  echo -e "${RED}   Container not running - cannot check logs${NC}"
fi

# 6. Recent errors
echo -e "${BLUE}6. Any Recent Errors:${NC}"
if docker ps --filter "name=notion-invoices" --format "{{.Names}}" | grep -q notion-invoices; then
  ERROR_LOGS=$(docker logs notion-invoices 2>&1 | grep -i "error" | tail -5)
  if [ -n "$ERROR_LOGS" ]; then
    echo -e "${RED}   Recent errors found:${NC}"
    echo "$ERROR_LOGS"
  else
    echo -e "${GREEN}   ✓ No recent errors found${NC}"
  fi
else
  echo -e "${RED}   Container not running - cannot check for errors${NC}"
fi

# 7. Docker compose status
echo -e "${BLUE}7. Docker Compose Status:${NC}"
if [ -f docker-compose.yml ]; then
  COMPOSE_STATUS=$(docker-compose ps 2>/dev/null)
  if [ $? -eq 0 ]; then
    echo "$COMPOSE_STATUS"
  else
    echo -e "${RED}   Error getting docker-compose status${NC}"
  fi
else
  echo -e "${RED}   docker-compose.yml not found${NC}"
fi

echo ""
echo -e "${GREEN}Status check complete!${NC}"
echo ""
echo -e "${BLUE}Useful commands:${NC}"
echo "  ./docker-status.sh --restart          # Restart all services"
echo "  docker-compose logs -f notion-invoices # View live logs"
echo "  docker-compose logs -f cloudflared-tunnel # View tunnel logs"
echo "  docker-compose down                   # Stop all services"
echo "  docker-compose up -d                  # Start services"
echo "  docker exec -it notion-invoices bash  # Enter container shell"