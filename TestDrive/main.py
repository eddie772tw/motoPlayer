import asyncio
import logging
import json
import os
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.slider import Slider
from kivy.uix.scrollview import ScrollView
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.utils import platform
from kivy.core.window import Window

# Import your original DMX class
from DMX import DMXController
from bleak import BleakScanner, BleakClient, BleakError

# 設定存檔檔名 (於 DMXApp 中動態設定)
DATA_FILE = "" 

logger = logging.getLogger(__name__)

# ---------------------------------------------------------
# UI Component: Single Device List Row (for Settings Page)
# ---------------------------------------------------------
class DeviceListRow(BoxLayout):
    """Row displaying a single MAC address and a delete button"""
    def __init__(self, mac_address, remove_callback, **kwargs):
        super().__init__(**kwargs)
        self.size_hint_y = None
        self.height = 50
        self.mac_address = mac_address
        
        # MAC 地址顯示
        self.lbl_mac = Label(text=mac_address, size_hint_x=0.7, halign='left', valign='middle')
        self.lbl_mac.bind(size=self.lbl_mac.setter('text_size')) # Ensure text aligns left
        self.add_widget(self.lbl_mac)

        # 刪除按鈕
        self.btn_remove = Button(text="Delete", size_hint_x=0.3, background_color=(1, 0.3, 0.3, 1))
        self.btn_remove.bind(on_press=lambda x: remove_callback(self))
        self.add_widget(self.btn_remove)

# ---------------------------------------------------------
# UI Component: Scan Result Row
# ---------------------------------------------------------
class ScanResultRow(BoxLayout):
    def __init__(self, device, rssi, add_callback, **kwargs):
        super().__init__(**kwargs)
        self.size_hint_y = None
        self.height = 60
        self.device = device
        self.add_callback = add_callback
        
        # Icon/RSSI
        rssi_color = (0, 1, 0, 1) if rssi > -70 else (1, 1, 0, 1) if rssi > -90 else (1, 0, 0, 1)
        self.add_widget(Label(text=f"{rssi}dB", size_hint_x=0.15, color=rssi_color))
        
        # Info
        info_text = f"{device.name or 'Unknown'}\n{device.address}"
        self.add_widget(Label(text=info_text, size_hint_x=0.55, halign='left', valign='middle'))
        
        # Add Button
        self.btn_add = Button(text="Add", size_hint_x=0.3, background_color=(0.2, 0.6, 1, 1))
        self.btn_add.bind(on_press=self.on_add_press)
        self.add_widget(self.btn_add)

    def on_add_press(self, instance):
        self.btn_add.text = "..."
        self.btn_add.disabled = True
        self.add_callback(self.device, self)

