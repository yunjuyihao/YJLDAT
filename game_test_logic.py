# game_test_logic.py
import math

def print_statistics(values, log_func):
    """计算并打印延迟统计数据到指定的日志函数"""
    n = len(values)
    log_func("\n\n" + "="*20 + " 统计结果 " + "="*20)
    if n < 2:
        log_func("未收集到足够的有效延迟值。")
        if n == 1:
            log_func(f"仅有一次测量: {values[0]:.0f} µs ({values[0]/1000:.2f} ms)")
        return
        
    minimum = min(values)
    maximum = max(values)
    avg = sum(values) / n
    variance = sum((x - avg) ** 2 for x in values) / (n - 1) 
    stddev = math.sqrt(variance)
    
    log_func(f"有效测量次数: {n}")
    log_func(f"最小延迟    : {minimum:.0f} µs ({minimum/1000:.2f} ms)")
    log_func(f"最大延迟    : {maximum:.0f} µs ({maximum/1000:.2f} ms)")
    log_func(f"平均延迟    : {avg:.0f} µs ({avg/1000:.2f} ms)")
    log_func(f"样本标准差  : {stddev:.0f} µs ({stddev/1000:.2f} ms)")
    log_func("="*55)

def run_game_test(serial_manager, log_func, stop_event):
    """
    主测量逻辑，被设计为在后台线程中运行。
    :param serial_manager: GUI传入的已连接的SerialManager实例
    :param log_func: GUI传入的用于打印日志的函数
    :param stop_event: threading.Event对象，用于从外部停止循环
    """
    # --- 配置 ---
    MCU_TIMEOUT_VAL = 9999999
    MAX_ACCEPTABLE_US = 200000

    log_func("[INFO] 动态校准已启用：")
    log_func("       在未按下按键时，Pico会自动适应当前光照。")

    latencies = []
    collected_count = 0

    log_func("Game Test 监听器已启动。")
    log_func("说明：将光敏贴在开枪火光处，点击鼠标/外设按键触发测量。")
    log_func("点击 '退出当前测试模式' 按钮来结束测试并查看统计。")

    serial_manager.reset_buffers()
    
    while not stop_event.is_set():
        raw_line = serial_manager.readline_str()

        if not raw_line:
            # 超时，循环继续，检查 stop_event
            continue 
        if raw_line == "ERR_BRIGHT":
            log_func("[ALERT] 传感器过曝(0)！请调暗屏幕或调整传感器位置。")
            # 这里可以选择 break 退出测试，或者只是打印警告让用户调整
            continue 
        if raw_line == "ERR_DARK":
            log_func("[ALERT] 传感器截止(1023)！请确保传感器紧贴发光区域。")
            continue
        if raw_line.isdigit():
            latency_us = int(raw_line)
            
            if latency_us >= MCU_TIMEOUT_VAL:
                # 超时通常意味着只检测到了按键，没检测到屏幕变化
                log_func(f"[MCU] 未检测到屏幕光线变化 (超时).")
            elif latency_us > MAX_ACCEPTABLE_US:
                log_func(f"[RESULT] 值过大 ({latency_us} µs). 丢弃.")
            else:
                latencies.append(latency_us)
                collected_count += 1
                log_func(f"[RESULT] 延迟: ({latency_us/1000:.2f} ms)")
        else:
            # 过滤掉校准期间可能产生的杂波（虽然我们在校准时不打印，以防万一）
            if raw_line.strip():
                 log_func(f"[SERIAL] \"{raw_line}\"")

    log_func("[INFO] 收到停止信号，监听已结束。")
    print_statistics(latencies, log_func)
