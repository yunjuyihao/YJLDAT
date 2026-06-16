# reaction_test_logic.py
import math

def print_statistics(values, log_func):
    n = len(values)
    log_func("\n" + "="*20 + " 反应速度统计 " + "="*20)
    if n < 1:
        log_func("无有效数据。")
        return
    minimum = min(values)
    maximum = max(values)
    avg = sum(values) / n
    variance = sum((x - avg) ** 2 for x in values) / (n - 1) if n > 1 else 0.0
    stddev = math.sqrt(variance)
    
    log_func(f"成功次数    : {n}")
    log_func(f"最快反应    : {minimum:.2f} ms")
    log_func(f"最慢反应    : {maximum:.2f} ms")
    log_func(f"平均反应    : {avg:.2f} ms")
    log_func(f"标准差      : {stddev:.2f} ms")
    log_func("="*55)

def run_reaction_test(serial_manager, log_func, stop_event):
    """
    反应速度测试逻辑 (M4)
    """
    log_func("[INFO] 反应速度测试已启动。")
    log_func("[INFO] 流程：让铜箔接地->随机等待3-5秒 -> 灯亮 -> 立即抬手离开铜箔。")
    
    latencies = []
    
    # 清空缓冲
    serial_manager.reset_buffers()
    
    while not stop_event.is_set():
        # 这里的 readline 可能会被阻塞直到串口有数据或超时
        # 固件在等待期不会发数据，所以这里大部分时间在空转或阻塞
        raw_line = serial_manager.readline_str()

        if not raw_line:
            continue

        if raw_line == "EARLY":
            log_func("[WARN] 抢跑！(在灯亮前触发)")
        elif raw_line == "TIMEOUT":
            log_func("[INFO] 超时 (未在1秒内响应)")
        elif raw_line.isdigit():
            # 固件返回的是微秒
            ms = int(raw_line) / 1000.0
            latencies.append(ms)
            log_func(f"[RESULT] 反应时间: {ms:.2f} ms")
        else:
            # 过滤杂波
            if raw_line.strip():
                log_func(f"[SERIAL] {raw_line}")

    log_func("[INFO] 测试结束。")
    print_statistics(latencies, log_func)
