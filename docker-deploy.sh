#!/bin/bash

# Colors for better readability
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}Deploying Notion-Invoices with Docker...${NC}"

# Check if Docker is running
if ! docker info >/dev/null 2>&1; then
    echo -e "${RED}Docker is not running! Please start Docker and try again.${NC}"
    exit 1
fi

# Check if .env file exists
if [ ! -f .env ]; then
    echo -e "${YELLOW}Warning: .env file not found. Please create one with your API keys.${NC}"
    echo -e "${BLUE}You can copy .env.example if it exists.${NC}"
fi

# Create necessary directories
echo -e "${BLUE}Creating directories...${NC}"
mkdir -p logs
mkdir -p data
mkdir -p cloudflared

# Parse command line arguments
SETUP_TUNNEL=false
BUILD_ONLY=false
NO_TUNNEL=false

for arg in "$@"; do
    case $arg in
        --setup-tunnel)
            SETUP_TUNNEL=true
            shift
            ;;
        --build-only)
            BUILD_ONLY=true
            shift
            ;;
        --no-tunnel)
            NO_TUNNEL=true
            shift
            ;;
        --help)
            echo -e "${BLUE}Docker Deployment Script for Notion-Invoices${NC}"
            echo ""
            echo "Usage: ./docker-deploy.sh [options]"
            echo ""
            echo "Options:"
            echo "  --setup-tunnel    Set up Cloudflare tunnel configuration"
            echo "  --build-only      Only build the Docker image, don't deploy"
            echo "  --no-tunnel       Deploy without Cloudflare tunnel"
            echo "  --help            Show this help message"
            exit 0
            ;;
    esac
done

# Stop existing containers
echo -e "${BLUE}Stopping existing containers...${NC}"
docker-compose down

# Build the application
echo -e "${BLUE}Building Docker image...${NC}"
docker-compose build notion-invoices

if [ $? -ne 0 ]; then
    echo -e "${RED}Failed to build Docker image${NC}"
    exit 1
fi

if [ "$BUILD_ONLY" = true ]; then
    echo -e "${GREEN}Build completed successfully!${NC}"
    exit 0
fi

# Handle Cloudflare tunnel setup
if [ "$SETUP_TUNNEL" = true ]; then
    echo -e "${BLUE}Setting up Cloudflare tunnel...${NC}"
    
    # Check if cloudflared is available in Docker
    if ! docker run --rm cloudflare/cloudflared:latest version >/dev/null 2>&1; then
        echo -e "${RED}Failed to access cloudflared Docker image${NC}"
        exit 1
    fi
    
    # Create tunnel configuration directory
    mkdir -p cloudflared
    
    echo -e "${BLUE}Please follow these steps to set up your Cloudflare tunnel:${NC}"
    echo ""
    echo "1. Authenticate with Cloudflare:"
    echo "   docker run --rm -v \$(pwd)/cloudflared:/etc/cloudflared cloudflare/cloudflared:latest tunnel login"
    echo ""
    echo "2. Create a tunnel:"
    echo "   docker run --rm -v \$(pwd)/cloudflared:/etc/cloudflared cloudflare/cloudflared:latest tunnel create notion-invoices"
    echo ""
    echo "3. Create a config file at ./cloudflared/config.yml with content like:"
    echo "   tunnel: YOUR_TUNNEL_ID"
    echo "   credentials-file: /etc/cloudflared/YOUR_TUNNEL_ID.json"
    echo "   ingress:"
    echo "     - hostname: notion-invoices.yourdomain.com"
    echo "       service: http://notion-invoices:8080"
    echo "     - service: http_status:404"
    echo ""
    echo "4. Create a DNS record pointing notion-invoices.yourdomain.com to YOUR_TUNNEL_ID.cfargotunnel.com"
    echo ""
    echo "5. Run this script again without --setup-tunnel to deploy with tunnel support"
    exit 0
fi

# Deploy the application
echo -e "${BLUE}Deploying application...${NC}"

if [ "$NO_TUNNEL" = true ] || [ ! -f cloudflared/config.yml ]; then
    echo -e "${BLUE}Deploying without Cloudflare tunnel...${NC}"
    docker-compose up -d notion-invoices
else
    echo -e "${BLUE}Deploying with Cloudflare tunnel...${NC}"
    docker-compose --profile tunnel up -d
fi

if [ $? -eq 0 ]; then
    echo -e "${GREEN}Deployment successful!${NC}"
else
    echo -e "${RED}Deployment failed!${NC}"
    exit 1
fi

# Wait a moment for services to start
sleep 5

# Check service status
echo -e "${BLUE}Checking service status...${NC}"

# Check if notion-invoices container is running
if docker ps | grep -q notion-invoices; then
    echo -e "${GREEN}✓ Notion-invoices container is running${NC}"
else
    echo -e "${RED}✗ Notion-invoices container is not running${NC}"
    echo -e "${BLUE}Container logs:${NC}"
    docker-compose logs notion-invoices
fi

# Check health endpoint
echo -e "${BLUE}Testing health endpoint...${NC}"
sleep 2
HEALTH_CHECK=$(curl -s http://localhost:8080/health 2>/dev/null || echo "failed")
if [ "$HEALTH_CHECK" == '{"status":"ok"}' ]; then
    echo -e "${GREEN}✓ Health endpoint is responding correctly${NC}"
else
    echo -e "${RED}✗ Health endpoint is not responding: $HEALTH_CHECK${NC}"
fi

# Check tunnel if enabled
if [ "$NO_TUNNEL" != true ] && [ -f cloudflared/config.yml ]; then
    if docker ps | grep -q cloudflared-tunnel; then
        echo -e "${GREEN}✓ Cloudflare tunnel is running${NC}"
    else
        echo -e "${RED}✗ Cloudflare tunnel is not running${NC}"
    fi
fi

echo ""
echo -e "${GREEN}Deployment complete!${NC}"
echo -e "${BLUE}Access points:${NC}"
echo "  Local: http://localhost:8080/health"

if [ "$NO_TUNNEL" != true ] && [ -f cloudflared/config.yml ]; then
    HOSTNAME=$(grep "hostname:" cloudflared/config.yml | awk '{print $2}' || echo "your-domain.com")
    echo "  Public: https://$HOSTNAME/health"
    echo "  Webhook: https://$HOSTNAME/api/webhooks/stripe"
fi

echo ""
echo -e "${BLUE}Useful commands:${NC}"
echo "  ./docker-status.sh                    # Check service status"
echo "  docker-compose logs -f notion-invoices # View live logs"
echo "  docker-compose down                   # Stop services"
echo "  docker-compose up -d                  # Start services"