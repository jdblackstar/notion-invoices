# Migration Guide: From macOS plists to Docker

This guide helps you migrate from the old macOS plist-based deployment to the new Docker-based deployment.

## Prerequisites

- Docker and Docker Compose installed on your system
- Your existing `.env` file with API keys

## Migration Steps

### 1. Stop the old macOS services

If you have the old plist-based services running, stop them first:

```bash
# Stop the old services
launchctl bootout gui/$UID ~/Library/LaunchAgents/com.user.notion-invoices.plist 2>/dev/null || true
launchctl bootout gui/$UID ~/Library/LaunchAgents/com.user.cloudflared.plist 2>/dev/null || true

# Remove the plist files (optional)
rm ~/Library/LaunchAgents/com.user.notion-invoices.plist 2>/dev/null || true
rm ~/Library/LaunchAgents/com.user.cloudflared.plist 2>/dev/null || true
```

### 2. Update your repository

Pull the latest changes that include Docker support:

```bash
git pull origin main
```

### 3. Deploy with Docker

Deploy the service using the new Docker-based deployment:

```bash
# Deploy without Cloudflare tunnel
./docker-deploy.sh --no-tunnel

# OR deploy with Cloudflare tunnel (if you were using it before)
./docker-deploy.sh --setup-tunnel
# Follow the instructions, then run:
./docker-deploy.sh
```

### 4. Verify the migration

Check that everything is working:

```bash
# Check service status
./docker-status.sh

# Test the health endpoint
curl http://localhost:8080/health

# View logs
docker-compose logs -f notion-invoices
```

### 5. Set up auto-restart (optional)

If you want the service to automatically start on system boot:

```bash
cd system-restart
./setup-system-restart.sh
```

## Key Differences

| Feature | Old (macOS plists) | New (Docker) |
|---------|-------------------|--------------|
| **Deployment** | `./deploy.sh` | `./docker-deploy.sh` |
| **Status Check** | `./status.sh` | `./docker-status.sh` |
| **Logs** | `tail -f logs/notion-invoices.log` | `docker-compose logs -f notion-invoices` |
| **Restart** | `./status.sh --restart` | `./docker-status.sh --restart` |
| **Auto-start** | macOS LaunchAgent | systemd service (Linux) |
| **Isolation** | System processes | Docker containers |
| **Dependencies** | System Python + packages | Self-contained containers |

## Benefits of Docker Deployment

- **Platform Independence**: Works on Linux, macOS, and Windows
- **Isolation**: No conflicts with system Python or packages  
- **Consistency**: Same environment in development and production
- **Easier Management**: Container orchestration with Docker Compose
- **Better Logging**: Centralized log management with rotation
- **Health Checks**: Built-in container health monitoring
- **Scalability**: Easy to add more services or scale existing ones

## Troubleshooting

### Port Conflicts
If port 8080 is already in use, you can change it in `docker-compose.yml`:

```yaml
ports:
  - "8081:8080"  # Change first number to any available port
```

### Permission Issues
Make sure your user can run Docker commands:

```bash
# Add your user to the docker group (Linux)
sudo usermod -aG docker $USER
# Log out and back in for changes to take effect
```

### Cloudflare Tunnel Migration
If you were using Cloudflare tunnel before:

1. Your existing tunnel should still work
2. Copy your tunnel credentials to `./cloudflared/`
3. Update the service endpoint in your tunnel config to `http://notion-invoices:8080`

## Rollback (if needed)

If you need to rollback to the old deployment:

1. Stop Docker services: `docker-compose down`
2. Checkout the previous commit: `git checkout <previous-commit>`
3. Run the old deployment: `./deploy.sh`

However, we recommend sticking with Docker for the improved reliability and features.