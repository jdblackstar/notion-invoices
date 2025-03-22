"""Script to inspect Notion database structure."""

import logging
import sys

from notion_client import Client

from app.config import Config
from app.services.notion_service import _format_notion_id

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


def inspect_database(database_id: str) -> None:
    """
    Inspect a Notion database to show its structure.

    Args:
        database_id: ID of the Notion database to inspect
    """
    client = Client(auth=Config.NOTION_INTEGRATION_SECRET)

    # Format the database ID
    db_id = _format_notion_id(database_id)

    try:
        # Get database details
        logger.info(f"Fetching database with ID: {db_id}")
        database = client.databases.retrieve(database_id=db_id)

        # Extract properties
        properties = database.get("properties", {})

        logger.info(
            f"Database title: {database.get('title', [{}])[0].get('plain_text', 'Unnamed')}"
        )
        logger.info(f"Found {len(properties)} properties:")

        # Print each property and its type
        for name, details in properties.items():
            prop_type = details.get("type", "unknown")
            logger.info(f"  - {name} (Type: {prop_type})")

            # For select properties, show options
            if prop_type == "select" or prop_type == "status":
                options = details.get(prop_type, {}).get("options", [])
                option_names = [option.get("name", "") for option in options]
                logger.info(f"    Options: {', '.join(option_names)}")

        # Query to get a sample page
        logger.info("\nFetching a sample page to inspect data:")
        query_result = client.databases.query(database_id=db_id, page_size=1)

        pages = query_result.get("results", [])
        if pages:
            sample_page = pages[0]
            page_id = sample_page.get("id")
            logger.info(f"Sample page ID: {page_id}")

            # Extract title
            title_prop_name = None
            for name, details in properties.items():
                if details.get("type") == "title":
                    title_prop_name = name
                    break

            if title_prop_name:
                title_prop = sample_page.get("properties", {}).get(title_prop_name, {})
                title_text = []

                if title_prop.get("type") == "title":
                    for text_item in title_prop.get("title", []):
                        text = text_item.get("plain_text", "")
                        title_text.append(text)

                title_value = "".join(title_text)
                logger.info(f"Title ({title_prop_name}): {title_value}")

            # Show all properties with their values
            logger.info("\nAll properties and values:")
            for prop_name, prop_value in sample_page.get("properties", {}).items():
                prop_type = prop_value.get("type")
                logger.info(f"  - {prop_name} ({prop_type}):")

                if prop_type == "title":
                    texts = [
                        item.get("plain_text", "")
                        for item in prop_value.get("title", [])
                    ]
                    logger.info(f"    Value: {''.join(texts)}")
                elif prop_type == "rich_text":
                    texts = [
                        item.get("plain_text", "")
                        for item in prop_value.get("rich_text", [])
                    ]
                    logger.info(f"    Value: {''.join(texts)}")
                elif prop_type == "number":
                    logger.info(f"    Value: {prop_value.get('number')}")
                elif prop_type == "select":
                    select_value = prop_value.get("select", {})
                    logger.info(
                        f"    Value: {select_value.get('name') if select_value else 'None'}"
                    )
                elif prop_type == "status":
                    status_value = prop_value.get("status", {})
                    logger.info(
                        f"    Value: {status_value.get('name') if status_value else 'None'}"
                    )
                elif prop_type == "date":
                    date_value = prop_value.get("date", {})
                    logger.info(
                        f"    Value: {date_value.get('start') if date_value else 'None'}"
                    )
                elif prop_type == "url":
                    logger.info(f"    Value: {prop_value.get('url')}")
                elif prop_type == "relation":
                    relations = prop_value.get("relation", [])
                    relation_ids = [rel.get("id") for rel in relations]
                    logger.info(f"    Value: {relation_ids}")
                else:
                    logger.info(f"    Raw value: {prop_value}")
        else:
            logger.info("No pages found in the database.")

        logger.info(
            "\nTo use these properties in your code, update the property names in notion_service.py"
        )
    except Exception as e:
        logger.error(f"Error inspecting database: {e}")
        import traceback

        logger.error(traceback.format_exc())


if __name__ == "__main__":
    # Check which database to inspect
    if len(sys.argv) > 1 and sys.argv[1] == "clients":
        inspect_database(Config.NOTION_CLIENTS_DATABASE_ID)
    else:
        inspect_database(Config.NOTION_INVOICES_DATABASE_ID)
