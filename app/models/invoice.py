"""Invoice data models."""

from datetime import datetime
from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel, Field


class InvoiceStatus(str, Enum):
    """Status of an invoice in the system."""

    DRAFT = "draft"
    OPEN = "open"
    PAID = "paid"
    UNCOLLECTIBLE = "uncollectible"
    VOID = "void"
    DELETED = "deleted"


class Invoice(BaseModel):
    """
    Invoice model representing data shared between Stripe and Notion.

    This model contains fields synced between systems and tracks
    the source of truth for each field.
    """

    # Shared identifiers
    id: str = Field(..., description="Stripe invoice ID")
    invoice_number: Optional[str] = Field(None, description="Invoice number")

    # Core invoice data
    status: InvoiceStatus = Field(..., description="Current status of the invoice")
    amount: int = Field(..., description="Total amount in cents")
    finalized_date: Optional[datetime] = Field(
        None, description="Date when invoice was finalized"
    )
    due_date: Optional[datetime] = Field(None, description="Date when payment is due")
    memo: Optional[str] = Field(None, description="Invoice memo or description")

    # Customer data
    customer_id: str = Field(..., description="Stripe customer ID")

    # Notion-specific fields
    notion_id: Optional[str] = Field(
        None, description="Notion page ID for this invoice"
    )
    billing_period_start: Optional[datetime] = Field(
        None, description="Billing period start date"
    )
    billing_period_end: Optional[datetime] = Field(
        None, description="Billing period end date"
    )

    # Metadata and sync information
    last_synced_at: Optional[datetime] = Field(
        None, description="Timestamp of last successful sync"
    )
    stripe_updated_at: Optional[datetime] = Field(
        None, description="Last update timestamp from Stripe"
    )
    notion_updated_at: Optional[datetime] = Field(
        None, description="Last update timestamp from Notion"
    )

    @property
    def billing_period(self) -> Optional[datetime]:
        """For backward compatibility, return the start date as the billing period."""
        return self.billing_period_start

    class Config:
        """Pydantic model configuration."""

        json_encoders = {
            datetime: lambda dt: dt.isoformat() if dt else None,
        }


class StripeInvoice(BaseModel):
    """
    Raw Stripe invoice data model.

    Used for parsing webhook payloads and API responses from Stripe.
    Contains only the fields we care about for syncing.
    """

    id: str
    number: Optional[str] = None
    status: str
    customer: str
    amount_due: int
    amount_paid: int
    amount_remaining: int
    created: int  # Unix timestamp
    due_date: Optional[int] = None  # Unix timestamp
    finalized_at: Optional[int] = None  # Unix timestamp
    description: Optional[str] = None
    metadata: Dict[str, str] = Field(default_factory=dict)

    def to_invoice_model(self) -> Invoice:
        """
        Convert Stripe invoice to shared Invoice model.

        Returns:
            Invoice: Converted invoice model
        """
        status_map = {
            "draft": InvoiceStatus.DRAFT,
            "open": InvoiceStatus.OPEN,
            "paid": InvoiceStatus.PAID,
            "uncollectible": InvoiceStatus.UNCOLLECTIBLE,
            "void": InvoiceStatus.VOID,
        }

        # Generate a user-friendly invoice number if one is not provided by Stripe
        invoice_number = self.number
        if not invoice_number:
            # Extract the unique part of the Stripe ID (last 8 chars) and combine with status
            id_part = self.id.split("_")[-1][-8:].upper()
            status_suffix = "-DRAFT" if self.status == "draft" else ""
            invoice_number = f"{id_part}{status_suffix}"

        return Invoice(
            id=self.id,
            invoice_number=invoice_number,
            status=status_map.get(self.status, InvoiceStatus.DRAFT),
            amount=self.amount_due,
            customer_id=self.customer,
            finalized_date=datetime.fromtimestamp(self.finalized_at)
            if self.finalized_at
            else None,
            due_date=datetime.fromtimestamp(self.due_date) if self.due_date else None,
            memo=self.description,
            stripe_updated_at=datetime.now(),
            billing_period_start=None,
            billing_period_end=None,
        )


class NotionInvoice(BaseModel):
    """
    Notion invoice data model.

    Used for parsing Notion database entries and preparing updates.
    """

    notion_id: str
    stripe_id: Optional[str] = None
    invoice_number: Optional[str] = None
    status: Optional[str] = None
    amount: Optional[int] = None
    customer_id: Optional[str] = None
    finalized_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    memo: Optional[str] = None
    billing_period_start: Optional[datetime] = None
    billing_period_end: Optional[datetime] = None
    last_edited_time: Optional[datetime] = None

    @property
    def billing_period(self) -> Optional[datetime]:
        """For backward compatibility, return the start date as the billing period."""
        return self.billing_period_start

    def to_invoice_model(self) -> Invoice:
        """
        Convert Notion invoice to shared Invoice model.

        Returns:
            Invoice: Converted invoice model
        """
        # Map Notion statuses to our internal statuses
        status_map = {
            "Draft": InvoiceStatus.DRAFT,
            "Pending": InvoiceStatus.OPEN,  # "Pending" in Notion = "open" in Stripe
            "Paid": InvoiceStatus.PAID,
            "Void": InvoiceStatus.VOID,
        }

        return Invoice(
            id=self.stripe_id or "",
            notion_id=self.notion_id,
            invoice_number=self.invoice_number,
            status=status_map.get(self.status or "", InvoiceStatus.DRAFT),
            amount=self.amount or 0,
            customer_id=self.customer_id or "",
            finalized_date=self.finalized_date,
            due_date=self.due_date,
            memo=self.memo,
            billing_period_start=self.billing_period_start,
            billing_period_end=self.billing_period_end,
            notion_updated_at=datetime.now(),
        )
