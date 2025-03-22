"""Service for interacting with the Stripe API."""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import stripe
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import Config
from app.models.invoice import Invoice, InvoiceStatus, StripeInvoice

# Configure logging
logger = logging.getLogger(__name__)

# Configure Stripe API key
stripe.api_key = Config.STRIPE_API_KEY


class StripeService:
    """Service for interacting with Stripe API."""

    @staticmethod
    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def _make_api_request(func, *args, **kwargs) -> Dict:
        """
        Make a request to Stripe API with retry logic.

        Args:
            func: Stripe API function to call
            *args: Arguments to pass to the function
            **kwargs: Keyword arguments to pass to the function

        Returns:
            Dict: API response

        Raises:
            stripe.error.StripeError: If the API request fails after retries
        """
        try:
            return func(*args, **kwargs)
        except stripe.error.RateLimitError as e:
            logger.warning(f"Rate limit hit when calling Stripe API: {e}")
            raise
        except stripe.error.StripeError as e:
            logger.error(f"Error calling Stripe API: {e}")
            raise

    @classmethod
    def get_invoice(cls, invoice_id: str) -> Optional[Invoice]:
        """
        Retrieve an invoice from Stripe by ID.

        Args:
            invoice_id: Stripe invoice ID

        Returns:
            Optional[Invoice]: Invoice object if found, None otherwise
        """
        try:
            response = cls._make_api_request(stripe.Invoice.retrieve, invoice_id)
            stripe_invoice = StripeInvoice.parse_obj(response)
            return stripe_invoice.to_invoice_model()
        except stripe.error.InvalidRequestError:
            logger.warning(f"Invoice {invoice_id} not found in Stripe")
            return None
        except Exception as e:
            logger.error(f"Error retrieving invoice {invoice_id} from Stripe: {e}")
            return None

    @classmethod
    def get_recent_invoices(cls, days_back: int = 30) -> List[StripeInvoice]:
        """
        Get invoices from Stripe created or updated in the last N days.

        Args:
            days_back: Number of days back to fetch

        Returns:
            List[StripeInvoice]: List of recent invoices
        """
        try:
            # Calculate timestamp for days_back days ago
            now = datetime.now()
            created_after = int((now - timedelta(days=days_back)).timestamp())

            logger.info(
                f"Fetching invoices created after {datetime.fromtimestamp(created_after)}"
            )

            # Fetch invoices created in the specified time period
            response = cls._make_api_request(
                stripe.Invoice.list,
                limit=100,  # Adjust based on your volume
                created={"gte": created_after},
            )

            invoices = []
            for invoice_data in response.get("data", []):
                try:
                    stripe_invoice = StripeInvoice.parse_obj(invoice_data)
                    invoices.append(stripe_invoice)
                except Exception as e:
                    logger.error(f"Error parsing invoice {invoice_data.get('id')}: {e}")

            logger.info(
                f"Found {len(invoices)} invoices in Stripe from the last {days_back} days"
            )
            return invoices
        except Exception as e:
            logger.error(
                f"Error retrieving recent invoices from Stripe: {e}", exc_info=True
            )
            return []

    @classmethod
    def update_invoice_memo(cls, invoice_id: str, memo: str) -> bool:
        """
        Update the memo/description field of a Stripe invoice.

        Args:
            invoice_id: Stripe invoice ID
            memo: New memo text

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.info(f"Updating Stripe invoice {invoice_id} memo to: '{memo}'")
            response = cls._make_api_request(
                stripe.Invoice.modify, invoice_id, description=memo
            )
            logger.info(f"Stripe API response: {response.description}")
            return True
        except stripe.error.StripeError as e:
            logger.error(
                f"Stripe API error updating memo for invoice {invoice_id}: {e}",
                exc_info=True,
            )
            return False
        except Exception as e:
            logger.error(
                f"Error updating memo for invoice {invoice_id}: {e}", exc_info=True
            )
            return False

    @classmethod
    def verify_webhook_signature(cls, payload: bytes, signature: str) -> bool:
        """
        Verify that a webhook request came from Stripe.

        Args:
            payload: Raw request body
            signature: Stripe signature header

        Returns:
            bool: True if signature is valid, False otherwise
        """
        try:
            stripe.Webhook.construct_event(
                payload, signature, Config.STRIPE_WEBHOOK_SECRET
            )
            return True
        except (stripe.error.SignatureVerificationError, ValueError) as e:
            logger.warning(f"Invalid webhook signature: {e}")
            return False

    @classmethod
    def parse_webhook_event(cls, payload: bytes, signature: str) -> Optional[Dict]:
        """
        Parse and validate a webhook event from Stripe.

        Args:
            payload: Raw request body
            signature: Stripe signature header

        Returns:
            Optional[Dict]: Event data if valid, None otherwise
        """
        try:
            event = stripe.Webhook.construct_event(
                payload, signature, Config.STRIPE_WEBHOOK_SECRET
            )
            return event
        except (stripe.error.SignatureVerificationError, ValueError) as e:
            logger.warning(f"Invalid webhook event: {e}")
            return None

    @classmethod
    def process_invoice_event(cls, event: Dict) -> Optional[Invoice]:
        """
        Process a Stripe invoice event.

        Args:
            event: Stripe event object

        Returns:
            Optional[Invoice]: Processed invoice if successful, None otherwise
        """
        event_type = event["type"]

        # Check if this is a deletion event
        if event_type == "invoice.deleted":
            invoice_data = event["data"]["object"]
            # Create a minimal Invoice object with just the ID
            return Invoice(
                id=invoice_data["id"],
                invoice_number=invoice_data.get("number", ""),
                status=InvoiceStatus.DELETED,  # Mark as deleted
                amount=0,
                customer_id=invoice_data.get("customer", ""),
                stripe_updated_at=datetime.now(),
            )

        # For regular events
        if event_type not in [
            "invoice.created",
            "invoice.updated",
            "invoice.finalized",
            "invoice.paid",
            "invoice.payment_failed",
            "invoice.payment_succeeded",
        ]:
            return None

        try:
            invoice_data = event["data"]["object"]
            stripe_invoice = StripeInvoice.parse_obj(invoice_data)
            return stripe_invoice.to_invoice_model()
        except Exception as e:
            logger.error(f"Error processing invoice event: {e}")
            return None
