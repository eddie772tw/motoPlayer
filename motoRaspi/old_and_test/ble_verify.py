# ble_verify.py (v2 - Updated for modern bleak API)
# This script focuses on advertising a service, which is the
# primary test for BLE peripheral functionality on Linux.

import asyncio
from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

# --- Use the same UUIDs as before ---
MOTO_SERVICE_UUID = "0000180A-0000-1000-8000-00805F9B34FB" # Using a standard UUID for testing

async def main():
    print("Scanning for 5 seconds to wake up the adapter...")
    # A short scan can help ensure the adapter is active
    async with BleakScanner(timeout=5.0):
        pass

    print("Attempting to advertise a BLE service...")
    
    # We create a scanner and use it to send out our advertisement
    scanner = BleakScanner(detection_callback=None)

    try:
        await scanner.start()
        print(f"Advertising service: {MOTO_SERVICE_UUID}")
        print("Please use 'nRF Connect' on your phone to see if this device is advertising the service.")
        print("This script will advertise for 5 minutes. Press Ctrl+C to stop.")
        
        # Keep the script running to continue advertising
        await asyncio.sleep(300) 

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        print("Stopping advertisement...")
        await scanner.stop()

if __name__ == "__main__":
    # Note: On Linux, advertising often requires running with sudo
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nScript stopped by user.")