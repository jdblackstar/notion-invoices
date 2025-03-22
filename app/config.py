"""Configuration management for the application."""

import os
from typing import Dict

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Application configuration loaded from environment variables."""

    # Stripe configuration
    STRIPE_API_KEY: str = os.getenv("STRIPE_API_KEY", "")
    STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")

    # Notion configuration
    NOTION_INTEGRATION_SECRET: str = os.getenv("NOTION_INTEGRATION_SECRET", "")
    NOTION_INVOICES_DATABASE_ID: str = os.getenv("NOTION_INVOICES_DATABASE_ID", "")
    NOTION_CLIENTS_DATABASE_ID: str = os.getenv("NOTION_CLIENTS_DATABASE_ID", "")
    NOTION_INVOICE_TEMPLATE_ID: str = os.getenv("NOTION_INVOICE_TEMPLATE_ID", "")

    # Application settings
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    SYNC_INTERVAL_SECONDS: int = int(os.getenv("SYNC_INTERVAL_SECONDS", "30"))

    @classmethod
    def validate(cls) -> Dict[str, str]:
        """
        Validate that all required configuration variables are set.

        Returns:
            Dict[str, str]: Dictionary of missing configuration variables and their descriptions
        """
        missing_vars: Dict[str, str] = {}

        if not cls.STRIPE_API_KEY:
            missing_vars["STRIPE_API_KEY"] = "Stripe API Key is required"

        if not cls.STRIPE_WEBHOOK_SECRET:
            missing_vars["STRIPE_WEBHOOK_SECRET"] = "Stripe Webhook Secret is required"

        if not cls.NOTION_INTEGRATION_SECRET:
            missing_vars["NOTION_INTEGRATION_SECRET"] = (
                "Notion Integration Secret is required"
            )

        if not cls.NOTION_INVOICES_DATABASE_ID:
            missing_vars["NOTION_INVOICES_DATABASE_ID"] = (
                "Notion Invoices Database ID is required"
            )

        if not cls.NOTION_CLIENTS_DATABASE_ID:
            missing_vars["NOTION_CLIENTS_DATABASE_ID"] = (
                "Notion Clients Database ID is required"
            )

        return missing_vars
