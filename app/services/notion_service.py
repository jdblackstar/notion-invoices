"""Service for interacting with the Notion API."""

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import logfire
from notion_client import APIResponseError, Client
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import Config
from app.models.invoice import Invoice, InvoiceStatus, NotionInvoice

# Configure logger
logger = logfire.getLogger(__name__)


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


def _extract_stripe_id_from_url(url: Optional[str]) -> Optional[str]:
    """
    Extract the Stripe invoice ID from a Stripe URL.

    Args:
        url: Stripe URL

    Returns:
        Optional[str]: Stripe invoice ID if found, None otherwise
    """
    if not url:
        return None

    # Match pattern like in_1R4aLkJSWV99SGLXxmzRkl7z
    match = re.search(r"invoices/([^/]+)(?:\?|$)", url)
    if match:
        return match.group(1)
    return None


class NotionService:
    """Service for interacting with Notion API."""

    def __init__(self):
        """Initialize the Notion client with API key."""
        self.client = Client(auth=Config.NOTION_INTEGRATION_SECRET)
        # Format database IDs
        self.invoice_db_id = _format_notion_id(Config.NOTION_INVOICES_DATABASE_ID)
        self.client_db_id = _format_notion_id(Config.NOTION_CLIENTS_DATABASE_ID)

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def _make_api_request(self, func, *args, **kwargs) -> Dict:
        """
        Make a request to Notion API with retry logic.

        Args:
            func: Notion API function to call
            *args: Arguments to pass to the function
            **kwargs: Keyword arguments to pass to the function

        Returns:
            Dict: API response

        Raises:
            APIResponseError: If the API request fails after retries
        """
        try:
            return func(*args, **kwargs)
        except APIResponseError as e:
            logger.error("Error calling Notion API", error=str(e))
            raise

    def query_invoice_by_stripe_id(self, stripe_id: str) -> Optional[NotionInvoice]:
        """
        Query Notion database for an invoice with the given Stripe ID.

        Args:
            stripe_id: Stripe invoice ID

        Returns:
            Optional[NotionInvoice]: Notion invoice if found, None otherwise
        """
        with logfire.span("query_invoice_by_stripe_id", stripe_id=stripe_id):
            try:
                # Since we don't have a direct Stripe ID field, we have to search all records
                # and then filter by URL if it contains the ID
                response = self._make_api_request(
                    self.client.databases.query,
                    database_id=self.invoice_db_id,
                    page_size=100,
                )

                results = response.get("results", [])
                if not results:
                    return None

                # Find pages where the Stripe link contains the stripe_id
                matching_pages = []
                for page in results:
                    props = page.get("properties", {})
                    stripe_link = self._extract_url_property(
                        props.get("Stripe link", {})
                    )

                    # Extract the Stripe ID from the URL
                    url_stripe_id = _extract_stripe_id_from_url(stripe_link)

                    # If the ID matches, consider it a match
                    if url_stripe_id and url_stripe_id == stripe_id:
                        matching_pages.append(page)

                if not matching_pages:
                    return None

                # Get the first matching result
                page = matching_pages[0]
                return self._page_to_notion_invoice(page)
            except Exception as e:
                logger.error(
                    "Error querying invoice with Stripe ID",
                    stripe_id=stripe_id,
                    error=str(e),
                )
                return None

    def query_invoice_by_notion_id(self, notion_id: str) -> Optional[NotionInvoice]:
        """
        Query Notion database for invoice with specific Notion page ID.

        Args:
            notion_id: Notion page ID

        Returns:
            Optional[NotionInvoice]: Matching invoice if found, None otherwise
        """
        with logfire.span("query_invoice_by_notion_id", notion_id=notion_id):
            try:
                # Format the ID if needed
                notion_id = _format_notion_id(notion_id)

                # Get the page from Notion
                page = self._make_api_request(
                    self.client.pages.retrieve, page_id=notion_id
                )

                # Convert to NotionInvoice model
                return self._page_to_notion_invoice(page)
            except APIResponseError as e:
                if e.code == "object_not_found":
                    logger.warning(
                        "Invoice with Notion ID not found", notion_id=notion_id
                    )
                    return None
                logger.error(
                    "Error querying invoice with Notion ID",
                    notion_id=notion_id,
                    error=str(e),
                )
                return None
            except Exception as e:
                logger.error(
                    "Error querying invoice with Notion ID",
                    notion_id=notion_id,
                    error=str(e),
                )
                return None

    def _page_to_notion_invoice(self, page: Dict) -> NotionInvoice:
        """
        Convert a Notion page to a NotionInvoice model.

        Args:
            page: Notion page object

        Returns:
            NotionInvoice: Converted NotionInvoice model
        """
        props = page.get("properties", {})

        # Extract the Stripe ID from the URL
        stripe_link = self._extract_url_property(props.get("Stripe link", {}))
        stripe_id = _extract_stripe_id_from_url(stripe_link)

        # Extract the billing period date range
        billing_period_start, billing_period_end = self._extract_date_range_property(
            props.get("Billing Period", {})
        )

        # Log the billing period extraction for debugging
        logger.info(
            "Extracted billing period from Notion",
            start=billing_period_start,
            end=billing_period_end,
        )

        return NotionInvoice(
            notion_id=page["id"],
            stripe_id=stripe_id,
            invoice_number=self._extract_title_property(
                props.get("Invoice Number", {})
            ),
            status=self._extract_status_property(props.get("Status", {})),
            amount=self._extract_number_property(props.get("Amount", {})),
            customer_id=self._extract_relation_property(props.get("Client", {})),
            finalized_date=self._extract_date_property(props.get("Finalized", {})),
            due_date=self._extract_date_property(props.get("Due Date", {})),
            memo=None,  # No memo field in the database
            billing_period_start=billing_period_start,
            billing_period_end=billing_period_end,
            last_edited_time=datetime.fromisoformat(
                page.get("last_edited_time", "").replace("Z", "+00:00")
            ),
        )

    def _extract_text_property(self, prop: Dict) -> Optional[str]:
        """Extract text value from Notion property."""
        if prop.get("type") == "rich_text":
            rich_text = prop.get("rich_text", [])
            if rich_text:
                return "".join(item.get("plain_text", "") for item in rich_text)
        return None

    def _extract_title_property(self, prop: Dict) -> Optional[str]:
        """Extract title value from Notion property."""
        if prop.get("type") == "title":
            title = prop.get("title", [])
            if title:
                return "".join(item.get("plain_text", "") for item in title)
        return None

    def _extract_number_property(self, prop: Dict) -> Optional[int]:
        """Extract number value from Notion property."""
        if prop.get("type") == "number":
            number = prop.get("number")
            return int(number * 100) if number is not None else None  # Convert to cents
        return None

    def _extract_select_property(self, prop: Dict) -> Optional[str]:
        """Extract select value from Notion property."""
        if prop.get("type") == "select":
            select = prop.get("select")
            if select:
                return select.get("name")
        return None

    def _extract_status_property(self, prop: Dict) -> Optional[str]:
        """Extract status value from Notion property."""
        if prop.get("type") == "status":
            status = prop.get("status")
            if status:
                return status.get("name")
        return None

    def _extract_date_property(self, prop: Dict) -> Optional[datetime]:
        """Extract date value from Notion property."""
        if prop.get("type") == "date":
            date = prop.get("date")
            if date and date.get("start"):
                return datetime.fromisoformat(date["start"].replace("Z", "+00:00"))
        return None

    def _extract_date_range_property(
        self, prop: Dict
    ) -> Tuple[Optional[datetime], Optional[datetime]]:
        """
        Extract date range (start and end) from Notion date property.

        Args:
            prop: Notion date property

        Returns:
            Tuple[Optional[datetime], Optional[datetime]]: Start and end dates
        """
        start_date = None
        end_date = None

        try:
            logger.info("Extracting date range from property", property=prop)

            if prop.get("type") == "date":
                date = prop.get("date")
                logger.info("Date property content", date=date)

                if date:
                    if date.get("start"):
                        start_str = date["start"]
                        logger.info("Found start date string", start_str=start_str)
                        start_date = datetime.fromisoformat(
                            start_str.replace("Z", "+00:00")
                        )
                        logger.info("Parsed start date", start_date=start_date)

                    if date.get("end"):
                        end_str = date["end"]
                        logger.info("Found end date string", end_str=end_str)
                        end_date = datetime.fromisoformat(
                            end_str.replace("Z", "+00:00")
                        )
                        logger.info("Parsed end date", end_date=end_date)
            else:
                logger.info("Property is not a date type", type=prop.get("type"))

            logger.info("Final extracted date range", start=start_date, end=end_date)
        except Exception as e:
            logger.error("Error extracting date range", error=str(e), exc_info=True)

        return start_date, end_date

    def _extract_url_property(self, prop: Dict) -> Optional[str]:
        """Extract URL value from Notion property."""
        if prop.get("type") == "url":
            return prop.get("url")
        return None

    def _extract_relation_property(self, prop: Dict) -> Optional[str]:
        """Extract relation ID from Notion property."""
        if prop.get("type") == "relation":
            relations = prop.get("relation", [])
            if relations:
                # Just return the first relation ID
                return relations[0].get("id")
        return None

    def create_or_update_invoice(self, invoice: Invoice) -> Optional[str]:
        """
        Create or update an invoice in Notion.

        Args:
            invoice: Invoice model

        Returns:
            Optional[str]: Notion page ID if successful, None otherwise
        """
        with logfire.span("create_or_update_invoice", invoice_id=invoice.id):
            try:
                # Check if invoice already exists by looking up Stripe ID
                existing_invoice = None
                if invoice.id:
                    existing_invoice = self.query_invoice_by_stripe_id(invoice.id)

                if existing_invoice:
                    # Update existing invoice
                    page_id = existing_invoice.notion_id
                    logger.info(
                        "Updating existing invoice in Notion",
                        stripe_id=invoice.id,
                        notion_id=page_id,
                    )
                    self._make_api_request(
                        self.client.pages.update,
                        page_id=page_id,
                        properties=self._invoice_to_notion_properties(invoice),
                    )
                    return page_id
                else:
                    # Create new invoice using template if configured
                    logger.info("Creating new invoice in Notion", stripe_id=invoice.id)
                    if Config.NOTION_INVOICE_TEMPLATE_ID:
                        return self._create_invoice_from_template(invoice)
                    else:
                        # Create new invoice directly in database
                        response = self._make_api_request(
                            self.client.pages.create,
                            parent={"database_id": self.invoice_db_id},
                            properties=self._invoice_to_notion_properties(invoice),
                        )
                        return response["id"]
            except Exception as e:
                logger.error(
                    "Error creating/updating invoice in Notion",
                    invoice_id=invoice.id,
                    error=str(e),
                )
                return None

    def _create_invoice_from_template(self, invoice: Invoice) -> Optional[str]:
        """
        Create a new invoice page by duplicating a template.

        Args:
            invoice: Invoice model

        Returns:
            Optional[str]: Notion page ID if successful, None otherwise
        """
        with logfire.span("create_invoice_from_template", invoice_id=invoice.id):
            try:
                # Format the template ID
                template_id = _format_notion_id(Config.NOTION_INVOICE_TEMPLATE_ID)

                logger.info(
                    "Creating invoice from template",
                    invoice_id=invoice.id,
                    template_id=template_id,
                )

                # Create a new page in the database
                properties = self._invoice_to_notion_properties(invoice)

                # Create a new page in the database with properties from the invoice
                new_page = self._make_api_request(
                    self.client.pages.create,
                    parent={"database_id": self.invoice_db_id},
                    properties=properties,
                )

                new_page_id = new_page["id"]
                logger.info("Created new page", page_id=new_page_id)

                # Get the template's content blocks
                template_blocks = self._make_api_request(
                    self.client.blocks.children.list, block_id=template_id
                ).get("results", [])

                if template_blocks:
                    logger.info(
                        "Copying blocks from template to new page",
                        block_count=len(template_blocks),
                        template_id=template_id,
                        page_id=new_page_id,
                    )

                    # Convert the blocks to a format suitable for creating
                    blocks_to_create = self._prepare_blocks_for_copy(template_blocks)

                    # Add the template blocks to the new page
                    if blocks_to_create:
                        self._make_api_request(
                            self.client.blocks.children.append,
                            block_id=new_page_id,
                            children=blocks_to_create,
                        )

                return new_page_id
            except Exception as e:
                logger.error(
                    "Error creating invoice from template",
                    invoice_id=invoice.id,
                    error=str(e),
                    exc_info=True,
                )

                # Fallback to regular creation
                return self._create_invoice_without_template(invoice)

    def _prepare_blocks_for_copy(self, blocks: List[Dict]) -> List[Dict]:
        """
        Prepare blocks for copying by removing Notion-specific IDs.

        Args:
            blocks: List of Notion blocks

        Returns:
            List[Dict]: Blocks ready for creation
        """
        prepared_blocks = []

        for block in blocks:
            # Skip if no type
            if "type" not in block:
                continue

            block_type = block["type"]

            # Create a new block with the same type and content
            new_block = {
                "object": "block",
                "type": block_type,
                block_type: block[block_type],
            }

            # Remove any IDs from the content
            if "id" in new_block[block_type]:
                del new_block[block_type]["id"]

            prepared_blocks.append(new_block)

        return prepared_blocks

    def _create_invoice_without_template(self, invoice: Invoice) -> Optional[str]:
        """
        Create a new invoice page directly without using a template.

        Args:
            invoice: Invoice model

        Returns:
            Optional[str]: Notion page ID if successful, None otherwise
        """
        try:
            logger.info("Creating invoice without template", invoice_id=invoice.id)
            # Create new invoice directly in database
            response = self._make_api_request(
                self.client.pages.create,
                parent={"database_id": self.invoice_db_id},
                properties=self._invoice_to_notion_properties(invoice),
            )
            return response["id"]
        except Exception as e:
            logger.error(
                "Error creating invoice without template",
                invoice_id=invoice.id,
                error=str(e),
            )
            return None

    def _invoice_to_notion_properties(self, invoice: Invoice) -> Dict[str, Any]:
        """
        Convert an Invoice model to Notion properties.

        Args:
            invoice: Invoice model

        Returns:
            Dict[str, Any]: Notion properties
        """
        # Map Stripe statuses to Notion status values
        status_map = {
            InvoiceStatus.DRAFT: "Draft",
            InvoiceStatus.OPEN: "Pending",  # Notion uses "Pending" instead of "Open"
            InvoiceStatus.PAID: "Paid",
            InvoiceStatus.UNCOLLECTIBLE: "Void",  # Map to closest equivalent
            InvoiceStatus.VOID: "Void",
        }

        properties = {
            "Status": {"status": {"name": status_map.get(invoice.status, "Draft")}},
            "Amount": {
                "number": invoice.amount / 100  # Convert from cents
            },
            "Stripe link": {
                "url": f"https://dashboard.stripe.com/invoices/{invoice.id}"
            },
            # Always set the title/Invoice Number, using invoice number if available, otherwise use Stripe ID
            "Invoice Number": {
                "title": [{"text": {"content": invoice.invoice_number or invoice.id}}]
            },
        }

        if invoice.finalized_date:
            properties["Finalized"] = {
                "date": {"start": invoice.finalized_date.isoformat()}
            }

        if invoice.due_date:
            properties["Due Date"] = {"date": {"start": invoice.due_date.isoformat()}}

        # Handle billing period as a date range if both start and end are provided
        if invoice.billing_period_start:
            date_prop = {"start": invoice.billing_period_start.isoformat()}

            # If end date is provided, add it to the range
            if invoice.billing_period_end:
                date_prop["end"] = invoice.billing_period_end.isoformat()

            properties["Billing Period"] = {"date": date_prop}

        # Handle client relation if it exists
        if invoice.customer_id:
            # Would need to look up the relation page ID for this customer
            # This is a placeholder - we'd need a proper lookup
            # properties["Client"] = {
            #     "relation": [{"id": client_page_id}]
            # }
            pass

        return properties

    def get_customer_by_stripe_id(self, stripe_id: str) -> Optional[Dict]:
        """
        Get a customer from Notion by Stripe ID.

        Args:
            stripe_id: Stripe customer ID

        Returns:
            Optional[Dict]: Customer data if found, None otherwise
        """
        with logfire.span("get_customer_by_stripe_id", stripe_id=stripe_id):
            try:
                # This would need to be customized based on your clients database structure
                # Similar to how we're handling the invoice lookup
                return None
            except Exception as e:
                logger.error(
                    "Error getting customer with Stripe ID",
                    stripe_id=stripe_id,
                    error=str(e),
                )
                return None

    def delete_invoice_by_stripe_id(self, stripe_id: str) -> bool:
        """
        Delete an invoice from Notion by Stripe ID.

        Args:
            stripe_id: Stripe invoice ID

        Returns:
            bool: True if successful, False otherwise
        """
        with logfire.span("delete_invoice_by_stripe_id", stripe_id=stripe_id):
            try:
                logger.info(
                    "Attempting to delete invoice from Notion", stripe_id=stripe_id
                )

                # Query for the invoice
                existing_invoice = self.query_invoice_by_stripe_id(stripe_id)

                if not existing_invoice:
                    logger.warning(
                        "Invoice not found in Notion - nothing to delete",
                        stripe_id=stripe_id,
                    )
                    return False

                logger.info(
                    "Found invoice to delete",
                    notion_id=existing_invoice.notion_id,
                    invoice_number=existing_invoice.invoice_number,
                )

                # Archive the page in Notion (soft delete)
                response = self._make_api_request(
                    self.client.pages.update,
                    page_id=existing_invoice.notion_id,
                    archived=True,
                )

                # Log the response status
                logger.info(
                    "Notion API response for deletion",
                    archived=response.get("archived", False),
                )

                logger.info(
                    "Successfully deleted invoice from Notion", stripe_id=stripe_id
                )
                return True
            except Exception as e:
                logger.error(
                    "Error deleting invoice from Notion",
                    stripe_id=stripe_id,
                    error=str(e),
                    exc_info=True,
                )
                return False

    def get_recently_updated_invoices(self, hours_back: int = 1) -> List[NotionInvoice]:
        """
        Get recently updated invoices from Notion.

        Args:
            hours_back: Number of hours back to check for updates

        Returns:
            List[NotionInvoice]: List of recently updated invoices
        """
        with logfire.span("get_recently_updated_invoices", hours_back=hours_back):
            try:
                logger.info(
                    "Querying for recently updated invoices", hours_back=hours_back
                )

                # Get all invoices from the database
                response = self._make_api_request(
                    self.client.databases.query,
                    database_id=self.invoice_db_id,
                    page_size=100,
                )

                results = response.get("results", [])
                if not results:
                    logger.info("No invoices found in Notion database")
                    return []

                # Calculate the cutoff time with timezone awareness for proper comparison
                cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
                logger.info("Using cutoff time", cutoff_time=cutoff_time)

                # Filter pages by last edit time
                recent_pages = []
                for page in results:
                    try:
                        last_edited_time = datetime.fromisoformat(
                            page.get("last_edited_time", "").replace("Z", "+00:00")
                        )
                        logger.info(
                            "Checking page last edited time",
                            page_id=page.get("id", "unknown"),
                            last_edited_time=last_edited_time,
                        )

                        # Now both datetimes are timezone-aware, so comparison will work
                        if last_edited_time > cutoff_time:
                            recent_pages.append(page)
                            logger.info(
                                "Added page to recent pages",
                                page_id=page.get("id", "unknown"),
                            )
                        else:
                            logger.info(
                                "Skipped page (edited before cutoff)",
                                page_id=page.get("id", "unknown"),
                            )
                    except (ValueError, TypeError) as e:
                        logger.error(
                            "Error parsing last_edited_time",
                            page_id=page.get("id", "unknown"),
                            error=str(e),
                        )
                        continue

                logger.info(
                    "Found recently updated pages in Notion", count=len(recent_pages)
                )

                # Convert pages to NotionInvoice models
                invoices = []
                for page in recent_pages:
                    try:
                        invoice = self._page_to_notion_invoice(page)
                        if invoice and invoice.stripe_id:
                            invoices.append(invoice)
                            logger.info(
                                "Added invoice to results",
                                notion_id=invoice.notion_id,
                                stripe_id=invoice.stripe_id,
                            )
                        else:
                            if not invoice:
                                logger.warning(
                                    "Failed to convert page to invoice",
                                    page_id=page.get("id", "unknown"),
                                )
                            else:
                                logger.warning(
                                    "Invoice has no Stripe ID, skipping",
                                    notion_id=invoice.notion_id,
                                )
                    except Exception as e:
                        logger.error("Error converting page to invoice", error=str(e))

                logger.info(
                    "Converted valid invoices with Stripe IDs", count=len(invoices)
                )
                return invoices
            except Exception as e:
                logger.error(
                    "Error getting recently updated invoices",
                    error=str(e),
                    exc_info=True,
                )
                return []