# ---------------------------------------------------------
# Page 1.5: Scan & Search (ScanScreen)
# ---------------------------------------------------------
class ScanScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        self.scanner = None
        self.found_devices = {} # map address -> device
        
        # Main Layout
        layout = BoxLayout(orientation='vertical', padding=20, spacing=15)
        
        # Header / Nav
        header = BoxLayout(size_hint_y=None, height=50)
        btn_back = Button(text="< Back", size_hint_x=0.25)
        btn_back.bind(on_press=self.go_back)
        header.add_widget(btn_back)
        header.add_widget(Label(text="Scan New Devices", font_size=20, size_hint_x=0.5))
        
        self.btn_scan = Button(text="Start Scan", size_hint_x=0.25, background_color=(0.2, 0.8, 0.2, 1))
        self.btn_scan.bind(on_press=self.toggle_scan)
        header.add_widget(self.btn_scan)
        layout.add_widget(header)
        
        # Status
        self.status_label = Label(text="Ready via BleakScanner", size_hint_y=None, height=30, color=(0.7,0.7,0.7,1))
        layout.add_widget(self.status_label)

        # List
        self.scroll = ScrollView()
        self.list_layout = BoxLayout(orientation='vertical', size_hint_y=None, spacing=5)
        self.list_layout.bind(minimum_height=self.list_layout.setter('height'))
        self.scroll.add_widget(self.list_layout)
        layout.add_widget(self.scroll)

        self.add_widget(layout)

    def on_leave(self):
        # 確保在離開頁面時停止掃描
        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(self.stop_scan())

    def go_back(self, instance):
        self.manager.transition.direction = 'right'
        self.manager.current = 'settings'

    def toggle_scan(self, instance):
        if self.scanner:
            self.stop_scan()
        else:
            self.start_scan()

    def start_scan(self):
        self.list_layout.clear_widgets()
        self.found_devices = {}
        self.btn_scan.text = "Stop"
        self.btn_scan.background_color = (0.8, 0.2, 0.2, 1)
        self.status_label.text = "Scanning..."
        
        asyncio.create_task(self._async_scan())

    async def stop_scan(self):
        if self.scanner:
            scanner_to_stop = self.scanner
            self.scanner = None
            await scanner_to_stop.stop()
        self.btn_scan.text = "Start Scan"
        self.btn_scan.background_color = (0.2, 0.8, 0.2, 1)
        self.status_label.text = "Scan Stopped"

    async def _async_scan(self):
        try:
            self.scanner = BleakScanner(detection_callback=self.device_detected)
            await self.scanner.start()
        except Exception as e:
            self.status_label.text = f"Scan Error: {e}"
            self.stop_scan()

    def device_detected(self, device, advertisement_data):
        # Filter Logic
        if device.address in self.found_devices:
            return
        if device.address in self.app.saved_devices:
            return # Already saved
        if advertisement_data.rssi < -90:
            return # Too weak
        
        # DMX name check (simple heuristic) or Service UUID check
        # Many HM-10/11 modules advertise FFE0 service. DMX uses FFE1 char inside FFE0 service usually.
        is_candidate = False
        if device.name and len(device.name) > 0:
            is_candidate = True # Allow any named device for now, verify later
        
        # Example: Filter by specific service UUIDs if known (e.g. ['0000ffe0...'])
        # if '0000ffe0-0000-1000-8000-00805f9b34fb' in advertisement_data.service_uuids:
        #    is_candidate = True

        if is_candidate:
            self.found_devices[device.address] = device
            # Update UI on main thread
            # Since we are in async callback, we should use some thread-safe way if strictly needed, 
            # but Kivy often handles this loosely or needs Clock.schedule_once. 
            # For simplicity in this async loop, we append directly (watch out for thread issues if any).
            row = ScanResultRow(device, advertisement_data.rssi, self.verify_and_add)
            self.list_layout.add_widget(row)

    def verify_and_add(self, device, row_widget):
        asyncio.create_task(self._async_verify_and_add(device, row_widget))

    async def _async_verify_and_add(self, device, row_widget):
        self.status_label.text = f"Verifying {device.name}..."
        
        # Valid Characteristic UUID for DMX
        DMX_CHAR_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"
        
        client = BleakClient(device, timeout=10.0)
        try:
            await client.connect()
            
            # Check for characteristic
            has_dmx = False
            for service in client.services:
                for char in service.characteristics:
                    if char.uuid == DMX_CHAR_UUID:
                        has_dmx = True
                        break
                if has_dmx: break
            
            await client.disconnect()
            
            if has_dmx:
                self.status_label.text = f"Verified! Added {device.name}"
                self.app.saved_devices.append(device.address)
                self.app.save_devices_to_disk()
                self.list_layout.remove_widget(row_widget)
            else:
                 self.status_label.text = "Failed: Not a DMX Controller"
                 row_widget.btn_add.text = "Blocked"
                 row_widget.btn_add.background_color = (0.5, 0.5, 0.5, 1)

        except Exception as e:
            self.status_label.text = f"Verify Failed: {e}"
            row_widget.btn_add.text = "Retry"
            row_widget.btn_add.disabled = False

