#!/usr/bin/env python3
import asyncio
import os
import logging
from typing import Optional, Tuple, Dict, Any
import socket

import aiohttp
from onepassword.client import Client
import ssl
import certifi

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

CF_API_KEY_REF="op://Services/CF DNS API/credential"
CF_HOST_REF="op://Services/CF DNS API/hostname"
CF_ZONE_ID_REF="op://Services/CF DNS API/zone_id"
CF_URL='https://speed.cloudflare.com/meta'

class CloudflareDNS:
    """
    A class to handle Cloudflare DNS record updates using a single session.
    """
    def __init__(self, cf_api_token: str, zone_id: str, record_name: str):
        """Initialize the CloudflareDNSUpdater with Cloudflare credentials."""
        self.cf_api_token = cf_api_token
        self.zone_id = zone_id
        self.record_name = record_name
        self.session = None
        self.headers = {
            "Authorization": f"Bearer {self.cf_api_token}",
            "Content-Type": "application/json"
        }
    
    async def __aenter__(self):
        """Set up the aiohttp session when entering an async context."""
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        self.session = aiohttp.ClientSession(connector=connector)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close the aiohttp session when exiting the async context."""
        if self.session:
            await self.session.close()
            self.session = None
    
    async def get_my_ip(self) -> Optional[str]:
        """Get the current public IP address using Cloudflare's Speed Test API."""
        try:
            async with self.session.get("https://speed.cloudflare.com/meta") as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("clientIp")
                else:
                    logger.error(f"Failed to get IP: HTTP {response.status}")
        except Exception as e:
            logger.error(f"Error getting IP: {str(e)}")
    
    async def find_dns_record_id(self) -> Optional[str]:
        """Find the ID of a DNS record by its name."""
        try:
            # List all DNS records in the zone
            url = f"https://api.cloudflare.com/client/v4/zones/{self.zone_id}/dns_records"
            params = {"name": self.record_name}
            
            async with self.session.get(url, headers=self.headers, params=params) as response:
                result = await response.json()
                
                if response.status == 200 and result.get("success"):
                    records = result.get("result", [])
                    
                    if not records:
                        logger.warning(f"No DNS records found with name {self.record_name}")
                        return None
                    
                    # Find the A record with the matching name
                    for record in records:
                        if record.get("type") == "A" and record.get("name") == self.record_name:
                            record_id = record.get("id")
                            logger.info(f"Found DNS record ID for {self.record_name}: {record_id}")
                            return record_id
                    
                    logger.warning(f"No matching A record found for {self.record_name}")
                    return None
                else:
                    error_messages = result.get("errors", [{"message": "Unknown error"}])
                    logger.error(f"Failed to list DNS records: {error_messages[0].get('message')}")
                    return None
        except Exception as e:
            logger.error(f"Error finding DNS record: {str(e)}")
            return None
    
    async def update_dns_record(self, ip_address: str, record_id: Optional[str] = None) -> bool:
        """
        Update a DNS record in Cloudflare with the given IP address.
        If record_id is not provided, it will create a new record.
        """
        data = {
            "type": "A",
            "name": self.record_name,
            "content": ip_address,
            "ttl": 1,  # Auto
            "proxied": False
        }

        try:
            if record_id:
                # Update existing record
                url = f"https://api.cloudflare.com/client/v4/zones/{self.zone_id}/dns_records/{record_id}"
                async with self.session.put(url, headers=self.headers, json=data) as response:
                    result = await response.json()
                    
                    if response.status == 200 and result.get("success"):
                        logger.info(f"Successfully updated DNS record to {ip_address}")
                        return True
                    else:
                        error_messages = result.get("errors", [{"message": "Unknown error"}])
                        logger.error(f"Failed to update DNS record: {error_messages[0].get('message')}")
                        return False
            else:
                # Create new record
                url = f"https://api.cloudflare.com/client/v4/zones/{self.zone_id}/dns_records"
                async with self.session.post(url, headers=self.headers, json=data) as response:
                    result = await response.json()
                    
                    if response.status == 200 and result.get("success"):
                        logger.info(f"Successfully created new DNS record for {self.record_name} with IP {ip_address}")
                        return True
                    else:
                        error_messages = result.get("errors", [{"message": "Unknown error"}])
                        logger.error(f"Failed to create DNS record: {error_messages[0].get('message')}")
                        return False
        except Exception as e:
            logger.error(f"Error updating DNS record: {str(e)}")
            return False

    async def verify_dns_update(self, expected_ip: str) -> bool:
        """Verify that the DNS record was properly updated by resolving it."""
        try:
            # Allow some time for DNS propagation
            await asyncio.sleep(5)
            
            # Resolve the DNS
            resolved_ip = socket.gethostbyname(self.record_name)
            
            if resolved_ip == expected_ip:
                logger.info(f"DNS verification successful: {self.record_name} resolves to {resolved_ip}")
                return True
            else:
                logger.warning(f"DNS verification failed: {self.record_name} resolves to {resolved_ip}, expected {expected_ip}")
                return False
        except socket.gaierror:
            logger.error(f"DNS resolution failed for {self.record_name}")
            return False

async def main():
    token = os.getenv("OP_SERVICE_ACCOUNT_TOKEN")
    client = await Client.authenticate(auth=token, integration_name="cfupdater", integration_version="1.0")
    CF_API_KEY = await client.secrets.resolve(CF_API_KEY_REF)
    CF_ZONE_ID = await client.secrets.resolve(CF_ZONE_ID_REF)
    CF_DNS_RECORD = await client.secrets.resolve(CF_HOST_REF)
    # Validate required configuration
    if not all([CF_API_KEY, CF_ZONE_ID, CF_DNS_RECORD]):
        logger.error("Please set CF_API_TOKEN, CF_ZONE_ID, and CF_RECORD_NAME")
        return
    
    # Create and run the Cloudflare DNS updater
    async with CloudflareDNS(CF_API_KEY, CF_ZONE_ID, CF_DNS_RECORD) as updater:
        ip_address = await updater.get_my_ip()
        
        if not ip_address:
            logger.error("Failed to get current IP address. Exiting.")
            return
        
        logger.info(f"Current IP address: {ip_address}")
        
        # Find the DNS record ID
        record_id = await updater.find_dns_record_id()
        
        # Update or create the DNS record
        if record_id:
            logger.info(f"Updating existing DNS record with ID: {record_id}")
            success = await updater.update_dns_record(ip_address, record_id)
        else:
            logger.info(f"No existing record found. Creating a new DNS record for {CF_DNS_RECORD}")
            success = await updater.update_dns_record(ip_address)
        
        if success:
            # Verify the DNS update (optional)
            await updater.verify_dns_update(ip_address)
    
if __name__ == "__main__":
    asyncio.run(main())
