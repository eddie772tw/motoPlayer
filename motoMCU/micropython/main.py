import machine
import network
import uasyncio as asyncio
import ujson
import time
import gc

# =================================================================
# --- 常數與腳位定義 (Constants and Pin Definitions) ---
# =================================================================

# -- 硬體腳位 (ESP8266 D1 Mini mappings) --
# D1 = GPIO 5 (SCL)
# D2 = GPIO 4 (SDA)
# D4 = GPIO 2 (LED_G_PIN - Builtin LED often)
# D0 = GPIO 16 (LED_B_PIN)

PIN_SDA = 4
PIN_SCL = 5
PIN_LED_G = 2
PIN_LED_B = 16

UNO_I2C_ADDRESS = 8
I2C_CHECK_INTERVAL_MS = 500
WIFI_TIMEOUT_MS = 15000
MDNS_HOSTNAME = "motoplayer"

# WiFi Credentials (from main.cpp)
STA_SSID = "motoplayer"
STA_PASSWORD = "password12345"
STA_SSID2 = "C80"
STA_PASSWORD2 = "eddie772tw"

# =================================================================
# --- 全域變數 (Global Variables) ---
# =================================================================

is_uno_online = False
last_rfid_from_uno = "N/A"

# Environment Data
current_temperature = -999.0
current_humidity = 0.0
light_level = 0
last_sensor_read_millis = 0

# LED State
blink_task_ref = None

# Hardware Objects
i2c = None
led_g = None
led_b = None
wlan = None

# =================================================================
# --- 硬體控制函式 (Hardware Control) ---
# =================================================================

def setup_hardware():
    global i2c, led_g, led_b, wlan
    
    # Initialize LEDs (Active LOW usually, matching C++ logic which seems to treat them that way for on/off? 
    # C++: setSolidLEDColor(false, false) -> writes HIGH (if common anode) or LOW.
    # C++ setLED: status==HIGH -> output=LOW. So Active LOW.
    led_g = machine.Pin(PIN_LED_G, machine.Pin.OUT)
    led_b = machine.Pin(PIN_LED_B, machine.Pin.OUT)
    set_solid_led_color(False, False)

    # Initialize I2C
    # Frequency default 400000 is usually fine, or 100000.
    i2c = machine.SoftI2C(scl=machine.Pin(PIN_SCL), sda=machine.Pin(PIN_SDA), freq=100000)
    
    # Initialize WiFi
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.config(dhcp_hostname=MDNS_HOSTNAME) # Attempt to set hostname

def set_led(pin, status):
    # status: True (ON) or False (OFF) in logical sense
    # C++: status==HIGH -> output=LOW. 
    val = 0 if status else 1
    
    global blink_task_ref
    if blink_task_ref:
        blink_task_ref.cancel()
        blink_task_ref = None

    if pin.lower() == 'g':
        led_g.value(val)
    elif pin.lower() == 'b':
        led_b.value(val)
    elif pin.lower() == 'a':
        led_g.value(val)
        led_b.value(val)

def set_solid_led_color(g_on, b_on):
    global blink_task_ref
    if blink_task_ref:
        blink_task_ref.cancel()
        blink_task_ref = None
        
    led_g.value(0 if g_on else 1)
    led_b.value(0 if b_on else 1)

async def blink_led_task(pin, interval_ms):
    state = True # Start ON
    t_sec = interval_ms / 1000.0
    
    target_leds = []
    if pin.lower() == 'g' or pin.lower() == 'a':
        target_leds.append(led_g)
    if pin.lower() == 'b' or pin.lower() == 'a':
        target_leds.append(led_b)
        
    try:
        while True:
            val = 0 if state else 1
            for l in target_leds:
                l.value(val)
            state = not state
            await asyncio.sleep(t_sec)
    except asyncio.CancelledError:
        pass

def start_blinking(pin, interval_ms):
    global blink_task_ref
    if blink_task_ref:
        blink_task_ref.cancel()
    blink_task_ref = asyncio.create_task(blink_led_task(pin, interval_ms))

