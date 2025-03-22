"""Test script to manually trigger invoice synchronization."""

import logging
import sys
from typing import Dict, Optional

import stripe

from app.config import Config
from app.services.stripe_service import StripeService
from app.services.sync_service import SyncService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


def _get_latest_invoice() -> Optional[Dict]:
    """
    Get the latest invoice from Stripe.

    Returns:
        Optional[Dict]: Latest invoice data if found, None otherwise
    """
    try:
        stripe.api_key = Config.STRIPE_API_KEY

        # List the most recent invoice
        invoices = stripe.Invoice.list(limit=1)

        if not invoices.data:
            logger.error("No invoices found in Stripe")
            return None

        return invoices.data[0]
    except Exception as e:
        logger.error(f"Error fetching latest invoice from Stripe: {e}")
        return None


def _sync_invoice(invoice_id: Optional[str] = None) -> None:
    """
    Sync a specific invoice or the latest one from Stripe to Notion.

    Args:
        invoice_id: Stripe invoice ID to sync, or None to sync the latest
    """
    try:
        # Get the invoice data
        if invoice_id:
            logger.info(f"Fetching invoice {invoice_id} from Stripe")
            stripe.api_key = Config.STRIPE_API_KEY
            invoice_data = stripe.Invoice.retrieve(invoice_id)
        else:
            logger.info("Fetching the latest invoice from Stripe")
            invoice_data = _get_latest_invoice()

        if not invoice_data:
            logger.error("No invoice data found")
            return

        invoice_id = invoice_data.id
        logger.info(f"Processing invoice {invoice_id}")

        # Convert to our model
        invoice = StripeService.process_invoice_event(
            {"type": "invoice.updated", "data": {"object": invoice_data}}
        )

        if not invoice:
            logger.error("Failed to process invoice data")
            return

        # Sync to Notion
        sync_service = SyncService()
        success = sync_service.handle_stripe_event(invoice)

        if success:
            logger.info(f"Successfully synced invoice {invoice_id} to Notion")
        else:
            logger.error(f"Failed to sync invoice {invoice_id} to Notion")

    except Exception as e:
        logger.error(f"Error syncing invoice: {e}")
        import traceback

        logger.error(traceback.format_exc())


if __name__ == "__main__":
    # Check if a specific invoice ID was provided
    if len(sys.argv) > 1:
        invoice_id = sys.argv[1]
        _sync_invoice(invoice_id)
    else:
        _sync_invoice()
