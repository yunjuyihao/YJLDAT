# mouse_rate_logic.py
import mouse
import time
import collections
from queue import Queue, Empty

def run_mouse_rate_test(log_func, stop_event, window_size=100):
    log_func(f"[MOUSE_RATE] 鼠标回报率检测器启动 (采样窗口: {window_size})")
    log_func("[MOUSE_RATE] 请快速移动鼠标以获得准确读数...")
    event_queue = Queue()    
    timestamps = collections.deque(maxlen=window_size + 1)
    
    max_hz = 0
    current_hz = 0

    def _on_move(event):
        if isinstance(event, mouse.MoveEvent):
            event_queue.put(time.perf_counter_ns())

    # 启动鼠标钩子
    mouse.hook(_on_move)
    
    last_print_time = 0
    
    try:
        while not stop_event.is_set():
            try:
                timestamp = event_queue.get(timeout=0.05)
                timestamps.append(timestamp)

                if len(timestamps) > window_size:
                    # 计算逻辑
                    intervals = []
                    for i in range(1, len(timestamps)):
                        diff_ns = timestamps[i] - timestamps[i-1]
                        diff_sec = diff_ns / 1_000_000_000.0
                        if 0 < diff_sec < 0.1: # 过滤停顿
                            intervals.append(diff_sec)
                    
                    if intervals:
                        avg_interval = sum(intervals) / len(intervals)
                        if avg_interval > 0:
                            current_hz = int(1 / avg_interval)
                            if current_hz > max_hz:
                                max_hz = current_hz
                    else:
                        current_hz = 0 
                
                # 限制日志刷新频率 (每 0.25 秒输出一次)
                current_time = time.time()
                if current_time - last_print_time > 0.25:
                    # 注意：不要频繁 log 刷屏，这里我们只输出当前状态
                    if current_hz > 0:
                        log_func(f"实时回报率: {current_hz:5d} Hz | 峰值: {max_hz:5d} Hz")
                    last_print_time = current_time

            except Empty:
                current_hz = 0
                # 队列空闲时也稍微检查一下时间，避免长时间无输出感觉像卡死
                current_time = time.time()
                if current_time - last_print_time > 1.0:
                    # log_func("[MOUSE_RATE] 等待鼠标移动...") 
                    last_print_time = current_time
                continue
                
    except Exception as e:
        log_func(f"[ERROR] 鼠标测试出错: {e}")
    finally:
        mouse.unhook(_on_move)
        log_func(f"[MOUSE_RATE] 测试结束。本次最高峰值: {max_hz} Hz")
