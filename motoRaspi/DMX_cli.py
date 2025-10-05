import asyncio
import logging
from DMX import DMXController
from DMX_test import DEVICE_ADDRESS as DEFAULT_DMX_ADDRESS

def print_help():
    """logger.infos the available commands."""
    print("\nAvailable commands:")
    print("  on                - Turn the light on")
    print("  off               - Turn the light off")
    print("  color <r> <g> <b> - Set static color (e.g., color 255 0 0)")
    print("  brightness <val>  - Set brightness (0-100)")
    print("  mode <val>        - Set dynamic mode (1-255)")
    print("  speed <val>       - Set mode speed (0-100)")
    print("  help              - Show this help message")
    print("  exit, quit        - Disconnect and exit the CLI\n")

async def main():
    logging.basicConfig(level=logging.INFO, format='[%(levelname)s][%(asctime)s]%(message)s')
    logger = logging.getLogger(__name__)
    """Main function to run the interactive CLI."""
    mac_addresses_input = input(f"Enter DMX controller MAC addresses (comma-separated, or press Enter to use default: {DEFAULT_DMX_ADDRESS}): ").strip()
    if not mac_addresses_input:
        mac_addresses = DEFAULT_DMX_ADDRESS
    else:
        mac_addresses = [addr.strip() for addr in mac_addresses_input.split(',')]

    controllers = [DMXController(addr) for addr in mac_addresses]

    async def connect_controller(controller):
        """Helper to connect to a single controller and handle errors."""
        try:
            # logger.info(f"Connecting to {controller._device_address}...")
            await controller.connect()
            # logger.info(f"Connected successfully to {controller._device_address}!")
            return controller
        except Exception as e:
            logger.error(f"Failed to connect to {controller._device_address}: {e}")
            return None

    # Concurrently connect to all devices
    connect_tasks = [connect_controller(c) for c in controllers]
    results = await asyncio.gather(*connect_tasks)
    connected_controllers = [c for c in results if c is not None]

    if not connected_controllers:
        logger.info("No devices could be connected. Exiting.")
        return

    try:
        print_help()
        active_addresses = ", ".join([c._device_address for c in connected_controllers])

        while True:
            try:
                cmd_input = await asyncio.to_thread(input, f"DMX ({active_addresses})> ")
                parts = cmd_input.lower().split()
                if not parts:
                    continue

                command = parts[0]

                if command in ["exit", "quit"]:
                    break
                elif command == "help":
                    print_help()
                    continue

                tasks = []
                if command == "on":
                    tasks = [c.set_power(True) for c in connected_controllers]
                    await asyncio.gather(*tasks)
                    logger.info("Light turned on for all devices.")
                elif command == "off":
                    tasks = [c.set_power(False) for c in connected_controllers]
                    await asyncio.gather(*tasks)
                    logger.info("Light turned off for all devices.")
                elif command == "brightness":
                    if len(parts) == 2 and parts[1].isdigit():
                        val = int(parts[1])
                        tasks = [c.set_brightness(val) for c in connected_controllers]
                        await asyncio.gather(*tasks)
                        logger.info(f"Brightness set to {val}% for all devices.")
                    else:
                        logger.warning("Invalid brightness command. Usage: brightness <value>")
                elif command == "speed":
                    if len(parts) == 2 and parts[1].isdigit():
                        val = int(parts[1])
                        tasks = [c.set_speed(val) for c in connected_controllers]
                        await asyncio.gather(*tasks)
                        logger.info(f"Speed set to {val}% for all devices.")
                    else:
                        logger.warning("Invalid speed command. Usage: speed <value>")
                elif command == "mode":
                    if len(parts) == 2 and parts[1].isdigit():
                        val = int(parts[1])
                        tasks = [c.set_mode(val) for c in connected_controllers]
                        await asyncio.gather(*tasks)
                        logger.info(f"Mode set to {val} for all devices.")
                    else:
                        logger.warning("Invalid mode command. Usage: mode <value>")
                elif command == "color":
                    if len(parts) == 4 and all(p.isdigit() for p in parts[1:]):
                        r, g, b = map(int, parts[1:])
                        tasks = [c.set_static_color(r, g, b) for c in connected_controllers]
                        await asyncio.gather(*tasks)
                        logger.info(f"Color set to R={r}, G={g}, B={b} for all devices.")
                    else:
                        logger.warning("Invalid color command. Usage: color <r> <g> <b>")
                else:
                    logger.error(f"Unknown command: {command}")
                    print_help()

            except (ValueError, IndexError) as e:
                logger.info(f"Invalid command syntax: {e}")
                print_help()
            except Exception as e:
                logger.info(f"An error occurred: {e}")

    except Exception as e:
        logger.error(f"An error occurred during the process: {e}")
    finally:
        if connected_controllers:
            logger.info("Disconnecting all connected devices...")

            async def disconnect_with_log(controller):
                if controller.is_connected:
                    logger.info(f"Disconnecting from {controller._device_address}...")
                    await controller.disconnect()
                    logger.info(f"Disconnected from {controller._device_address}.")

            tasks = [disconnect_with_log(c) for c in connected_controllers]
            await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")