import sys
import os
import subprocess
import time
import argparse
import serial.tools.list_ports

# Configuration
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
MICROPYTHON_BIN = os.path.join(PROJECT_ROOT, "micropython", "firmware.bin")
MICROPYTHON_MAIN = os.path.join(PROJECT_ROOT, "micropython", "main.py")
CPP_BIN_DIR = os.path.join(PROJECT_ROOT, ".pio", "build", "nodemcuv2")
BENCHMARK_TOOL = os.path.join(PROJECT_ROOT, "benchmark_tool.py")

DEFAULT_BAUD = 460800
TARGET_IP = "192.168.9.2"

def find_esp_port():
    ports = list(serial.tools.list_ports.comports())
    # Try to find a likely candidate (CH340, CP210x often used for NodeMCU)
    for p in ports:
        if "USB-SERIAL" in p.description or "CP210" in p.description or "CH340" in p.description:
            return p.device
    # Fallback: return first port or None
    if ports:
        return ports[0].device
    return None

def run_command(cmd, cwd=None, ignore_error=False):
    print(f"\n[EXEC] {cmd}")
    try:
        subprocess.check_call(cmd, shell=True, cwd=cwd)
        return True
    except subprocess.CalledProcessError:
        if not ignore_error:
            print(f"[ERROR] Command failed: {cmd}")
            sys.exit(1)
        return False

def wait_for_online(ip, timeout=30):
    print(f"Waiting for device ({ip}) to come online...", end="", flush=True)
    start = time.time()
    while time.time() - start < timeout:
        # Use benchmark tool's check or simple ping/request
        # Simplest is just ping, but let's try to wget root
        try:
            subprocess.check_output(f"python \"{BENCHMARK_TOOL}\" {ip} --check-only", shell=True, stderr=subprocess.STDOUT)
            print(" Online!")
            return True
        except subprocess.CalledProcessError:
            pass
        
        time.sleep(1)
        print(".", end="", flush=True)
    print(" Timeout!")
    return False

def test_cpp(port):
    print("\n=== Testing C++ Firmware ===")
    
    # 1. Build & Upload
    # pio run -t upload
    # We assume 'pio' is in path
    cmd = f"pio run -t upload --upload-port {port}"
    run_command(cmd, cwd=PROJECT_ROOT)
    
    # 2. Monitor/Wait
    # Wait for WiFi connection (hardcoded delay or smart check)
    time.sleep(5) 
    if not wait_for_online(TARGET_IP):
        print("Device failed to connect to WiFi.")
        return
        
    # 3. Benchmark
    run_command(f"python \"{BENCHMARK_TOOL}\" {TARGET_IP}", cwd=PROJECT_ROOT)

def test_mp(port):
    print("\n=== Testing MicroPython Firmware ===")
    
    if not os.path.exists(MICROPYTHON_BIN):
        print(f"[ERROR] MicroPython binary not found at: {MICROPYTHON_BIN}")
        print("Please download it from micropython.org and place it there.")
        sys.exit(1)
        
    # 1. Flash Firmware
    print("Erasing flash...")
    run_command(f"esptool.py --port {port} erase_flash")
    
    print("Writing firmware...")
    run_command(f"esptool.py --port {port} --baud {DEFAULT_BAUD} write_flash --flash_size=detect 0 \"{MICROPYTHON_BIN}\"")
    
    # 2. Upload Code
    print("Uploading main.py...")
    # Give it a moment to boot after flash
    time.sleep(3)
    # ampy needs a bit of reset sometimes, or just try put
    # We allow retries for ampy
    success = False
    for i in range(3):
        try:
            # Set environment variable for ampy port or use -p
            # ampy -p COMx put ...
            # We might need to enforce raw mode or delay
            run_command(f"ampy -p {port} -d 1.5 put \"{MICROPYTHON_MAIN}\" main.py", ignore_error=False)
            success = True
            break
        except:
            print("Retrying upload...")
            time.sleep(2)
    
    if not success:
        print("[ERROR] Failed to upload main.py")
        sys.exit(1)
        
    # 3. Reset
    print("Resetting board...")
    # ampy reset is soft reset, hard reset is better.
    # We can use esptool to reset or just tell user to press button? 
    # Or use pyserial to toggle DTR/RTS
    try:
        import serial
        with serial.Serial(port) as ser:
            ser.dtr = False
            ser.rts = True
            time.sleep(0.1)
            ser.rts = False
            time.sleep(0.1)
    except:
        print("Could not hard-reset via serial, please press Reset button if needed.")
        
    # 4. Benchmark
    if not wait_for_online(TARGET_IP, timeout=40): # MP takes longer to connect maybe
        print("Device failed to connect to WiFi.")
        return
        
    run_command(f"python \"{BENCHMARK_TOOL}\" {TARGET_IP}", cwd=PROJECT_ROOT)

def main():
    parser = argparse.ArgumentParser(description="Automated Flash & Test for MotoMCU")
    parser.add_argument("--mode", choices=["cpp", "mp", "all"], default="all", help="Test mode")
    parser.add_argument("--port", help="COM port (auto-detect if missing)")
    parser.add_argument("--ip", default="192.168.9.2", help="Target Device IP")
    
    args = parser.parse_args()
    
    global TARGET_IP
    TARGET_IP = args.ip
    
    port = args.port
    if not port:
        port = find_esp_port()
        if not port:
            print("Could not auto-detect ESP8266. Please specify --port.")
            sys.exit(1)
        print(f"Auto-detected Port: {port}")
    
    if args.mode == "cpp":
        test_cpp(port)
    elif args.mode == "mp":
        test_mp(port)
    elif args.mode == "all":
        test_cpp(port)
        print("\n\n" + "="*50 + "\n\n")
        time.sleep(2)
        test_mp(port)

if __name__ == "__main__":
    main()
