import asyncio
import logging
from DMX import DMXController
from DMX_test import DEVICE_ADDRESS as DEFAULT_DMX_ADDRESS

def print_help():
    """Prints the available commands."""
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
    """Main function to run the interactive CLI."""
    mac_addresses_input = input(f"Enter DMX controller MAC addresses (comma-separated, or press Enter to use default: {DEFAULT_DMX_ADDRESS}): ").strip()
    if not mac_addresses_input:
        mac_addresses = [DEFAULT_DMX_ADDRESS]
    else:
        mac_addresses = [addr.strip() for addr in mac_addresses_input.split(',')]

    controllers = [DMXController(addr) for addr in mac_addresses]

    connected_controllers = []
    for controller in controllers:
        try:
            print(f"Connecting to {controller._device_address}...")
            await controller.connect()
            print(f"Connected successfully to {controller._device_address}!")
            connected_controllers.append(controller)
        except Exception as e:
            print(f"Failed to connect to {controller._device_address}: {e}")

    if not connected_controllers:
        print("No devices could be connected. Exiting.")
        return

    try:
        print_help()
        active_addresses = ", ".join([c.address for c in connected_controllers])

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
                elif command == "on":
                    for controller in connected_controllers:
                        await controller.set_power(True)
                    print("Light turned on for all devices.")
                elif command == "off":
                    for controller in connected_controllers:
                        await controller.set_power(False)
                    print("Light turned off for all devices.")
                elif command == "brightness":
                    if len(parts) == 2 and parts[1].isdigit():
                        val = int(parts[1])
                        for controller in connected_controllers:
                            await controller.set_brightness(val)
                        print(f"Brightness set to {val}% for all devices.")
                    else:
                        print("Invalid brightness command. Usage: brightness <value>")
                elif command == "speed":
                    if len(parts) == 2 and parts[1].isdigit():
                        val = int(parts[1])
                        for controller in connected_controllers:
                            await controller.set_speed(val)
                        print(f"Speed set to {val}% for all devices.")
                    else:
                        print("Invalid speed command. Usage: speed <value>")
                elif command == "mode":
                    if len(parts) == 2 and parts[1].isdigit():
                        val = int(parts[1])
                        for controller in connected_controllers:
                            await controller.set_mode(val)
                        print(f"Mode set to {val} for all devices.")
                    else:
                        print("Invalid mode command. Usage: mode <value>")
                elif command == "color":
                    if len(parts) == 4 and all(p.isdigit() for p in parts[1:]):
                        r, g, b = map(int, parts[1:])
                        for controller in connected_controllers:
                            await controller.set_static_color(r, g, b)
                        print(f"Color set to R={r}, G={g}, B={b} for all devices.")
                    else:
                        print("Invalid color command. Usage: color <r> <g> <b>")
                else:
                    print(f"Unknown command: {command}")
                    print_help()

            except (ValueError, IndexError) as e:
                print(f"Invalid command syntax: {e}")
                print_help()
            except Exception as e:
                print(f"An error occurred: {e}")

    except Exception as e:
        print(f"An error occurred during the process: {e}")
    finally:
        for controller in connected_controllers:
            if controller.is_connected:
                print(f"Disconnecting from {controller._device_address}...")
                await controller.disconnect()
                print(f"Disconnected from {controller._device_address}.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='[%(levelname)s][%(asctime)s]%(message)s')
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")