# =================================================================
# --- I2C 與 邏輯 (I2C & Logic) ---
# =================================================================

async def i2c_loop():
    global is_uno_online, last_rfid_from_uno, current_temperature, current_humidity, light_level
    
    print("Starting I2C Loop...")
    
    while True:
        await asyncio.sleep_ms(I2C_CHECK_INTERVAL_MS)
        
        try:
            # Request 10 bytes
            data = i2c.readfrom(UNO_I2C_ADDRESS, 10)
            
            if len(data) == 10:
                if not is_uno_online:
                    print("I2C: Online.")
                    is_uno_online = True
                
                status_flag = data[0]
                
                if status_flag == 0x01:
                    # RFID
                    uid_raw = data[1:5]
                    # Convert to Hex String
                    uid_str = "".join(["{:02X}".format(b) for b in uid_raw])
                    last_rfid_from_uno = uid_str
                    print(f">>> Received RFID: {last_rfid_from_uno}")
                    
                elif status_flag == 0x02:
                    # Environment
                    # packetBuffer[1]<<8 | packetBuffer[2] -> temp * 10
                    t_raw = (data[1] << 8) | data[2]
                    # Python treats bytes as unsigned, so this is simple.
                    # Handle negative? C++ uses ((packetBuffer[1] << 8) | packetBuffer[2]) / 10.0
                    # If it's a signed 16-bit int, we might need correction, but let's assume valid range.
                    if t_raw > 32767: t_raw -= 65536 # Basic signed conversion if needed
                    current_temperature = t_raw / 10.0
                    
                    current_humidity = float(data[3])
                    light_level = (data[4] << 8) | data[5]
                    
                    print(f">>> Received ENV: Temp: {current_temperature}, Humid: {current_humidity}, Light: {light_level}")

                # Blink Blue briefly on success
                # Since we don't want to block, we just set it and let a background tiny task turn it off?
                # Or just ignore slight blocking for 10ms. C++ did delay(10).
                led_b.value(0) # ON
                await asyncio.sleep_ms(10)
                led_b.value(1) # OFF
                
            else:
                # Should not happen with readfrom if it returns
                pass
                
        except OSError:
            if is_uno_online:
                print("I2C: Connection lost")
            is_uno_online = False
            last_rfid_from_uno = "N/A"

def play_track(track_num):
    if not is_uno_online: return
    try:
        print(f"<<< Send CMD: Play track {track_num}")
        # 'P' is 0x50
        buf = bytes([0x50, track_num])
        i2c.writeto(UNO_I2C_ADDRESS, buf)
        
        # Blink Green
        led_g.value(0)
        time.sleep_ms(10)
        led_g.value(1)
    except OSError as e:
        print(f"I2C Write Error: {e}")

def chg_vol(vol_char):
    if not is_uno_online: return
    try:
        print(f"<<< Send CMD: Volume {vol_char}")
        buf = bytes([ord(vol_char)]) # '+' or '-'
        i2c.writeto(UNO_I2C_ADDRESS, buf)
        
        # Blink Green
        led_g.value(0)
        time.sleep_ms(10)
        led_g.value(1)
    except OSError as e:
        print(f"I2C Write Error: {e}")

# =================================================================
# --- Web Server (Minimal Async) ---
# =================================================================

def get_nav_footer():
    return """<hr style='margin-top: 50px;'>
<p>
<a href='/'>[首頁]</a> | 
<a href='/debug'>[測試頁面]</a> | 
<a href='/sensor'>[即時數據]</a> | 
<a href='/update'>[Update(Dummy)]</a>
</p>"""

