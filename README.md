# Notion-Stripe Invoice Sync

A service that provides two-way synchronization between Stripe invoices and a Notion database.

## Features

- Real-time sync of invoice data from Stripe to Notion via webhooks
- Ability to edit billing period in Notion and sync it back to Stripe as part of the memo
- Configurable field mapping between systems
- Error handling and retry mechanisms for failed API calls
- Logging of all sync activities

## Setup

### Requirements

- Python 3.13 or higher
- Stripe account with API access
- Notion account with a properly formatted invoice database
- Notion API key with access to your databases

### Installation

1. Clone this repository:

```bash
git clone https://github.com/yourusername/notion-invoices.git
cd notion-invoices
```

2. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e .
```

3. Copy the example environment file and fill in your credentials:

```bash
cp .env.example .env
# Edit .env with your Stripe and Notion API keys
```

### Notion Database Setup

Your Notion Invoice database should have the following properties:

- **Stripe ID** (Text): Stores the Stripe invoice ID
- **Invoice Number** (Text): Stores the invoice number
- **Status** (Select): Options should include Draft, Open, Paid, Uncollectible, Void
- **Amount** (Number): Stores the invoice amount (will be displayed as dollars/currency)
- **Customer ID** (Text): Stores the Stripe customer ID
- **Finalized Date** (Date): Date when the invoice was finalized
- **Due Date** (Date): Date when payment is due
- **Memo** (Text): Invoice memo or description
- **Billing Period** (Text): Billing period for the invoice (Notion-only field)

### Stripe Webhook Setup

1. Go to the Stripe Dashboard > Developers > Webhooks
2. Add a new endpoint with URL: `https://your-domain.com/api/webhooks/stripe`
3. Select the following events to listen for:
   - `invoice.created`
   - `invoice.updated`
   - `invoice.finalized`
   - `invoice.paid`
   - `invoice.payment_failed`
   - `invoice.payment_succeeded`
4. Copy the webhook signing secret to your `.env` file

## Running the Service

Start the service with:

```bash
python -m app.main
```

The API will be available at http://localhost:8000.

## Development

### Testing Webhooks Locally

You can use the Stripe CLI to test webhooks locally:

```bash
stripe listen --forward-to http://localhost:8000/api/webhooks/stripe
```

### Running Tests

```bash
pytest
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.
