CF_URL='https://speed.cloudflare.com/meta'
import requests
import ssl
import certifi
import logging
from typing import Optional, Tuple, Dict, Any
import socket
import time

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

class CloudflareDNS:
    """
    A class to handle Cloudflare DNS record updates using requests.
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
    
    def __enter__(self):
        """Set up the requests session when entering a context."""
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        # Configure SSL verification
        self.session.verify = certifi.where()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Close the requests session when exiting the context."""
        if self.session:
            self.session.close()
            self.session = None
    
    def get_my_ip(self) -> Optional[str]:
        """Get the current public IP address using Cloudflare's Speed Test API."""
        try:
            response = self.session.get(CF_URL, timeout=30)
            if response.status_code == 200:
                data = response.json()
                return data.get("clientIp")
            else:
                logger.error(f"Failed to get IP: HTTP {response.status_code}")
        except Exception as e:
            logger.error(f"Error getting IP: {str(e)}")
        return None
    
    def find_dns_record_id(self) -> Optional[str]:
        """Find the ID of a DNS record by its name."""
        try:
            # List all DNS records in the zone
            url = f"https://api.cloudflare.com/client/v4/zones/{self.zone_id}/dns_records"
            params = {"name": self.record_name}
            
            response = self.session.get(url, params=params, timeout=30)
            result = response.json()
            
            if response.status_code == 200 and result.get("success"):
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
    
    def update_dns_record(self, ip_address: str, record_id: Optional[str] = None) -> bool:
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
                response = self.session.put(url, json=data, timeout=30)
                result = response.json()
                
                if response.status_code == 200 and result.get("success"):
                    logger.info(f"Successfully updated DNS record to {ip_address}")
                    return True
                else:
                    error_messages = result.get("errors", [{"message": "Unknown error"}])
                    logger.error(f"Failed to update DNS record: {error_messages[0].get('message')}")
                    return False
            else:
                # Create new record
                url = f"https://api.cloudflare.com/client/v4/zones/{self.zone_id}/dns_records"
                response = self.session.post(url, json=data, timeout=30)
                result = response.json()
                
                if response.status_code == 200 and result.get("success"):
                    logger.info(f"Successfully created new DNS record for {self.record_name} with IP {ip_address}")
                    return True
                else:
                    error_messages = result.get("errors", [{"message": "Unknown error"}])
                    logger.error(f"Failed to create DNS record: {error_messages[0].get('message')}")
                    return False
        except Exception as e:
            logger.error(f"Error updating DNS record: {str(e)}")
            return False

    def verify_dns_update(self, expected_ip: str) -> bool:
        """Verify that the DNS record was properly updated by resolving it."""
        try:
            # Allow some time for DNS propagation
            time.sleep(5)
            
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