async def handle_root(writer):
    ip = wlan.ifconfig()[0]
    mac = "".join(["{:02X}:".format(b) for b in wlan.config('mac')])[:-1]
    uno_status = "<span style='color: green;'>Online</span>" if is_uno_online else "<span style='color: red;'>Offline</span>"
    
    html = f"""<h1>MotoNodeMCU Control Panel (MicroPython)</h1>
<p>Access me at <a href='http://{MDNS_HOSTNAME}.local'>http://{MDNS_HOSTNAME}.local</a></p>
<h3>STA IP: {ip}</h3>
<h3>STA MAC: {mac}</h3>
<h3>UNO Module: {uno_status}</h3>
<h3>Last RFID Scanned: {last_rfid_from_uno}</h3>
<h3>Device Temp: {current_temperature:.1f} &deg;C</h3>
<h3>Device Humidity: {current_humidity:.1f} &#x25;</h3>
<h3>Device Light: {light_level}</h3>
{get_nav_footer()}"""
    
    await send_response(writer, 200, "text/html; charset=UTF-8", html)

async def handle_debug(writer):
    html = f"""<h1>Debug & Test Page</h1>
<h3>DFPlayer Control</h3>
播放第 <input type='number' id='trackNum' value='1' min='1' style='width: 50px;'> 首: 
<button onclick="playSpecificTrack()">Play</button><br>
<button onclick="sendCmd('vol_up')">Volume +</button> 
<button onclick="sendCmd('vol_down')">Volume -</button>
<h3>LED Control (Green / Blue)</h3>
<button onclick="sendCmd('blink_g')">Blink Green</button> 
<button onclick="sendCmd('blink_b')">Blink Blue</button> 
<button onclick="sendCmd('stop_blink')">Stop Blink</button><br>
<button onclick="sendCmd('on_g')">Green On</button> 
<button onclick="sendCmd('on_b')">Blue On</button><br>
<button onclick="sendCmd('off_g')">Green Off</button> 
<button onclick="sendCmd('off_b')">Blue Off</button>
<h3>System</h3>
<button onclick="if(confirm('你確定嗎？')) sendCmd('restart')">Restart Device</button>
<script>
function sendCmd(cmd) {{ fetch('/api/' + cmd).then(response => console.log(cmd + ' sent.')); }}
function playSpecificTrack() {{
  var trackId = document.getElementById('trackNum').value;
  if (trackId) {{ fetch('/api/play?track=' + trackId).then(response => console.log('Play track ' + trackId + ' command sent.')); }}
}}
</script>
{get_nav_footer()}"""
    await send_response(writer, 200, "text/html; charset=UTF-8", html)

async def handle_sensor_page(writer):
    html = f"""<h1>傳感器即時數據</h1>
<p>更新週期: 2.5秒</p>
<h2 style='font-size: 2em;'>UNO: <span id='UNO' style='color: #4b4b4b;'>--</span></h2>
<h2 style='font-size: 2em;'>溫度: <span id='temp' style='color: #E67E22;'>--</span> &deg;C</h2>
<h2 style='font-size: 2em;'>濕度: <span id='humid' style='color: #3498DB;'>--</span> &#x25;</h2>
<h2 style='font-size: 2em;'>日照: <span id='light' style='color: #F1C40F;'>--</span></h2>
<h2 style='font-size: 2em;'>卡號: <span id='card' style='color: #7F4448;'>--</span></h2>
<script>
function updateSensorData() {{
  fetch('/api/sensors').then(response => response.json())
    .then(data => {{
      document.getElementById('UNO').innerText = data.UNO;
      document.getElementById('UNO').style.color = (data.UNO == 'Online') ? '#2ECC71' : '#E74C3C';
      document.getElementById('temp').innerText = data.temperature.toFixed(1);
      document.getElementById('humid').innerText = data.humidity.toFixed(1);
      document.getElementById('light').innerText = data.light;
      document.getElementById('card').innerText = data.card;
    }}).catch(error => console.error('Error fetching sensor data:', error));
}}
window.onload = function() {{ updateSensorData(); setInterval(updateSensorData, 2500); }};
</script>
{get_nav_footer()}"""
    await send_response(writer, 200, "text/html; charset=UTF-8", html)

async def handle_api_sensors(writer):
    data = {
        "temperature": current_temperature,
        "humidity": current_humidity,
        "light": light_level,
        "card": last_rfid_from_uno,
        "UNO": "Online" if is_uno_online else "Offline"
    }
    await send_response(writer, 200, "application/json", ujson.dumps(data))

