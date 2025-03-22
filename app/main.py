"""Main application module for the Notion-Stripe invoice sync service."""

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from typing import Dict

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.config import Config
from app.services.sync_service import SyncService

# Configure logging
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


# Global variable to store the background task
background_task = None


async def _run_periodic_sync():
    """Run the periodic sync in the background."""
    sync_interval = Config.SYNC_INTERVAL_SECONDS
    logger.info(f"Starting periodic sync task with interval of {sync_interval} seconds")

    # Wait for the app to fully start and for the immediate sync to complete
    await asyncio.sleep(10)
    logger.info("Beginning regular periodic sync schedule")

    while True:
        try:
            # Create a new SyncService instance
            sync_service = SyncService()

            # Perform the sync
            logger.info(f"Running scheduled background sync at {datetime.now()}")
            stats = sync_service.perform_background_sync()

            # Look for recently updated Notion invoices and sync their billing periods to Stripe
            try:
                logger.info(
                    "=== BILLING PERIOD SYNC: Starting Notion to Stripe billing period sync ==="
                )
                notion_service = sync_service.notion_service

                # Get recently updated invoices from Notion
                # This would require a method to get recent updates from Notion
                # For now, we'll use the existing database query and filter by last_edited_time
                logger.info(
                    "BILLING PERIOD SYNC: Fetching recently updated Notion invoices"
                )
                recent_invoices = notion_service.get_recently_updated_invoices(
                    hours_back=1
                )

                logger.info(
                    f"BILLING PERIOD SYNC: Found {len(recent_invoices)} recently updated Notion invoices"
                )

                if recent_invoices:
                    # Log each invoice found for debugging
                    for i, invoice in enumerate(recent_invoices):
                        logger.info(
                            f"BILLING PERIOD SYNC: Invoice {i + 1}: ID={invoice.notion_id}, "
                            f"Stripe ID={invoice.stripe_id}, "
                            f"Billing Period Start={invoice.billing_period_start}, "
                            f"Billing Period End={invoice.billing_period_end}"
                        )

                    # Sync each invoice's billing period to Stripe
                    sync_count = 0
                    for invoice in recent_invoices:
                        if invoice.notion_id and invoice.billing_period_start:
                            logger.info(
                                f"BILLING PERIOD SYNC: Syncing billing period for Notion invoice {invoice.notion_id} to Stripe"
                            )
                            result = sync_service.handle_notion_update(
                                invoice.notion_id
                            )
                            logger.info(
                                f"BILLING PERIOD SYNC: Sync result for {invoice.notion_id}: {result}"
                            )
                            if result:
                                sync_count += 1
                        else:
                            logger.info(
                                f"BILLING PERIOD SYNC: Skipping invoice {invoice.notion_id} - no billing period or missing Stripe ID"
                            )

                    logger.info(
                        f"BILLING PERIOD SYNC: Completed with {sync_count} invoices synced to Stripe"
                    )
                else:
                    logger.info(
                        "BILLING PERIOD SYNC: No recently updated invoices found in Notion"
                    )

                logger.info(
                    "=== BILLING PERIOD SYNC: Completed Notion to Stripe billing period sync ==="
                )
            except Exception as e:
                logger.error(
                    f"BILLING PERIOD SYNC ERROR: Error syncing Notion billing periods to Stripe: {e}",
                    exc_info=True,
                )

            logger.info(f"Background sync completed with stats: {stats}")
        except Exception as e:
            logger.error(f"Error in background sync: {e}", exc_info=True)

        # Wait for the next sync interval
        await asyncio.sleep(sync_interval)


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        FastAPI: Configured FastAPI application
    """
    # Validate configuration
    missing_config = Config.validate()
    if missing_config:
        for var, message in missing_config.items():
            logger.error(f"Missing configuration: {var} - {message}")
        sys.exit(1)

    # Create FastAPI app
    app = FastAPI(
        title="Notion-Stripe Invoice Sync",
        description="A service that synchronizes invoices between Stripe and Notion",
        version="0.1.0",
    )

    # Include API router
    app.include_router(api_router, prefix="/api")

    # Add exception handlers
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request, exc):
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "message": exc.detail},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request, exc):
        logger.exception("Unhandled exception")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "Internal server error"},
        )

    # Health check endpoint
    @app.get("/health", tags=["health"])
    async def health_check() -> Dict[str, str]:
        """
        Health check endpoint to verify the service is running.

        Returns:
            Dict[str, str]: Status information
        """
        return {"status": "ok"}

    # Start the background sync task
    @app.on_event("startup")
    async def start_background_tasks():
        global background_task

        # Run an immediate sync to catch any changes that happened while service was down
        logger.info("Running immediate startup sync to catch recent changes")
        try:
            sync_service = SyncService()

            # Run Stripe to Notion sync first
            logger.info("Performing immediate Stripe to Notion sync on startup")
            stats = sync_service.perform_background_sync()
            logger.info(f"Immediate startup sync completed: {stats}")

            # Then check for Notion updates that need to be synced to Stripe
            logger.info("Checking for Notion updates that need to be synced to Stripe")
            notion_service = sync_service.notion_service
            # Use a more generous timeframe for startup sync to catch any missed updates
            recent_invoices = notion_service.get_recently_updated_invoices(
                hours_back=72
            )  # Check last 3 days

            if recent_invoices:
                logger.info(
                    f"Found {len(recent_invoices)} recently updated invoices in Notion during startup sync"
                )

                # Sync each invoice's billing period to Stripe
                sync_count = 0
                for invoice in recent_invoices:
                    if invoice.notion_id and invoice.billing_period_start:
                        logger.info(
                            f"Syncing billing period for Notion invoice {invoice.notion_id} to Stripe"
                        )
                        result = sync_service.handle_notion_update(invoice.notion_id)
                        if result:
                            sync_count += 1
                logger.info(
                    f"Startup sync completed: {sync_count} Notion invoices synced to Stripe"
                )
            else:
                logger.info(
                    "No recently updated invoices found in Notion during startup sync"
                )
        except Exception as e:
            logger.error(f"Error during immediate startup sync: {e}", exc_info=True)

        # Start the background task for periodic sync
        if Config.SYNC_INTERVAL_SECONDS > 0:
            background_task = asyncio.create_task(_run_periodic_sync())
            logger.info("Background sync task started")

    # Clean up background tasks
    @app.on_event("shutdown")
    async def cleanup_background_tasks():
        global background_task
        if background_task:
            background_task.cancel()
            logger.info("Background sync task cancelled")

    return app


# Create the global app instance for Uvicorn to use
app = create_app()


def main():
    """Run the application."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Notion-Stripe Invoice Sync Service")
    parser.add_argument(
        "--sync-notion", help="Sync a specific Notion page ID to Stripe (for testing)"
    )
    args = parser.parse_args()

    # If a specific Notion page ID was provided, just sync that and exit
    if args.sync_notion:
        sync_service = SyncService()
        print(f"Syncing Notion page {args.sync_notion} to Stripe...")
        success = sync_service.handle_notion_update(args.sync_notion)
        if success:
            print("Sync completed successfully")
        else:
            print("Sync failed")
        return

    # Otherwise, start the API server
    # Note: We don't need to call create_app again as we already have a global instance
    uvicorn.run(
        "app.main:app",  # Use the module:app pattern for reloading to work
        host=Config.HOST,
        port=Config.PORT,
        log_level=Config.LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    main()
