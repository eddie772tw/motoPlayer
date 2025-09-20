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
    mac_address = input(f"Enter DMX controller MAC address (or press Enter to use default: {DEFAULT_DMX_ADDRESS}): ").strip()
    if not mac_address:
        mac_address = DEFAULT_DMX_ADDRESS

    controller = DMXController(mac_address)

    try:
        print(f"Connecting to {mac_address}...")
        await controller.connect()
        print("Connected successfully!")
        print_help()

        while True:
            try:
                cmd_input = await asyncio.to_thread(input, f"DMX ({mac_address})> ")
                parts = cmd_input.lower().split()
                if not parts:
                    continue

                command = parts[0]

                if command in ["exit", "quit"]:
                    break
                elif command == "help":
                    print_help()
                elif command == "on":
                    await controller.set_power(True)
                    print("Light turned on.")
                elif command == "off":
                    await controller.set_power(False)
                    print("Light turned off.")
                elif command == "brightness":
                    if len(parts) == 2 and parts[1].isdigit():
                        val = int(parts[1])
                        await controller.set_brightness(val)
                        print(f"Brightness set to {val}%.")
                    else:
                        print("Invalid brightness command. Usage: brightness <value>")
                elif command == "speed":
                    if len(parts) == 2 and parts[1].isdigit():
                        val = int(parts[1])
                        await controller.set_speed(val)
                        print(f"Speed set to {val}%.")
                    else:
                        print("Invalid speed command. Usage: speed <value>")
                elif command == "mode":
                    if len(parts) == 2 and parts[1].isdigit():
                        val = int(parts[1])
                        await controller.set_mode(val)
                        print(f"Mode set to {val}.")
                    else:
                        print("Invalid mode command. Usage: mode <value>")
                elif command == "color":
                    if len(parts) == 4 and all(p.isdigit() for p in parts[1:]):
                        r, g, b = map(int, parts[1:])
                        await controller.set_static_color(r, g, b)
                        print(f"Color set to R={r}, G={g}, B={b}.")
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
        print(f"Failed to connect or an error occurred: {e}")
    finally:
        if controller.is_connected:
            print("Disconnecting...")
            await controller.disconnect()
            print("Disconnected.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='[%(levelname)s][%(asctime)s]%(message)s')
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")