async def handle_api_play(writer, query_params):
    track_id = query_params.get('track', None)
    if track_id:
        try:
            tid = int(track_id)
            play_track(tid)
            await send_response(writer, 200, "text/plain", f"Play command for track {tid} sent.")
        except ValueError:
            await send_response(writer, 400, "text/plain", "Invalid track number")
    else:
        await send_response(writer, 400, "text/plain", "Missing track parameter")

async def send_response(writer, status_code, content_type, content):
    response_header = f"HTTP/1.1 {status_code} OK\r\nContent-Type: {content_type}\r\nAccess-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n"
    writer.write(response_header.encode())
    writer.write(content.encode())
    await writer.drain()
    writer.close()

async def web_server_handler(reader, writer):
    try:
        request_line = await reader.readline()
        if not request_line:
            writer.close()
            return
        
        request_str = request_line.decode().strip()
        method, path, _ = request_str.split()
        
        # Parse Query Params
        query_params = {}
        if '?' in path:
            path, query = path.split('?', 1)
            for pair in query.split('&'):
                if '=' in pair:
                    k, v = pair.split('=', 1)
                    query_params[k] = v
        
        print(f"WEB: {method} {path}")
        
        # Simple Routing
        if path == "/":
            await handle_root(writer)
        elif path == "/debug":
            await handle_debug(writer)
        elif path == "/sensor":
            await handle_sensor_page(writer)
        elif path == "/api/sensors":
            await handle_api_sensors(writer)
        elif path == "/api/play":
            await handle_api_play(writer, query_params)
        elif path == "/api/vol_up":
            chg_vol('+')
            await send_response(writer, 200, "text/plain", "OK")
        elif path == "/api/vol_down":
            chg_vol('-')
            await send_response(writer, 200, "text/plain", "OK")
        elif path == "/api/blink_g":
            start_blinking('G', 250)
            await send_response(writer, 200, "text/plain", "OK")
        elif path == "/api/blink_b":
            start_blinking('B', 250)
            await send_response(writer, 200, "text/plain", "OK")
        elif path == "/api/on_g":
            set_led('G', True)
            await send_response(writer, 200, "text/plain", "OK")
        elif path == "/api/on_b":
            set_led('B', True)
            await send_response(writer, 200, "text/plain", "OK")
        elif path == "/api/off_g":
            set_led('G', False)
            await send_response(writer, 200, "text/plain", "OK")
        elif path == "/api/off_b":
            set_led('B', False)
            await send_response(writer, 200, "text/plain", "OK")
        elif path == "/api/stop_blink":
            set_solid_led_color(False, False)
            await send_response(writer, 200, "text/plain", "OK")
        elif path == "/api/restart":
            await send_response(writer, 200, "text/plain", "Restarting...")
            await asyncio.sleep(0.5)
            machine.reset()
        else:
            await send_response(writer, 404, "text/plain", "Not Found")
            
    except Exception as e:
        print(f"WEB Error: {e}")
        writer.close()

# =================================================================
# --- Main Logic ---
# =================================================================

async def main():
    setup_hardware()
    
    print("--- MotoNodeMCU MicroPython Booting ---")
    
    # WiFi Connect
    wlan.connect(STA_SSID, STA_PASSWORD)
    
    t_start = time.ticks_ms()
    led_state = True
    
    # Blinking while connecting
    print("Connecting to WiFi...")
    while not wlan.isconnected():
        led_g.value(0 if led_state else 1)
        led_state = not led_state
        await asyncio.sleep_ms(300)
        if time.ticks_diff(time.ticks_ms(), t_start) > WIFI_TIMEOUT_MS:
            print("WiFi Connect Timeout")
            break
            
    set_solid_led_color(False, False)
    
    if wlan.isconnected():
        print("Connected!")
        print("IP:", wlan.ifconfig()[0])
    
    # Start I2C polling task
    asyncio.create_task(i2c_loop())
    
    # Start Web Server
    print("Starting Web Server...")
    await asyncio.start_server(web_server_handler, "0.0.0.0", 80)
    
    while True:
        await asyncio.sleep(1)
        gc.collect()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
