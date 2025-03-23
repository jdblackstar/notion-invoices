"""Main application module for the Notion-Stripe invoice sync service."""

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from typing import Dict

import logfire
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from logfire.integrations.fastapi import LogfireMiddleware

from app.api.router import api_router
from app.config import Config
from app.services.sync_service import SyncService

# Configure Logfire
logfire.configure(
    service_name=Config.LOGFIRE_SERVICE_NAME,
    environment=Config.ENVIRONMENT,
    level=Config.LOG_LEVEL,
    api_key=Config.LOGFIRE_API_KEY if Config.LOGFIRE_API_KEY else None,
)

# Configure standard logging as a fallback
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# Replace the standard logger with Logfire logger
logger = logfire.getLogger(__name__)


# Global variable to store the background task
background_task = None


async def _run_periodic_sync():
    """Run the periodic sync in the background."""
    sync_interval = Config.SYNC_INTERVAL_SECONDS
    logger.info("Starting periodic sync task", sync_interval_seconds=sync_interval)

    # Wait for the app to fully start and for the immediate sync to complete
    await asyncio.sleep(10)
    logger.info("Beginning regular periodic sync schedule")

    while True:
        try:
            # Create a new SyncService instance
            sync_service = SyncService()

            # Perform the sync
            current_time = datetime.now()
            logger.info("Running scheduled background sync", timestamp=current_time)
            stats = sync_service.perform_background_sync()

            # Look for recently updated Notion invoices and sync their billing periods to Stripe
            try:
                with logfire.span("notion_to_stripe_billing_period_sync"):
                    logger.info("Starting Notion to Stripe billing period sync")
                    notion_service = sync_service.notion_service

                    # Get recently updated invoices from Notion
                    logger.info("Fetching recently updated Notion invoices")
                    recent_invoices = notion_service.get_recently_updated_invoices(
                        hours_back=1
                    )

                    logger.info(
                        "Found recently updated Notion invoices",
                        count=len(recent_invoices),
                    )

                    if recent_invoices:
                        # Log each invoice found for debugging
                        for i, invoice in enumerate(recent_invoices):
                            logger.info(
                                "Processing invoice",
                                index=i + 1,
                                notion_id=invoice.notion_id,
                                stripe_id=invoice.stripe_id,
                                billing_period_start=invoice.billing_period_start,
                                billing_period_end=invoice.billing_period_end,
                            )

                        # Sync each invoice's billing period to Stripe
                        sync_count = 0
                        for invoice in recent_invoices:
                            if invoice.notion_id and invoice.billing_period_start:
                                with logfire.span(
                                    "sync_billing_period", notion_id=invoice.notion_id
                                ):
                                    logger.info(
                                        "Syncing billing period to Stripe",
                                        notion_id=invoice.notion_id,
                                    )
                                    result = sync_service.handle_notion_update(
                                        invoice.notion_id
                                    )
                                    logger.info(
                                        "Billing period sync result",
                                        notion_id=invoice.notion_id,
                                        success=result,
                                    )
                                    if result:
                                        sync_count += 1
                            else:
                                logger.info(
                                    "Skipping invoice - no billing period or missing Stripe ID",
                                    notion_id=invoice.notion_id,
                                )

                        logger.info(
                            "Completed Notion to Stripe billing period sync",
                            invoices_synced=sync_count,
                        )
                    else:
                        logger.info("No recently updated invoices found in Notion")
            except Exception as e:
                logger.exception(
                    "Error syncing Notion billing periods to Stripe", error=str(e)
                )

            logger.info("Background sync completed", stats=stats)
        except Exception as e:
            logger.exception("Error in background sync", error=str(e))

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
            logger.error("Missing configuration", var=var, message=message)
        sys.exit(1)

    # Create FastAPI app
    app = FastAPI(
        title="Notion-Stripe Invoice Sync",
        description="A service that synchronizes invoices between Stripe and Notion",
        version="0.1.0",
    )

    # Add Logfire middleware
    app.add_middleware(LogfireMiddleware)

    # Include API router
    app.include_router(api_router, prefix="/api")

    # Add exception handlers
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request, exc):
        logger.warning("HTTP exception", status_code=exc.status_code, detail=exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "message": exc.detail},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request, exc):
        logger.exception("Unhandled exception", error=str(exc))
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
            with logfire.span("startup_sync"):
                sync_service = SyncService()

                # Run Stripe to Notion sync first
                logger.info("Performing immediate Stripe to Notion sync on startup")
                stats = sync_service.perform_background_sync()
                logger.info("Immediate startup sync completed", stats=stats)

                # Then check for Notion updates that need to be synced to Stripe
                logger.info(
                    "Checking for Notion updates that need to be synced to Stripe"
                )
                notion_service = sync_service.notion_service
                # Use a more generous timeframe for startup sync to catch any missed updates
                recent_invoices = notion_service.get_recently_updated_invoices(
                    hours_back=72
                )  # Check last 3 days

                if recent_invoices:
                    logger.info(
                        "Found recently updated invoices during startup sync",
                        count=len(recent_invoices),
                    )

                    # Sync each invoice's billing period to Stripe
                    sync_count = 0
                    for invoice in recent_invoices:
                        if invoice.notion_id and invoice.billing_period_start:
                            logger.info(
                                "Syncing billing period to Stripe",
                                notion_id=invoice.notion_id,
                            )
                            result = sync_service.handle_notion_update(
                                invoice.notion_id
                            )
                            if result:
                                sync_count += 1
                    logger.info(
                        "Startup sync completed", notion_invoices_synced=sync_count
                    )
                else:
                    logger.info(
                        "No recently updated invoices found during startup sync"
                    )
        except Exception as e:
            logger.exception("Error during immediate startup sync", error=str(e))

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
        with logfire.span("manual_notion_sync", notion_id=args.sync_notion):
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