# ---------------------------------------------------------
# Page 1: Device Settings & Connection (SettingsScreen)
# ---------------------------------------------------------
class SettingsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        
        # 主佈局
        layout = BoxLayout(orientation='vertical', padding=20, spacing=15)
        
        # 標題
        layout.add_widget(Label(text="[ Device Manager ]", font_size=24, size_hint_y=None, height=40))

        # --- Add Device Area ---
        add_box = BoxLayout(size_hint_y=None, height=50, spacing=10)
        
        # Search Button (New Feature)
        btn_search = Button(text="Search Nearby", size_hint_x=0.3, background_color=(0.2, 0.6, 1, 1))
        btn_search.bind(on_press=self.go_to_scan)
        add_box.add_widget(btn_search)
        self.input_mac = TextInput(hint_text="Enter MAC (e.g. 24:07:03:...)", multiline=False)
        btn_add = Button(text="Add to List", size_hint_x=0.3)
        btn_add.bind(on_press=self.add_device_from_input)
        add_box.add_widget(self.input_mac)
        add_box.add_widget(btn_add)
        layout.add_widget(add_box)

        # --- Device List (ScrollView) ---
        layout.add_widget(Label(text="Saved Device List:", size_hint_y=None, height=30, halign='left'))
        
        self.scroll = ScrollView()
        self.list_layout = BoxLayout(orientation='vertical', size_hint_y=None, spacing=5)
        self.list_layout.bind(minimum_height=self.list_layout.setter('height'))
        self.scroll.add_widget(self.list_layout)
        
        # Add frame or background to separate list area (Optional)
        layout.add_widget(self.scroll)

        # --- Bottom Connection Control Area ---
        status_box = BoxLayout(orientation='vertical', size_hint_y=None, height=100, spacing=5)
        
        self.status_label = Label(text="Status: Disconnected", color=(0.8, 0.8, 0.8, 1))
        status_box.add_widget(self.status_label)

        btn_box = BoxLayout(spacing=10)
        self.btn_connect = Button(text="Connect All", background_color=(0.2, 0.8, 0.2, 1))
        self.btn_connect.bind(on_press=self.connect_all)
        
        self.btn_disconnect = Button(text="Disconnect", background_color=(0.8, 0.2, 0.2, 1), disabled=True)
        self.btn_disconnect.bind(on_press=self.disconnect_all)
        
        btn_box.add_widget(self.btn_connect)
        btn_box.add_widget(self.btn_disconnect)
        status_box.add_widget(btn_box)
        
        layout.add_widget(status_box)

        # --- Switch to Control Panel ---
        self.btn_go_control = Button(text="Go to Control Panel >", size_hint_y=None, height=60)
        self.btn_go_control.bind(on_press=self.go_to_control)
        # Always enable this button
        self.btn_go_control.disabled = False 
        layout.add_widget(self.btn_go_control)
        
        # --- Debug Area ---
        debug_box = BoxLayout(size_hint_y=None, height=40, spacing=10)
        btn_debug = Button(text="[Debug] Open Config JSON", background_color=(0.4, 0.4, 0.4, 1))
        btn_debug.bind(on_press=self.open_config_file)
        debug_box.add_widget(btn_debug)
        
        btn_reload = Button(text="[Debug] Reload JSON", background_color=(0.4, 0.4, 0.4, 1))
        btn_reload.bind(on_press=self.reload_config_file)
        debug_box.add_widget(btn_reload)
        
        layout.add_widget(debug_box)

        self.add_widget(layout)

    def on_enter(self):
        """Refresh list when entering this page"""
        self.refresh_list_ui()
        self.update_connection_status()

    def refresh_list_ui(self):
        """Redraw list from App data"""
        self.list_layout.clear_widgets()
        for mac in self.app.saved_devices:
            row = DeviceListRow(mac, self.remove_device)
            self.list_layout.add_widget(row)

    def add_device_from_input(self, instance):
        mac = self.input_mac.text.strip().upper()
        if mac and mac not in self.app.saved_devices:
            self.app.saved_devices.append(mac)
            self.app.save_devices_to_disk() # Save to file
            self.refresh_list_ui()
            self.input_mac.text = ""

    def remove_device(self, row_widget):
        mac = row_widget.mac_address
        if mac in self.app.saved_devices:
            self.app.saved_devices.remove(mac)
            self.app.save_devices_to_disk() # Save to file
            self.list_layout.remove_widget(row_widget)

    def connect_all(self, instance):
        if not self.app.saved_devices:
            self.status_label.text = "Error: List is empty"
            return
        asyncio.create_task(self._async_connect_all())

    async def _async_connect_all(self):
        self.status_label.text = "Connecting..."
        self.status_label.color = (1, 1, 0, 1)
        self.btn_connect.disabled = True
        
        # Initialize controllers
        # MODIFIED: targeted scan to find devices first instead of parallel implicit scanning
        saved_macs = set(self.app.saved_devices)
        found_devices_map = {}
        
        if saved_macs:
            try:
                # Scan for up to 3 seconds to find listed devices
                scanner = BleakScanner()
                
                # Callback to capture targeted devices
                def detection_callback(device, advertisement_data):
                    if device.address in saved_macs:
                        found_devices_map[device.address] = device
                
                scanner.register_detection_callback(detection_callback)
                await scanner.start()
                await asyncio.sleep(3.0)
                await scanner.stop()
            except Exception as e:
                print(f"Pre-scan failed: {e}")
        
        self.app.controllers = []
        for mac in self.app.saved_devices:
            # Use found device object if available (faster/direct), else use string (implicit scan)
            if mac in found_devices_map:
                self.app.controllers.append(DMXController(found_devices_map[mac]))
            else:
                self.app.controllers.append(DMXController(mac))

        async def connect_single(c):
            try:
                await c.connect()
                return c
            except Exception as e:
                print(f"Connection failed {c._device_address}: {e}")
                return None

        tasks = [connect_single(c) for c in self.app.controllers]
        results = await asyncio.gather(*tasks)
        
        # Filter out successfully connected ones
        connected = [c for c in results if c is not None]
        self.app.controllers = connected

        if connected:
            self.status_label.text = f"Connected ({len(connected)} devices)"
            self.status_label.color = (0, 1, 0, 1)
            self.btn_disconnect.disabled = False
            self.btn_go_control.disabled = False # Enable access to control page
            # Auto redirect
            # self.manager.current = 'control' 
        else:
            self.status_label.text = "Connection Failed"
            self.status_label.color = (1, 0, 0, 1)
            self.btn_connect.disabled = False

    def disconnect_all(self, instance):
        asyncio.create_task(self._async_disconnect_all())

    async def _async_disconnect_all(self):
        self.status_label.text = "Disconnecting..."
        tasks = [c.disconnect() for c in self.app.controllers]
        await asyncio.gather(*tasks)
        self.app.controllers = []
        
        self.status_label.text = "Disconnected"
        self.status_label.color = (1, 0, 0, 1)
        self.btn_connect.disabled = False
        self.btn_disconnect.disabled = True
        self.btn_go_control.disabled = True

    def update_connection_status(self):
        """Update UI based on current controller status"""
        if self.app.controllers and any(c.is_connected for c in self.app.controllers):
            self.btn_connect.disabled = True
            self.btn_disconnect.disabled = False
            # self.btn_go_control.disabled = False # No longer toggling this
            self.status_label.text = f"Connected ({len(self.app.controllers)} devices)"
            self.status_label.color = (0, 1, 0, 1)
        else:
            self.btn_connect.disabled = False
            self.btn_disconnect.disabled = True
            # self.btn_go_control.disabled = True # No longer toggling this
            self.status_label.text = "Disconnected"

    def go_to_scan(self, instance):
        self.manager.transition.direction = 'left'
        self.manager.current = 'scan'

    def open_config_file(self, instance):
        if platform == 'android':
            # Android 下切換到內建編輯器頁面
            self.manager.transition.direction = 'left'
            self.manager.current = 'json_editor'
            return
            
        if not os.path.exists(DATA_FILE):
             # Try to force create it if empty
            self.app.save_devices_to_disk()
            
        if os.path.exists(DATA_FILE):
            try:
                os.startfile(DATA_FILE)
                self.status_label.text = f"Opened: {DATA_FILE}"
            except Exception as e:
                self.status_label.text = f"Open Error: {e}"
        else:
            self.status_label.text = "Error: Config file not found"

    def reload_config_file(self, instance):
        self.app.load_devices_from_disk()
        self.refresh_list_ui()
        self.status_label.text = f"Reloaded: {len(self.app.saved_devices)} devices"

    def go_to_control(self, instance):
        self.manager.transition.direction = 'left'
        self.manager.current = 'control'


