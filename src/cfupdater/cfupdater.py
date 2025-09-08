#!/usr/bin/env python3
import os
import logging
import time
import sched
from datetime import datetime
import argparse

from onepassword import Client
import asyncio

from .cfdns import CloudflareDNS

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

CF_API_KEY_REF="op://Services/CF DNS API/credential"
CF_HOST_REF="op://Services/CF DNS API/hostname"
CF_ZONE_ID_REF="op://Services/CF DNS API/zone_id"

async def get_secrets():
    token = os.getenv("OP_SERVICE_ACCOUNT_TOKEN")
    if not token:
        logger.error("OP_SERVICE_ACCOUNT_TOKEN unset")
        raise Exception("No OP service token provided")
    client = await Client.authenticate(auth=token, integration_name="cfupdater", integration_version="1.0")
    # Client(token=os.environ["OP_SERVICE_ACCOUNT_TOKEN"])

    CF_API_KEY = await client.secrets.resolve(CF_API_KEY_REF)
    CF_ZONE_ID = await client.secrets.resolve(CF_ZONE_ID_REF)
    CF_DNS_RECORD = await client.secrets.resolve(CF_HOST_REF)
    return (CF_API_KEY, CF_ZONE_ID, CF_DNS_RECORD)

def main(CF_API_KEY, CF_ZONE_ID, CF_DNS_RECORD):
    logger.info(f"[{datetime.now()}] Running scheduled CF update...")
    # Create and run the Cloudflare DNS updater
    with CloudflareDNS(CF_API_KEY, CF_ZONE_ID, CF_DNS_RECORD) as updater:
        ip_address = updater.get_my_ip()
        
        if not ip_address:
            logger.error("Failed to get current IP address. Exiting.")
            return
        
        logger.info(f"Current IP address: {ip_address}")
        
        # Find the DNS record ID
        record_id = updater.find_dns_record_id()
        
        # Update or create the DNS record
        if record_id:
            logger.info(f"Updating existing DNS record with ID: {record_id}")
            success = updater.update_dns_record(ip_address, record_id)
        else:
            logger.info(f"No existing record found. Creating a new DNS record for {CF_DNS_RECORD}")
            success = updater.update_dns_record(ip_address)
        
        if success:
            # Verify the DNS update (optional)
            updater.verify_dns_update(ip_address)
    
def get_interval_seconds(mode: str) -> int:
    return {
        "daily": 24 * 60 * 60,
        "hourly": 60 * 60,
        "min": 60,
    }.get(mode, 0)

def run(mode, num_runs):
    try:
        (CF_API_KEY, CF_ZONE_ID, CF_DNS_RECORD) = asyncio.run(get_secrets())
    except Exception as e:
        logger.fatal(f"Getting secrets raised Exception {e}")
        return
    # Validate required configuration
    if not all([CF_API_KEY, CF_ZONE_ID, CF_DNS_RECORD]):
        logger.fatal("Please set CF_API_TOKEN, CF_ZONE_ID, and CF_RECORD_NAME")
        return

    main(CF_API_KEY, CF_ZONE_ID, CF_DNS_RECORD)
    if not mode:
        return

    scheduler = sched.scheduler(time.time, time.sleep)
    runs_left = num_runs - 1  # Already ran once

    def schedule_next():
        if num_runs != 0 and runs_left <= 0:
            return
        interval = get_interval_seconds(mode)
        scheduler.enter(interval, 1, run_and_reschedule)

    def run_and_reschedule():
        nonlocal runs_left
        main(CF_API_KEY, CF_ZONE_ID, CF_DNS_RECORD)
        if num_runs == 0 or runs_left > 0:
            runs_left -= 1
            schedule_next()

    schedule_next()
    scheduler.run()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a scheduled task.")
    parser.add_argument(
        "--mode",
        choices=["daily", "hourly", "min"],
        help="Schedule the task to repeat. If omitted, runs only once.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="How many times to run the task (0 = infinite).",
    )

    args = parser.parse_args()
    run(args.mode, args.runs)
