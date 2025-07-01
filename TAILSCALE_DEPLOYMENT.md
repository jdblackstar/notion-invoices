# Tailscale Deployment Guide

This guide shows how to deploy the Notion-Invoices service using Tailscale for private access while handling the Stripe webhook requirement.

## Why Tailscale + Limited Public Access?

- **Tailscale**: Perfect for private access to your service dashboard and management
- **Public Endpoint**: Required for Stripe webhooks (Stripe can't reach private Tailnet)

## Deployment Options

### Option 1: Tailscale + Tailscale Funnel (Recommended)

Tailscale Funnel allows you to expose specific paths publicly while keeping the rest private.

1. **Deploy the service without Cloudflare:**
   ```bash
   ./docker-deploy.sh --no-tunnel
   ```

2. **Install Tailscale on your server:**
   ```bash
   # Ubuntu/Debian
   curl -fsSL https://tailscale.com/install.sh | sh
   
   # Start Tailscale
   sudo tailscale up
   ```

3. **Enable Tailscale Funnel for webhooks only:**
   ```bash
   # Enable HTTPS funnel for webhook path only
   tailscale funnel --bg --https=443 --set-path=/api/webhooks 8080
   ```

4. **Access your service:**
   - **Private access**: `https://your-machine-name.tailnet-name.ts.net:8080`
   - **Webhook URL**: `https://your-machine-name.tailnet-name.ts.net/api/webhooks/stripe`

### Option 2: Tailscale + Cloudflare for Webhooks Only

Keep Cloudflare tunnel but configure it to only expose webhook endpoints:

1. **Set up webhook-only tunnel:**
   ```bash
   ./docker-deploy.sh --setup-tunnel
   ```

2. **Configure `./cloudflared/config.yml` for webhooks only:**
   ```yaml
   tunnel: YOUR_TUNNEL_ID
   credentials-file: /etc/cloudflared/YOUR_TUNNEL_ID.json
   ingress:
     - hostname: webhooks.yourdomain.com
       service: http://notion-invoices:8080
       path: /api/webhooks/*
     - service: http_status:404
   ```

3. **Deploy with webhook tunnel:**
   ```bash
   ./docker-deploy.sh
   ```

4. **Install Tailscale for private access:**
   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up
   ```

5. **Access your service:**
   - **Private access**: `https://your-machine-name.tailnet-name.ts.net:8080`
   - **Webhook URL**: `https://webhooks.yourdomain.com/api/webhooks/stripe`

### Option 3: Tailscale + Reverse Proxy

Use nginx or Caddy to expose only webhooks publicly:

1. **Create nginx config for webhooks:**
   ```nginx
   # /etc/nginx/sites-available/notion-webhooks
   server {
       listen 80;
       server_name webhooks.yourdomain.com;
       
       location /api/webhooks/ {
           proxy_pass http://localhost:8080;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
       
       location / {
           return 404;
       }
   }
   ```

2. **Deploy service:**
   ```bash
   ./docker-deploy.sh --no-tunnel
   ```

## Stripe Webhook Configuration

Regardless of which option you choose, configure your Stripe webhook endpoint:

1. Go to Stripe Dashboard > Developers > Webhooks
2. Add endpoint with your public webhook URL:
   - **Option 1**: `https://your-machine-name.tailnet-name.ts.net/api/webhooks/stripe`
   - **Option 2**: `https://webhooks.yourdomain.com/api/webhooks/stripe`
   - **Option 3**: `https://webhooks.yourdomain.com/api/webhooks/stripe`

3. Select these events:
   - `invoice.created`
   - `invoice.updated`
   - `invoice.finalized`
   - `invoice.paid`
   - `invoice.payment_failed`
   - `invoice.payment_succeeded`
   - `invoice.deleted`

## Security Considerations

### With Tailscale Funnel
- Only webhook endpoints are exposed publicly
- Main application remains private in your Tailnet
- Tailscale handles authentication for private access

### With Cloudflare + Tailscale
- Cloudflare tunnel only exposes webhook paths
- Rate limiting and DDoS protection from Cloudflare
- Private access through Tailscale

### Access Control
```bash
# Restrict Tailscale access to specific users/devices
tailscale up --advertise-tags=tag:notion-invoices
```

## Monitoring and Logs

Access logs and monitoring through Tailscale:

```bash
# SSH through Tailscale
ssh user@your-machine-name.tailnet-name.ts.net

# Check service status
./docker-status.sh

# View logs
docker-compose logs -f notion-invoices
```

## Benefits of This Approach

- **Security**: Main application not exposed to public internet
- **Simplicity**: No complex firewall rules or VPN setup
- **Flexibility**: Easy access from any device in your Tailnet
- **Webhook Support**: Stripe can still reach your webhook endpoint
- **Zero Configuration**: Tailscale handles networking automatically

## Troubleshooting

### Tailscale Funnel Issues
```bash
# Check funnel status
tailscale funnel status

# Restart funnel
tailscale funnel --reset
tailscale funnel --bg --https=443 --set-path=/api/webhooks 8080
```

### Testing Webhook Access
```bash
# Test webhook endpoint publicly
curl -X POST https://your-public-endpoint/api/webhooks/stripe

# Test private access through Tailscale
curl https://your-machine-name.tailnet-name.ts.net:8080/health
```

This setup gives you the best of both worlds: private, secure access to your service through Tailscale, while still allowing Stripe to deliver webhooks to your application.