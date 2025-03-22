"""Webhook handlers for Stripe events."""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel

from app.services.stripe_service import StripeService
from app.services.sync_service import SyncService

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter()


class WebhookResponse(BaseModel):
    """Response model for webhook endpoints."""

    success: bool
    message: str


async def _get_sync_service() -> SyncService:
    """
    Dependency to get an instance of SyncService.

    Returns:
        SyncService: New instance of SyncService
    """
    return SyncService()


@router.post("/stripe", response_model=WebhookResponse)
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="Stripe-Signature"),
    sync_service: SyncService = Depends(_get_sync_service),
) -> Dict[str, Any]:
    """
    Handle Stripe webhook events.

    Args:
        request: FastAPI request object
        stripe_signature: Stripe signature header
        sync_service: SyncService instance

    Returns:
        Dict[str, Any]: Response with success status and message

    Raises:
        HTTPException: If the webhook signature is invalid or event processing fails
    """
    # Get raw request body
    payload = await request.body()

    # Verify webhook signature
    if not stripe_signature:
        logger.warning("Stripe webhook called without signature header")
        raise HTTPException(status_code=400, detail="Stripe signature header missing")

    # Parse and validate the event
    event = StripeService.parse_webhook_event(payload, stripe_signature)
    if not event:
        logger.warning("Invalid Stripe webhook signature")
        raise HTTPException(status_code=400, detail="Invalid Stripe webhook signature")

    # Log the event
    logger.info(f"Received Stripe webhook event: {event['type']}")

    try:
        # Process the event if it's an invoice event
        if event["type"].startswith("invoice."):
            # Add detailed logging for the event type
            logger.info(
                f"Processing Stripe event: {event['type']} for invoice {event['data']['object'].get('id')}"
            )

            # Process the invoice event
            invoice = StripeService.process_invoice_event(event)
            if invoice:
                # Log the invoice status
                logger.info(f"Invoice processed with status: {invoice.status}")

                # Sync to Notion
                success = sync_service.handle_stripe_event(invoice)
                if success:
                    return {
                        "success": True,
                        "message": f"Successfully processed {event['type']} event",
                    }
                else:
                    logger.error(f"Failed to sync invoice {invoice.id} to Notion")
                    return {
                        "success": False,
                        "message": "Failed to sync invoice to Notion",
                    }
            else:
                logger.warning(f"Could not process invoice from event {event['id']}")
                return {
                    "success": False,
                    "message": "Could not process invoice from event",
                }

        # For non-invoice events, just acknowledge receipt
        return {
            "success": True,
            "message": f"Received {event['type']} event, no action needed",
        }
    except Exception as e:
        logger.error(f"Error processing Stripe webhook: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error processing webhook: {str(e)}"
        )


@router.post("/notion", response_model=WebhookResponse)
async def notion_webhook(
    request: Request,
    sync_service: SyncService = Depends(_get_sync_service),
) -> Dict[str, Any]:
    """
    Handle Notion webhook events.

    Currently, this only handles invoice updates to sync billing period to Stripe memo.

    Args:
        request: FastAPI request object
        sync_service: SyncService instance

    Returns:
        Dict[str, Any]: Response with success status and message
    """
    try:
        # Get JSON data from request
        payload = await request.json()
        logger.info(f"Received Notion webhook event: {payload.get('type', 'unknown')}")

        # Extract the notion page ID from the payload
        # The exact structure will depend on Notion's webhook format
        notion_page_id = payload.get("page_id")

        if not notion_page_id:
            logger.warning("Missing page_id in Notion webhook payload")
            return {"success": False, "message": "Missing page_id in payload"}

        # Process the update
        success = sync_service.handle_notion_update(notion_page_id)

        if success:
            logger.info(
                f"Successfully processed Notion update for page {notion_page_id}"
            )
            return {"success": True, "message": "Successfully processed Notion update"}
        else:
            logger.warning(f"Failed to process Notion update for page {notion_page_id}")
            return {"success": False, "message": "Failed to process update"}
    except Exception as e:
        logger.error(f"Error processing Notion webhook: {e}", exc_info=True)
        return {"success": False, "message": f"Error processing webhook: {str(e)}"}