# ---------------------------------------------------------
# Page 2: Lighting Control Panel (ControlScreen)
# ---------------------------------------------------------
class ControlScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        self.updating_from_code = False # Flag to prevent recursive loops
        
        # Rate limiting flags
        self._sending_color_loop = False
        self._color_update_pending = False
        
        # Main Layout
        root = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        # Top Navigation
        nav_box = BoxLayout(size_hint_y=None, height=50)
        btn_back = Button(text="< Back to Settings", size_hint_x=0.3)
        btn_back.bind(on_press=self.go_back)
        nav_box.add_widget(btn_back)
        nav_box.add_widget(Label(text="Lighting Console", font_size=20))
        root.add_widget(nav_box)

        # Scroll Area (Sliders etc.)
        scroll = ScrollView()
        self.inner_layout = BoxLayout(orientation='vertical', size_hint_y=None, spacing=15, padding=10)
        self.inner_layout.bind(minimum_height=self.inner_layout.setter('height'))

        # Power
        self.inner_layout.add_widget(Label(text="Main Power", size_hint_y=None, height=30))
        power_box = BoxLayout(size_hint_y=None, height=50, spacing=20)
        self.btn_on = Button(text="Turn ON", background_color=(0, 1, 0, 1))
        self.btn_on.bind(on_press=lambda x: self.send_command("on"))
        self.btn_off = Button(text="Turn OFF", background_color=(1, 0, 0, 1))
        self.btn_off.bind(on_press=lambda x: self.send_command("off"))
        power_box.add_widget(self.btn_on)
        power_box.add_widget(self.btn_off)
        self.inner_layout.add_widget(power_box)

        self.inner_layout.add_widget(self.create_divider())

        # RGB Colors
        self.inner_layout.add_widget(Label(text="RGB Static Colors", size_hint_y=None, height=30))
        
        # Hex Input
        hex_box = BoxLayout(size_hint_y=None, height=40, spacing=10)
        hex_box.add_widget(Label(text="HEX Color:", size_hint_x=0.3))
        self.input_hex = TextInput(text="#FFFFFF", multiline=False, size_hint_x=0.7)
        self.input_hex.bind(text=self.on_hex_change)
        hex_box.add_widget(self.input_hex)
        self.inner_layout.add_widget(hex_box)

        self.r_slider = self.create_slider(0, 255, 255, "Red (R)")
        self.g_slider = self.create_slider(0, 255, 255, "Green (G)")
        self.b_slider = self.create_slider(0, 255, 255, "Blue (B)")
        
        # Bind sliders to hex update
        self.r_slider.bind(value=self.on_slider_change)
        self.g_slider.bind(value=self.on_slider_change)
        self.b_slider.bind(value=self.on_slider_change)

        # Removed "Set Color" button for real-time control
        # btn_set_color = Button(text="Set Color", size_hint_y=None, height=50)
        # btn_set_color.bind(on_press=lambda x: self.send_command("color"))
        # self.inner_layout.add_widget(btn_set_color)

        self.inner_layout.add_widget(self.create_divider())

        # Brightness
        self.inner_layout.add_widget(Label(text="Overall Brightness", size_hint_y=None, height=30))
        self.bri_slider = self.create_slider(0, 100, 100, "Brightness %")
        btn_set_bri = Button(text="Set Brightness", size_hint_y=None, height=50)
        btn_set_bri.bind(on_press=lambda x: self.send_command("brightness"))
        self.inner_layout.add_widget(btn_set_bri)

        self.inner_layout.add_widget(self.create_divider())

        # Mode and Speed
        self.inner_layout.add_widget(Label(text="Dynamic Mode", size_hint_y=None, height=30))
        self.mode_slider = self.create_slider(1, 255, 1, "Mode ID")
        btn_set_mode = Button(text="Set Mode", size_hint_y=None, height=50)
        btn_set_mode.bind(on_press=lambda x: self.send_command("mode"))
        self.inner_layout.add_widget(btn_set_mode)

        self.speed_slider = self.create_slider(0, 100, 50, "Speed %")
        btn_set_speed = Button(text="Set Speed", size_hint_y=None, height=50)
        btn_set_speed.bind(on_press=lambda x: self.send_command("speed"))
        self.inner_layout.add_widget(btn_set_speed)

        scroll.add_widget(self.inner_layout)
        root.add_widget(scroll)

        self.add_widget(root)

    def create_divider(self):
        return Label(size_hint_y=None, height=20, text="-----------------", color=(0.5,0.5,0.5,1))

    def create_slider(self, min_val, max_val, default, label_prefix):
        box = BoxLayout(orientation='vertical', size_hint_y=None, height=60)
        lbl = Label(text=f"{label_prefix}: {int(default)}")
        slider = Slider(min=min_val, max=max_val, value=default)
        # Immediately update label text
        slider.bind(value=lambda instance, val: setattr(lbl, 'text', f"{label_prefix}: {int(val)}"))
        box.add_widget(lbl)
        box.add_widget(slider)
        self.inner_layout.add_widget(box)
        return slider

    def on_slider_change(self, instance, value):
        if self.updating_from_code:
            return
            
        # Update HEX input from R/G/B sliders
        r = int(self.r_slider.value)
        g = int(self.g_slider.value)
        b = int(self.b_slider.value)
        
        self.updating_from_code = True
        self.input_hex.text = f"#{r:02X}{g:02X}{b:02X}"
        self.updating_from_code = False
        
        # Real-time update trigger
        self.trigger_color_update()

    def on_hex_change(self, instance, value):
        if self.updating_from_code:
            return

        text = value.strip().upper()
        if text.startswith("#"):
            text = text[1:]
        
        # Check if valid HEX
        if len(text) == 6 and all(c in "0123456789ABCDEF" for c in text):
            try:
                r = int(text[0:2], 16)
                g = int(text[2:4], 16)
                b = int(text[4:6], 16)
                
                self.updating_from_code = True
                self.r_slider.value = r
                self.g_slider.value = g
                self.b_slider.value = b
                self.updating_from_code = False
                
                # Real-time update trigger
                self.trigger_color_update()
            except ValueError:
                pass

    def trigger_color_update(self):
        """Handle rate-limited real-time updates"""
        if self._sending_color_loop:
            self._color_update_pending = True
        else:
            self._sending_color_loop = True
            asyncio.create_task(self._process_color_loop())

    async def _process_color_loop(self):
        while True:
            # Send current slider values
            controllers = self.app.controllers
            if controllers:
                # Use internal async method to ensure we wait for BLE completion
                # This prevents stacking commands if sending takes > 0.1s
                await self._send_command("color", controllers)
            
            # Rate limit (0.1s = 10Hz)
            await asyncio.sleep(0.1)
            
            if not self._color_update_pending:
                break
            
            # If pending update exists, reset flag and loop again
            self._color_update_pending = False
            
        self._sending_color_loop = False

    def go_back(self, instance):
        self.manager.transition.direction = 'right'
        self.manager.current = 'settings'

    def send_command(self, cmd_type):
        """Send command to all connected controllers in App"""
        controllers = App.get_running_app().controllers
        if not controllers:
            return # Do nothing if not connected

        asyncio.create_task(self._send_command(cmd_type, controllers))

    async def _send_command(self, cmd_type, controllers):
        """Modified to be more robust for direct calling without waiting"""
        tasks = []
        try:
            if cmd_type == "on":
                tasks = [c.set_power(True) for c in controllers]
            elif cmd_type == "off":
                tasks = [c.set_power(False) for c in controllers]
            elif cmd_type == "color":
                r, g, b = int(self.r_slider.value), int(self.g_slider.value), int(self.b_slider.value)
                tasks = [c.set_static_color(r, g, b) for c in controllers]
            elif cmd_type == "brightness":
                val = int(self.bri_slider.value)
                tasks = [c.set_brightness(val) for c in controllers]
            elif cmd_type == "mode":
                val = int(self.mode_slider.value)
                tasks = [c.set_mode(val) for c in controllers]
            elif cmd_type == "speed":
                val = int(self.speed_slider.value)
                tasks = [c.set_speed(val) for c in controllers]

            if tasks:
                await asyncio.gather(*tasks)
        except Exception as e:
            logger.error(f"Command send error: {e}")

