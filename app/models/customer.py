"""Customer data models."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Customer(BaseModel):
    """Customer data model."""

    # shared fields
    name: str = Field(..., description="The customer name")
    stripe_id: str = Field(..., description="The customer Stripe ID")
    ap_contact_email: str = Field(..., description="The email of the AP contact")
    main_contact_email: str = Field(..., description="The email of the main contact")

    # Notion fields
    notion_id: Optional[str] = Field(None, description="The Notion page ID")
    total_spend: Optional[float] = Field(
        None, description="The total spend of the customer, sums all paid invoices"
    )
    ytd_spend: Optional[float] = Field(
        None,
        description="The YTD spend of the customer, sums all paid invoices from the start of the year to the current date",
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


class StripeCustomer(BaseModel):
    """Stripe customer data model."""

    id: str = Field(..., description="The customer ID")
    name: str = Field(..., description="The name of the customer, matched with Notion")
    created: int = Field(
        ..., description="The timestamp of when the customer was created"
    )
    email: str = Field(..., description="The email of the customer")
    invoice_prefix: str = Field(
        ..., description="The prefix of the customer's invoices"
    )

    def to_customer_model(self) -> Customer:
        """Convert Stripe customer to shared Customer model."""
        return Customer(
            name=self.name,
            stripe_id=self.id,
            ap_contact_email=self.email,
            main_contact_email=self.email,  # Default to same email if no specific main contact
            stripe_updated_at=datetime.fromtimestamp(self.created),
        )


class NotionCustomer(BaseModel):
    """Notion customer data model (called a client in Notion)."""

    id: str = Field(..., description="The Notion page ID")
    title: str = Field(..., description="The name of the customer, matched with Stripe")
    main_contact_email: str = Field(..., description="The email of the main contact")
    ap_contact_email: str = Field(..., description="The email of the AP contact")
    total_spend: float = Field(
        ..., description="The total spend of the customer, sums all paid invoices"
    )
    ytd_spend: float = Field(
        ...,
        description="The YTD spend of the customer, sums all paid invoices from the start of the year to the current date",
    )

    def to_customer_model(self) -> Customer:
        """Convert Notion customer to shared Customer model."""
        return Customer(
            name=self.title,
            notion_id=self.id,
            stripe_id="",  # This needs to be provided from elsewhere
            ap_contact_email=self.ap_contact_email,
            main_contact_email=self.main_contact_email,
            total_spend=self.total_spend,
            ytd_spend=self.ytd_spend,
            notion_updated_at=datetime.now(),
        )
