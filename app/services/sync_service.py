"""Service for synchronizing invoices between Stripe and Notion."""

from datetime import datetime
from typing import Dict, Optional, Tuple

import logfire

from app.models.invoice import Invoice, InvoiceStatus
from app.services.notion_service import NotionService
from app.services.stripe_service import StripeService

# Configure logging
logger = logfire.getLogger(__name__)


class SyncService:
    """Service for handling two-way synchronization of invoices."""

    def __init__(self):
        """Initialize Stripe and Notion services."""
        self.notion_service = NotionService()

    def _sync_to_notion(self, invoice: Invoice) -> Tuple[bool, Optional[str]]:
        """
        Sync an invoice from Stripe to Notion.

        Args:
            invoice: Invoice model from Stripe

        Returns:
            Tuple[bool, Optional[str]]: Success status and Notion page ID
        """
        try:
            # Check if this is a deleted invoice
            if invoice.status == InvoiceStatus.DELETED:
                logger.info("Handling deleted invoice", invoice_id=invoice.id)
                success = self.notion_service.delete_invoice_by_stripe_id(invoice.id)
                logger.info("Delete operation result", success=success)
                return success, None

            # Set last synced timestamp
            invoice.last_synced_at = datetime.now()

            # Create or update in Notion
            with logfire.span("create_or_update_invoice", stripe_id=invoice.id):
                notion_id = self.notion_service.create_or_update_invoice(invoice)

            if notion_id:
                logger.info(
                    "Successfully synced invoice to Notion",
                    stripe_id=invoice.id,
                    notion_id=notion_id,
                )
                return True, notion_id
            else:
                logger.error("Failed to sync invoice to Notion", stripe_id=invoice.id)
                return False, None
        except Exception as e:
            logger.exception(
                "Error syncing invoice to Notion", stripe_id=invoice.id, error=str(e)
            )
            return False, None

    def _sync_to_stripe(self, invoice: Invoice) -> bool:
        """
        Sync invoice changes from Notion to Stripe.

        Currently, this only syncs the memo field, which includes the billing period.

        Args:
            invoice: Invoice model from Notion

        Returns:
            bool: Success status
        """
        try:
            # Only sync if we have a valid Stripe ID
            if not invoice.id or not invoice.id.startswith("in_"):
                logger.warning("Invalid Stripe invoice ID", stripe_id=invoice.id)
                return False

            logger.info("Syncing to Stripe", invoice_id=invoice.id, memo=invoice.memo)

            # Check if we have a memo to update
            if invoice.memo:
                # Update memo in Stripe
                logger.info(
                    "Updating memo in Stripe", stripe_id=invoice.id, memo=invoice.memo
                )
                with logfire.span("update_invoice_memo", stripe_id=invoice.id):
                    success = StripeService.update_invoice_memo(
                        invoice.id, invoice.memo
                    )

                if success:
                    logger.info(
                        "Successfully synced memo to Stripe", stripe_id=invoice.id
                    )
                else:
                    logger.error("Failed to sync memo to Stripe", stripe_id=invoice.id)
                return success
            else:
                logger.warning("No memo to update", stripe_id=invoice.id)

            # Nothing to sync
            return True
        except Exception as e:
            logger.exception(
                "Error syncing invoice to Stripe", stripe_id=invoice.id, error=str(e)
            )
            return False

    def handle_stripe_event(self, invoice: Invoice) -> bool:
        """
        Handle an invoice event from Stripe.

        This syncs the invoice from Stripe to Notion.

        Args:
            invoice: Invoice model from Stripe event

        Returns:
            bool: Success status
        """
        with logfire.span(
            "handle_stripe_event", stripe_id=invoice.id, status=invoice.status
        ):
            success, notion_id = self._sync_to_notion(invoice)
            return success

    def handle_notion_update(self, notion_invoice_id: str) -> bool:
        """
        Handle an invoice update from Notion.

        This syncs changes from Notion to Stripe, particularly the billing period
        to the memo field.

        Args:
            notion_invoice_id: Notion page ID of the updated invoice

        Returns:
            bool: Success status
        """
        try:
            with logfire.span("handle_notion_update", notion_id=notion_invoice_id):
                logger.info("Handling Notion update", notion_id=notion_invoice_id)

                # Get the updated invoice from Notion
                notion_invoice = self.notion_service.query_invoice_by_notion_id(
                    notion_invoice_id
                )

                if not notion_invoice:
                    logger.error(
                        "Failed to retrieve Notion invoice", notion_id=notion_invoice_id
                    )
                    return False

                # Add safety check for backward compatibility with older invoice objects
                if not hasattr(notion_invoice, "billing_period_start") or not hasattr(
                    notion_invoice, "billing_period_end"
                ):
                    logger.warning(
                        "Invoice has incompatible model - missing billing period fields",
                        notion_id=notion_invoice_id,
                    )
                    # Use the single billing_period field if available
                    if (
                        hasattr(notion_invoice, "billing_period")
                        and notion_invoice.billing_period
                    ):
                        billing_period = notion_invoice.billing_period
                        # Add these attributes to the instance for compatibility
                        notion_invoice.billing_period_start = billing_period
                        notion_invoice.billing_period_end = None
                        logger.info(
                            "Used legacy billing_period field",
                            billing_period=billing_period,
                        )
                    else:
                        logger.warning(
                            "No billing period information found",
                            notion_id=notion_invoice_id,
                        )

                logger.info(
                    "Retrieved Notion invoice",
                    notion_id=notion_invoice.notion_id,
                    stripe_id=notion_invoice.stripe_id,
                    billing_period_start=notion_invoice.billing_period_start,
                    billing_period_end=notion_invoice.billing_period_end,
                )

                # Convert to Invoice model
                if notion_invoice and notion_invoice.stripe_id:
                    # First get the current Stripe invoice to preserve existing memo content
                    stripe_invoice = StripeService.get_invoice(notion_invoice.stripe_id)

                    if not stripe_invoice:
                        logger.warning(
                            "Stripe invoice not found",
                            notion_id=notion_invoice_id,
                            stripe_id=notion_invoice.stripe_id,
                        )
                        return False

                    logger.info(
                        "Retrieved Stripe invoice",
                        stripe_id=stripe_invoice.id,
                        memo=stripe_invoice.memo,
                    )

                    # Create a new invoice model with combined data
                    invoice = notion_invoice.to_invoice_model()

                    # If there's a billing period in Notion, update the memo in Stripe
                    if notion_invoice.billing_period_start:
                        # Keep original memo content if any
                        memo = stripe_invoice.memo or ""
                        logger.info("Original memo content", memo=memo)

                        # Format the billing period information
                        billing_period_text = self._format_billing_period(
                            notion_invoice.billing_period_start,
                            notion_invoice.billing_period_end,
                        )

                        # Check if we need to update the billing period in the memo
                        if "Billing Period:" in memo:
                            # Replace existing billing period
                            logger.info("Updating existing billing period in memo")
                            memo_lines = memo.split("\n")
                            updated_lines = []
                            for line in memo_lines:
                                if line.startswith("Billing Period:"):
                                    updated_lines.append(
                                        f"Billing Period: {billing_period_text}"
                                    )
                                else:
                                    updated_lines.append(line)
                            memo = "\n".join(updated_lines)
                        else:
                            # Add billing period if not present
                            logger.info("Adding new billing period to memo")
                            memo = (
                                f"{memo}\nBilling Period: {billing_period_text}".strip()
                            )

                        logger.info("Updated memo content", memo=memo)

                        # Update the invoice memo
                        invoice.memo = memo
                    else:
                        logger.warning("No billing period found in Notion invoice")

                    # Sync to Stripe
                    logger.info(
                        "Syncing Notion invoice to Stripe with updated memo",
                        notion_id=notion_invoice_id,
                        stripe_id=invoice.id,
                    )
                    result = self._sync_to_stripe(invoice)
                    logger.info("Sync result", success=result)
                    return result
                else:
                    logger.warning(
                        "Invoice not found or missing Stripe ID",
                        notion_id=notion_invoice_id,
                    )
                    return False
        except Exception as e:
            logger.exception(
                "Error handling Notion update",
                notion_id=notion_invoice_id,
                error=str(e),
            )
            return False

    def _format_billing_period(
        self, start_date: Optional[datetime], end_date: Optional[datetime]
    ) -> str:
        """
        Format billing period dates for display in memo.

        Args:
            start_date: Billing period start date
            end_date: Billing period end date

        Returns:
            str: Formatted billing period text
        """
        if not start_date:
            return ""

        date_format = "%Y-%m-%d"
        start_str = start_date.strftime(date_format)

        if end_date:
            end_str = end_date.strftime(date_format)
            return f"{start_str} to {end_str}"
        else:
            return start_str

    def perform_background_sync(self, days_back: int = 30) -> Dict[str, int]:
        """
        Perform a background sync of recent invoices from Stripe to Notion.

        This should be called periodically to ensure consistency between
        Stripe and Notion, especially after downtime or missed webhooks.

        Args:
            days_back: Number of days back to sync

        Returns:
            Dict[str, int]: Stats about the sync operation
        """
        with logfire.span("background_sync", days_back=days_back):
            logger.info("Starting background sync", days_back=days_back)
            stats = {"total": 0, "synced": 0, "failed": 0, "unchanged": 0, "deleted": 0}

            try:
                # Get recent invoices from Stripe
                recent_invoices = StripeService.get_recent_invoices(days_back)
                stats["total"] = len(recent_invoices)

                logger.info("Found recent invoices in Stripe", count=stats["total"])

                # Process each invoice
                for stripe_invoice in recent_invoices:
                    try:
                        # Convert to our model
                        invoice = stripe_invoice.to_invoice_model()

                        # Check if the invoice already exists and is up to date
                        existing_invoice = (
                            self.notion_service.query_invoice_by_stripe_id(invoice.id)
                        )

                        if existing_invoice and existing_invoice.last_edited_time:
                            # Skip if the existing invoice is newer than this one
                            if invoice.stripe_updated_at:
                                # Convert both datetimes to naive for comparison or ensure both are timezone-aware
                                notion_time = existing_invoice.last_edited_time.replace(
                                    tzinfo=None
                                )
                                stripe_time = invoice.stripe_updated_at.replace(
                                    tzinfo=None
                                )

                                if notion_time > stripe_time:
                                    stats["unchanged"] += 1
                                    continue

                        # Sync to Notion
                        with logfire.span("sync_invoice", stripe_id=invoice.id):
                            success, _ = self._sync_to_notion(invoice)

                        if success:
                            stats["synced"] += 1
                        else:
                            stats["failed"] += 1

                    except Exception as e:
                        logger.exception(
                            "Error syncing invoice",
                            stripe_id=stripe_invoice.id,
                            error=str(e),
                        )
                        stats["failed"] += 1

                # Check for deleted invoices - this is more expensive so we'll skip for now
                # This would require comparing all Notion invoices with all Stripe invoices

                logger.info("Background sync completed", **stats)
                return stats

            except Exception as e:
                logger.exception("Error performing background sync", error=str(e))
                return stats