# ---------------------------------------------------------
# Page 3: JSON Raw Editor (JsonEditorScreen)
# ---------------------------------------------------------
class JsonEditorScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        # Header
        header = BoxLayout(size_hint_y=None, height=50, spacing=10)
        btn_back = Button(text="Cancel", size_hint_x=0.3)
        btn_back.bind(on_press=self.go_back)
        header.add_widget(btn_back)
        header.add_widget(Label(text="Edit Device JSON", font_size=18))
        self.btn_save = Button(text="Save", size_hint_x=0.3, background_color=(0.2, 0.8, 0.2, 1))
        self.btn_save.bind(on_press=self.save_json)
        header.add_widget(self.btn_save)
        layout.add_widget(header)
        
        # Editor
        self.editor = TextInput(
            text="[]",
            multiline=True,
            font_name='Roboto', # Standard Kivy font
            background_color=(0.1, 0.1, 0.1, 1),
            foreground_color=(1, 1, 1, 1),
            cursor_color=(1, 1, 1, 1),
            size_hint_y=0.9
        )
        layout.add_widget(self.editor)
        
        self.add_widget(layout)

    def on_enter(self):
        """讀取暫存檔內容到編輯器"""
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                self.editor.text = f.read()
        else:
            self.editor.text = "[]"

    def go_back(self, instance):
        self.manager.transition.direction = 'right'
        self.manager.current = 'settings'

    def save_json(self, instance):
        try:
            # 驗證 JSON 語法
            data = json.loads(self.editor.text)
            if not isinstance(data, list):
                raise ValueError("Content must be a JSON list of MAC addresses")
            
            # 寫入檔案
            with open(DATA_FILE, 'w') as f:
                f.write(self.editor.text)
            
            # 同步更新 App 數據
            self.app.load_devices_from_disk()
            
            self.go_back(None)
        except Exception as e:
            # 顯示錯誤 (這裡可以使用 Kivy Popup，但簡單起見先改按鈕文字)
            self.btn_save.text = "Error!"
            self.btn_save.background_color = (1, 0.2, 0.2, 1)
            def reset_btn(dt):
                self.btn_save.text = "Save"
                self.btn_save.background_color = (0.2, 0.8, 0.2, 1)
            from kivy.clock import Clock
            Clock.schedule_once(reset_btn, 2)
            print(f"Save error: {e}")

