import time

def test_memoryview_int():
    data = b"410C1AF8"
    mv = memoryview(data)
    
    # Slice RPM part: 1AF8 (index 4 to 8)
    chunk = mv[4:8]
    
    try:
        val = int(chunk, 16)
        print(f"Success: int(memoryview, 16) = {val}")
        return True
    except TypeError as e:
        print(f"Failure: int() does not support memoryview directly. Error: {e}")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_bitwise_speed():
    iterations = 1000000
    val = 0x1AF8 # 6904
    
    start = time.perf_counter()
    for _ in range(iterations):
        x = int(val / 4)
    dt_div = time.perf_counter() - start
    
    start = time.perf_counter()
    for _ in range(iterations):
        x = val >> 2
    dt_shift = time.perf_counter() - start
    
    print(f"Division /4 time: {dt_div:.6f}s")
    print(f"Shift >>2 time:   {dt_shift:.6f}s")
    print(f"Speedup: {dt_div/dt_shift:.2f}x")

if __name__ == "__main__":
    print("--- Testing Memoryview ---")
    supports_mv = test_memoryview_int()
    
    print("\n--- Testing Bitwise Speed ---")
    test_bitwise_speed()
