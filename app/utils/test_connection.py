"""Test script to verify connections to Stripe and Notion APIs."""

import logging
import sys

from app.config import Config
from app.services.notion_service import NotionService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


def _format_notion_id(notion_id: str) -> str:
    """
    Format a Notion ID by adding hyphens if needed.

    Args:
        notion_id: Notion ID to format

    Returns:
        str: Formatted Notion ID
    """
    # Remove existing hyphens if any
    notion_id = notion_id.replace("-", "")

    # If the ID is the right length, format it with hyphens
    if len(notion_id) == 32:
        return f"{notion_id[:8]}-{notion_id[8:12]}-{notion_id[12:16]}-{notion_id[16:20]}-{notion_id[20:]}"

    # Otherwise return as is
    return notion_id


def _test_stripe_connection() -> bool:
    """
    Test connection to Stripe API.

    Returns:
        bool: True if connection is successful, False otherwise
    """
    try:
        # Try to list a single customer to verify API connection
        import stripe

        stripe.api_key = Config.STRIPE_API_KEY

        logger.info("Testing Stripe API connection...")
        customers = stripe.Customer.list(limit=1)

        logger.info(
            f"Successfully connected to Stripe API! Found {len(customers.data)} customers."
        )
        return True
    except Exception as e:
        logger.error(f"Failed to connect to Stripe API: {e}")
        return False


def _test_notion_connection() -> bool:
    """
    Test connection to Notion API.

    Returns:
        bool: True if connection is successful, False otherwise
    """
    try:
        notion_service = NotionService()

        # Format the database ID
        db_id = _format_notion_id(Config.NOTION_INVOICES_DATABASE_ID)

        logger.info("Testing Notion API connection...")
        logger.info(
            f"Attempting to access invoice database with formatted ID: {db_id}..."
        )

        # Try to query the database with a limit of 1 to verify API connection
        response = notion_service._make_api_request(
            notion_service.client.databases.query, database_id=db_id, page_size=1
        )

        result_count = len(response.get("results", []))
        logger.info(
            f"Successfully connected to Notion API! Found {result_count} invoices in database."
        )
        return True
    except Exception as e:
        logger.error(f"Failed to connect to Notion API: {e}")
        return False


def run_tests() -> None:
    """Run all connection tests."""
    # Validate configuration
    missing_config = Config.validate()
    if missing_config:
        logger.error("Missing configuration variables:")
        for var, message in missing_config.items():
            logger.error(f"  - {var}: {message}")
        logger.error("Please set these variables in your .env file and try again.")
        return

    # Test Stripe connection
    stripe_success = _test_stripe_connection()

    # Test Notion connection
    notion_success = _test_notion_connection()

    # Print summary
    logger.info("\n--- Connection Test Summary ---")
    logger.info(f"Stripe API: {'✅ Connected' if stripe_success else '❌ Failed'}")
    logger.info(f"Notion API: {'✅ Connected' if notion_success else '❌ Failed'}")

    if stripe_success and notion_success:
        logger.info(
            "\nAll connections successful! You can now create an invoice in Stripe to test the webhook."
        )
    else:
        logger.info(
            "\nSome connections failed. Please check your configuration and try again."
        )


if __name__ == "__main__":
    run_tests()
