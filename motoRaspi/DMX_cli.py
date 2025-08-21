# motoRaspi/dmx_cli.py
import asyncio
import argparse
import logging
from DMX import DMXController

# !!! 請填入您 DMX 控制器的真實 MAC 位址 !!!
DMX_DEVICE_ADDRESS = "A1:B2:C3:D4:E5:F6"

async def main():
    parser = argparse.ArgumentParser(description="DMX BLE Controller CLI")
    # ... (其餘程式碼與上次相同) ...
    parser.add_argument('--color', nargs=3, type=int, metavar=('R', 'G', 'B'), help='Set static color (e.g., --color 255 0 0)')
    parser.add_argument('--brightness', type=int, metavar='B', help='Set brightness (0-100)')
    parser.add_argument('--mode', type=int, metavar='M', help='Set dynamic mode (e.g., --mode 3)')
    parser.add_argument('--speed', type=int, metavar='S', help='Set mode speed (0-100)')
    parser.add_argument('--on', action='store_true', help='Turn the light on')
    parser.add_argument('--off', action='store_true', help='Turn the light off')
    args = parser.parse_args()

    if not any(vars(args).values()):
        parser.print_help()
        return

    controller = DMXController(DMX_DEVICE_ADDRESS)

    try:
        await controller.connect()

        if args.color:
            await controller.set_static_color(args.color[0], args.color[1], args.color[2])
            print(f"Set color to R={args.color[0]}, G={args.color[1]}, B={args.color[2]}")

        if args.brightness is not None:
            await controller.set_brightness(args.brightness)
            print(f"Set brightness to {args.brightness}%")

        if args.mode is not None:
            await controller.set_mode(args.mode)
            print(f"Set mode to {args.mode}")

        if args.speed is not None:
            await controller.set_speed(args.speed)
            print(f"Set speed to {args.speed}%")

        if args.on:
            await controller.set_power(True)
            print("Turned light on.")

        if args.off:
            await controller.set_power(False)
            print("Turned light off.")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        await controller.disconnect()
        print("Disconnected.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='[%(levelname)s][%(asctime)s]%(message)s')
    asyncio.run(main())