# ---------------------------------------------------------
# App Main Program
# ---------------------------------------------------------
class DMXApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.controllers = [] # Store connected DMXController objects
        self.saved_devices = [] # Store MAC address strings

    def build(self):
        global DATA_FILE
        # 如果是 Android，使用私有資料夾；否則（如 Windows）優先使用程式同目錄
        if platform == 'android':
            DATA_FILE = os.path.join(self.user_data_dir, "dmx_devices.json")
        else:
            DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dmx_devices.json")
        
        # Create ScreenManager
        sm = ScreenManager()
        sm.add_widget(SettingsScreen(name='settings'))
        sm.add_widget(ScanScreen(name='scan'))
        sm.add_widget(ControlScreen(name='control'))
        sm.add_widget(JsonEditorScreen(name='json_editor'))
        return sm

    def on_start(self):
        # Request Android permissions
        if platform == 'android':
            from android.permissions import request_permissions, Permission
            def callback(permissions, results):
                if all(results):
                    logger.info("All permissions granted")
                else:
                    logger.info("Some permissions denied")
                    
            request_permissions([
                Permission.BLUETOOTH_SCAN,
                Permission.BLUETOOTH_CONNECT,
                Permission.ACCESS_FINE_LOCATION,
                Permission.ACCESS_COARSE_LOCATION
            ], callback)
        
        self.load_devices_from_disk()

    def load_devices_from_disk(self):
        """Load device list from JSON"""
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r') as f:
                    self.saved_devices = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load save file: {e}")
                self.saved_devices = []
        else:
            # If no save file, try loading defaults from DMX_test.py
            try:
                from DMX_test import DEVICE_ADDRESS
                if isinstance(DEVICE_ADDRESS, list):
                    self.saved_devices = DEVICE_ADDRESS
                elif isinstance(DEVICE_ADDRESS, str):
                    self.saved_devices = [DEVICE_ADDRESS]
                
                # Automatically save the defaults to create the file
                if self.saved_devices:
                    self.save_devices_to_disk()
            except ImportError:
                self.saved_devices = []

    def save_devices_to_disk(self):
        """Save device list to JSON"""
        try:
            with open(DATA_FILE, 'w') as f:
                json.dump(self.saved_devices, f)
        except Exception as e:
            logger.error(f"Failed to save file: {e}")

    # Ensure disconnection on exit
    def on_stop(self):
        asyncio.create_task(self.disconnect_all_on_exit())

    async def disconnect_all_on_exit(self):
        if self.controllers:
            tasks = [c.disconnect() for c in self.controllers]
            await asyncio.gather(*tasks)

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    app = DMXApp()

    try:
        loop.run_until_complete(app.async_run())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()