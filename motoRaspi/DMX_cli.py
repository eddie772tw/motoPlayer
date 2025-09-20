# motoRaspi/dmx_cli.py
import asyncio
import argparse
import logging
from DMX import DMXController
from DMX_test import DEVICE_ADDRESS as DEFAULT_DMX_ADDRESS

async def control_device(mac_address, args):
    """
    Connects to a DMX device, sends commands, and disconnects.
    """
    controller = DMXController(mac_address)
    print(f"--- Processing device {mac_address} ---")
    try:
        await controller.connect()

        if args.color:
            await controller.set_static_color(args.color[0], args.color[1], args.color[2])
            print(f"Set color to R={args.color[0]}, G={args.color[1]}, B={args.color[2]} for {mac_address}")

        if args.brightness is not None:
            await controller.set_brightness(args.brightness)
            print(f"Set brightness to {args.brightness}% for {mac_address}")

        if args.mode is not None:
            await controller.set_mode(args.mode)
            print(f"Set mode to {args.mode} for {mac_address}")

        if args.speed is not None:
            await controller.set_speed(args.speed)
            print(f"Set speed to {args.speed}% for {mac_address}")

        if args.on:
            await controller.set_power(True)
            print(f"Turned light on for {mac_address}.")

        if args.off:
            await controller.set_power(False)
            print(f"Turned light off for {mac_address}.")

    except Exception as e:
        print(f"An error occurred with {mac_address}: {e}")
    finally:
        await controller.disconnect()
        print(f"Disconnected from {mac_address}.")
        print(f"--- Finished device {mac_address} ---\n")


async def main():
    parser = argparse.ArgumentParser(description="DMX BLE Controller CLI")
    parser.add_argument('--macs', nargs='+', default=None, help='One or more DMX controller MAC addresses. Defaults to the address in DMX_test.py if not provided.')
    parser.add_argument('--color', nargs=3, type=int, metavar=('R', 'G', 'B'), help='Set static color (e.g., --color 255 0 0)')
    parser.add_argument('--brightness', type=int, metavar='B', help='Set brightness (0-100)')
    parser.add_argument('--mode', type=int, metavar='M', help='Set dynamic mode (e.g., --mode 3)')
    parser.add_argument('--speed', type=int, metavar='S', help='Set mode speed (0-100)')
    parser.add_argument('--on', action='store_true', help='Turn the light on')
    parser.add_argument('--off', action='store_true', help='Turn the light off')
    args = parser.parse_args()

    mac_addresses = args.macs
    if mac_addresses is None:
        print(f"No MAC addresses provided. Using default from DMX_test.py: {DEFAULT_DMX_ADDRESS}")
        mac_addresses = [DEFAULT_DMX_ADDRESS]

    # Create a copy of args and remove 'macs' to check if any other command is present
    command_args = vars(args).copy()
    # macs might not be in command_args if default is used, so we check
    if 'macs' in command_args:
        del command_args['macs']

    # Filter out None values to correctly check for presence of commands
    if not any(v is not None and v is not False for v in command_args.values()):
        print("No command specified. Use --on, --off, --color, etc.")
        parser.print_help()
        return

    tasks = [control_device(mac, args) for mac in mac_addresses]
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='[%(levelname)s][%(asctime)s]%(message)s')
    asyncio.run(main())