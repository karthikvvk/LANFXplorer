import asyncio
import os
import sys

# Ensure local imports work
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from app_config import get_config
from pki.ca_service import CAManager

async def main():
    config = get_config()
    recivhost = config.reciv_host or "0.0.0.0"
    ca_ip = config.host or recivhost
    
    print("====================================")
    print("   Testing CA Peer Discovery        ")
    print("====================================")
    print(f"Using IP context: {ca_ip}")
    
    ca_mgr = CAManager(ca_ip, os.getcwd())
    
    # print("\n[Step 1] Attempting probe_ca_on_network (Direct Probe)...")
    # existing_ca = await ca_mgr.probe_ca_on_network(timeout=3.0)
    # if existing_ca:
    #     print(f" -> ✓ Probe Success: Existing CA found at {existing_ca[0]}:{existing_ca[1]}")
    #     return
    # else:
    #     print(" -> ✗ Probe could not find a CA.")

    print("\n[Step 2] Attempting full CA discovery loop via CAManager.start_discovery()...")
    await ca_mgr.start_discovery()
    print(" -> Broadcasting 'WHO_IS_CA' (waiting up to 10 seconds)...")
    
    try:
        await asyncio.wait_for(ca_mgr.ca_found_event.wait(), timeout=10.0)
        print(f" -> ✓ Discovery Success: Found CA at {ca_mgr.ca_info[0]}:{ca_mgr.ca_info[1]}")
    except asyncio.TimeoutError:
        print(" -> ✗ Discovery Timeout: No CA found on network.")
    finally:
        ca_mgr.stop_discovery()
        print("\nDiscovery stopped and test complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
