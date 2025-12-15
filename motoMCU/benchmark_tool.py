import sys
import time
import threading
import urllib.request
import json
from concurrent.futures import ThreadPoolExecutor

# Default Target
TARGET_IP = "192.168.9.2"
CONCURRENCY = 10
DURATION = 10 # seconds per test

def get_url(path):
    return f"http://{TARGET_IP}{path}"

def fetch_worker(url, results, stop_event):
    while not stop_event.is_set():
        start = time.time()
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                _ = response.read()
                code = response.getcode()
                latency = time.time() - start
                results.append({"code": code, "latency": latency, "error": None})
        except Exception as e:
            latency = time.time() - start
            results.append({"code": 0, "latency": latency, "error": str(e)})

def run_benchmark(name, path, duration, concurrency):
    print(f"\n--- Benchmarking: {name} ({path}) ---")
    print(f"Concurrency: {concurrency}, Duration: {duration}s")
    
    stop_event = threading.Event()
    results = []
    
    url = get_url(path)
    
    # Warmup
    print("Warming up...")
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            pass
    except:
        print("Warmup failed! Is the device online?")
        return

    threads = []
    for _ in range(concurrency):
        t = threading.Thread(target=fetch_worker, args=(url, results, stop_event))
        t.start()
        threads.append(t)
        
    start_time = time.time()
    while time.time() - start_time < duration:
        time.sleep(0.1)
        
    stop_event.set()
    for t in threads:
        t.join()
        
    # Analysis
    total_reqs = len(results)
    success_reqs = len([r for r in results if r["code"] == 200])
    failed_reqs = len([r for r in results if r["code"] != 200])
    
    latencies = [r["latency"] for r in results if r["code"] == 200]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    max_latency = max(latencies) if latencies else 0
    min_latency = min(latencies) if latencies else 0
    
    rps = success_reqs / duration
    
    print(f"Total Requests: {total_reqs}")
    print(f"Successful: {success_reqs}")
    print(f"Failed: {failed_reqs}")
    print(f"RPS: {rps:.2f}")
    print(f"Latency (Avg/Min/Max): {avg_latency*1000:.2f}ms / {min_latency*1000:.2f}ms / {max_latency*1000:.2f}ms")

def main():
    global TARGET_IP
    args = sys.argv[1:]
    if len(args) > 0:
        TARGET_IP = args[0]
        
    print(f"Target Device IP: {TARGET_IP}")
    
    print("Checking connection...")
    try:
        urllib.request.urlopen(get_url("/"), timeout=2)
        print("Device Online.")
    except Exception as e:
        print(f"Could not connect to device: {e}")
        print("Make sure the device is powered on and connected to the same network.")
        return

    # Test 1: JSON API (Lightweight)
    run_benchmark("JSON API (Sensors)", "/api/sensors", DURATION, CONCURRENCY)
    
    # Test 2: HTML Page (Heavier)
    run_benchmark("HTML Page (Root)", "/", DURATION, CONCURRENCY)

if __name__ == "__main__":
    main()
