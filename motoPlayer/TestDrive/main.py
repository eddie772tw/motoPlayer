import asyncio
import logging
import threading
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.slider import Slider
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock
from DMX import DMXController
try:
    from DMX_test import DEVICE_ADDRESS
    DEFAULT_DMX_ADDRESS = DEVICE_ADDRESS if isinstance(DEVICE_ADDRESS, list) else [DEVICE_ADDRESS]
except ImportError:
    DEFAULT_DMX_ADDRESS = []

# Initialize Logger
logger = logging.getLogger(__name__)

class DMXControlPanel(BoxLayout):
    def __init__(self, **kwargs):
        super(DMXControlPanel, self).__init__(**kwargs)
        self.orientation = 'vertical'
        self.controllers = []
        self.connected = False
        self.padding = 10
        self.spacing = 10

        # --- Connection Section ---
        conn_layout = BoxLayout(orientation='vertical', size_hint_y=None, height=120, spacing=5)
        conn_layout.add_widget(Label(text="DMX MAC Addresses (comma separated):", size_hint_y=None, height=30))

        default_text = ",".join(DEFAULT_DMX_ADDRESS)
        self.mac_input = TextInput(text=default_text, multiline=False, size_hint_y=None, height=40)
        conn_layout.add_widget(self.mac_input)

        self.connect_btn = Button(text="Connect", size_hint_y=None, height=40)
        self.connect_btn.bind(on_press=self.on_connect_press)
        conn_layout.add_widget(self.connect_btn)

        self.add_widget(conn_layout)

        # --- Status ---
        self.status_label = Label(text="Status: Disconnected", size_hint_y=None, height=30, color=(1, 0, 0, 1))
        self.add_widget(self.status_label)

        # --- Controls (Initially Disabled or just visible) ---
        self.controls_layout = ScrollView()
        self.inner_layout = BoxLayout(orientation='vertical', size_hint_y=None, spacing=10, padding=10)
        self.inner_layout.bind(minimum_height=self.inner_layout.setter('height'))

        # Power
        self.inner_layout.add_widget(Label(text="Power", size_hint_y=None, height=30))
        power_box = BoxLayout(size_hint_y=None, height=50)
        self.btn_on = Button(text="ON")
        self.btn_on.bind(on_press=lambda x: self.send_command("on"))
        self.btn_off = Button(text="OFF")
        self.btn_off.bind(on_press=lambda x: self.send_command("off"))
        power_box.add_widget(self.btn_on)
        power_box.add_widget(self.btn_off)
        self.inner_layout.add_widget(power_box)

        # RGB Color
        self.inner_layout.add_widget(Label(text="Color (R, G, B)", size_hint_y=None, height=30))
        self.r_slider = self.create_slider(0, 255, 255, "R")
        self.g_slider = self.create_slider(0, 255, 255, "G")
        self.b_slider = self.create_slider(0, 255, 255, "B")

        btn_set_color = Button(text="Set Color", size_hint_y=None, height=50)
        btn_set_color.bind(on_press=lambda x: self.send_command("color"))
        self.inner_layout.add_widget(btn_set_color)

        # Brightness
        self.inner_layout.add_widget(Label(text="Brightness (0-100)", size_hint_y=None, height=30))
        self.bri_slider = self.create_slider(0, 100, 100, "Brightness")
        btn_set_bri = Button(text="Set Brightness", size_hint_y=None, height=50)
        btn_set_bri.bind(on_press=lambda x: self.send_command("brightness"))
        self.inner_layout.add_widget(btn_set_bri)

        # Mode
        self.inner_layout.add_widget(Label(text="Mode (1-255)", size_hint_y=None, height=30))
        self.mode_slider = self.create_slider(1, 255, 1, "Mode")
        btn_set_mode = Button(text="Set Mode", size_hint_y=None, height=50)
        btn_set_mode.bind(on_press=lambda x: self.send_command("mode"))
        self.inner_layout.add_widget(btn_set_mode)

        # Speed
        self.inner_layout.add_widget(Label(text="Speed (0-100)", size_hint_y=None, height=30))
        self.speed_slider = self.create_slider(0, 100, 50, "Speed")
        btn_set_speed = Button(text="Set Speed", size_hint_y=None, height=50)
        btn_set_speed.bind(on_press=lambda x: self.send_command("speed"))
        self.inner_layout.add_widget(btn_set_speed)

        self.controls_layout.add_widget(self.inner_layout)
        self.add_widget(self.controls_layout)

    def create_slider(self, min_val, max_val, default, label_prefix):
        box = BoxLayout(orientation='vertical', size_hint_y=None, height=60)
        lbl = Label(text=f"{label_prefix}: {default}")
        slider = Slider(min=min_val, max=max_val, value=default)
        slider.bind(value=lambda instance, val: setattr(lbl, 'text', f"{label_prefix}: {int(val)}"))
        box.add_widget(lbl)
        box.add_widget(slider)
        self.inner_layout.add_widget(box)
        return slider

    def on_connect_press(self, instance):
        if not self.connected:
            mac_text = self.mac_input.text.strip()
            if not mac_text:
                return
            macs = [m.strip() for m in mac_text.split(',')]
            asyncio.create_task(self.connect_devices(macs))
        else:
            asyncio.create_task(self.disconnect_devices())

    async def connect_devices(self, macs):
        self.update_status("Connecting...", (1, 1, 0, 1))
        self.connect_btn.disabled = True

        self.controllers = [DMXController(addr) for addr in macs]

        async def connect_single(c):
            try:
                await c.connect()
                return c
            except Exception as e:
                print(f"Failed to connect {c._device_address}: {e}")
                return None

        tasks = [connect_single(c) for c in self.controllers]
        results = await asyncio.gather(*tasks)
        connected_controllers = [c for c in results if c is not None]

        if connected_controllers:
            self.controllers = connected_controllers
            self.connected = True
            self.update_status(f"Connected ({len(self.controllers)})", (0, 1, 0, 1))
            self.connect_btn.text = "Disconnect"
        else:
            self.controllers = []
            self.update_status("Connection Failed", (1, 0, 0, 1))

        self.connect_btn.disabled = False

    async def disconnect_devices(self):
        self.update_status("Disconnecting...", (1, 1, 0, 1))
        self.connect_btn.disabled = True

        async def disconnect_single(c):
            try:
                await c.disconnect()
            except:
                pass

        tasks = [disconnect_single(c) for c in self.controllers]
        await asyncio.gather(*tasks)

        self.controllers = []
        self.connected = False
        self.update_status("Disconnected", (1, 0, 0, 1))
        self.connect_btn.text = "Connect"
        self.connect_btn.disabled = False

    def send_command(self, cmd_type):
        if not self.connected:
            return

        asyncio.create_task(self._send_command_async(cmd_type))

    async def _send_command_async(self, cmd_type):
        tasks = []
        try:
            if cmd_type == "on":
                tasks = [c.set_power(True) for c in self.controllers]
            elif cmd_type == "off":
                tasks = [c.set_power(False) for c in self.controllers]
            elif cmd_type == "color":
                r = int(self.r_slider.value)
                g = int(self.g_slider.value)
                b = int(self.b_slider.value)
                tasks = [c.set_static_color(r, g, b) for c in self.controllers]
            elif cmd_type == "brightness":
                val = int(self.bri_slider.value)
                tasks = [c.set_brightness(val) for c in self.controllers]
            elif cmd_type == "mode":
                val = int(self.mode_slider.value)
                tasks = [c.set_mode(val) for c in self.controllers]
            elif cmd_type == "speed":
                val = int(self.speed_slider.value)
                tasks = [c.set_speed(val) for c in self.controllers]

            if tasks:
                await asyncio.gather(*tasks)
        except Exception as e:
            print(f"Error sending command {cmd_type}: {e}")

    def update_status(self, text, color):
        self.status_label.text = f"Status: {text}"
        self.status_label.color = color

class DMXApp(App):
    def build(self):
        return DMXControlPanel()

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    app = DMXApp()

    # Modern Kivy with asyncio support (Kivy 2.0.0+)
    # We use asyncio.run to run the app if available, else manual loop
    try:
        loop.run_until_complete(app.async_run())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()
