# Notion-Stripe Invoice Sync

A service that syncs invoices between Stripe and Notion.

## Features

- Real-time sync from Stripe to Notion using webhooks
- Edit billing period in Notion and sync it to Stripe
- Background sync to catch any missed updates
- Detailed logging of all activities
- Structured logging with Logfire for better observability

## Setup

### Requirements

- Python 3.13 or higher
- Stripe account with API access
- Notion account with an invoice database
- Notion API key
- Logfire account for observability (optional)

### Installation

1. Clone this repository:

```bash
git clone https://github.com/jdblackstar/notion-invoices.git
cd notion-invoices
```

2. Create a virtual environment and install dependencies:

   Option A: Using traditional tools
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -e .
   ```

   Option B: Using uv (faster)
   ```bash
   uv venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   uv pip install -e .
   ```

3. Copy the example environment file and add your credentials:

```bash
cp .env.example .env
# Edit .env with your Stripe and Notion API keys
```

### Logfire Configuration

For structured logging and observability, this project uses Logfire:

1. Sign up for a [Logfire](https://logfire.ai/) account if you don't have one
2. Get your API key from the Logfire dashboard
3. Add these variables to your `.env` file:

```bash
ENVIRONMENT=development # or production
LOGFIRE_API_KEY=your_logfire_api_key
LOGFIRE_SERVICE_NAME=notion-stripe-sync # or custom name
```

When `ENVIRONMENT` is set to `production`, a valid Logfire API key is required. In development mode, logs will be sent to stdout even without an API key.

### Deploy as a Service

For macOS, this project uses launchd to run as a background service:

1. Run the deployment script:

```bash
./deploy.sh
```

This will:
- Create plist files from the templates
- Install them to the correct location
- Start the service
- Set up Cloudflare tunnel (optional)

The plist templates are in the repository, but the generated plist files are git-ignored.

### Managing the Service

Check status and restart when needed:

```bash
./status.sh                # Check service status and recent activity
./status.sh --restart      # Restart services and show status
```

### Notion Database Setup

Your Notion Invoice database should have these properties:

- **Stripe ID** (Text): The Stripe invoice ID
- **Invoice Number** (Text): Invoice number
- **Status** (Select): Options for Draft, Open, Paid, Uncollectible, Void
- **Amount** (Number): Invoice amount
- **Customer ID** (Text): Stripe customer ID
- **Finalized Date** (Date): When the invoice was finalized
- **Due Date** (Date): When payment is due
- **Memo** (Text): Invoice description
- **Billing Period** (Text): Billing period (Notion-only field)

### Stripe Webhook Setup

1. Go to Stripe Dashboard > Developers > Webhooks
2. Add endpoint: `https://your-domain.com/api/webhooks/stripe`
3. Listen for these events:
   - `invoice.created`
   - `invoice.updated`
   - `invoice.finalized`
   - `invoice.paid`
   - `invoice.payment_failed`
   - `invoice.payment_succeeded`
   - `invoice.deleted`
4. Copy the webhook signing secret to your `.env` file

## Running the Service Manually

Start the service with:

```bash
python -m app.main
```

The API will be available at http://localhost:8000.

## Development

### Testing Webhooks Locally

Use the Stripe CLI to test webhooks:

```bash
stripe listen --forward-to http://localhost:8000/api/webhooks/stripe
```

### Running Tests

```bash
pytest
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.
