# display_test_logic.py
import pyglet
import pyglet.gl as gl
from pyglet.window import FPSDisplay
import time
import math
import random

def run_display_test(serial_manager, log_func):
    """
    运行显示器延迟测试 (M1模式)
    必须在主线程运行
    """
    # --- 配置 ---
    try:
        serial_manager.write(b'M1')
        time.sleep(0.1) # 给一点时间让Pico切换模式
        pyglet.options['vsync'] = False
    except Exception as e:
        log_func(f"[ERROR] 串口通信失败: {e}")
        return

    TOTAL_MEASUREMENTS = 200
    FULLSCREEN_STABILIZE = 5
    TIMEOUT_SECONDS = 2.0 
    
    state = {
        "is_measuring": False, 
        "measurement_idx": 0, 
        "latencies": [], 
        "measurement_start_time": 0.0, 
        "rtt_avg_us": 0.0, 
        "finalize_and_exit": False
    }
    
    try:
        config = gl.Config(double_buffer=True, vsync=False)
        window = pyglet.window.Window(500, 400, caption="Display Latency Test", config=config, resizable=False)
    except Exception as e:
        log_func(f"[PYGLET ERROR] 创建窗口失败: {e}")
        return

    label = pyglet.text.Label('按空格开始测试，ESC中途退出', font_name='SimHei', font_size=20, 
                              x=window.width // 2, y=window.height // 2, anchor_x='center', anchor_y='center', color=(0, 0, 0, 255))
    gl.glClearColor(1, 1, 1, 1)
    fps_display = FPSDisplay(window=window)
    # --- [新增] 获取当前系统刷新率 ---
    def get_current_windows_refresh_rate():
        try:
            import ctypes # 确保导入
            class DEVMODE(ctypes.Structure):
                _fields_ = [("dmDeviceName", ctypes.c_wchar * 32),
                            ("dmSpecVersion", ctypes.c_ushort),
                            ("dmDriverVersion", ctypes.c_ushort),
                            ("dmSize", ctypes.c_ushort),
                            ("dmDriverExtra", ctypes.c_ushort),
                            ("dmFields", ctypes.c_ulong),
                            ("dmPositionX", ctypes.c_long),
                            ("dmPositionY", ctypes.c_long),
                            ("dmDisplayOrientation", ctypes.c_ulong),
                            ("dmDisplayFixedOutput", ctypes.c_ulong),
                            ("dmColor", ctypes.c_short),
                            ("dmDuplex", ctypes.c_short),
                            ("dmYResolution", ctypes.c_short),
                            ("dmTTOption", ctypes.c_short),
                            ("dmCollate", ctypes.c_short),
                            ("dmFormName", ctypes.c_wchar * 32),
                            ("dmLogPixels", ctypes.c_ushort),
                            ("dmBitsPerPel", ctypes.c_ulong),
                            ("dmPelsWidth", ctypes.c_ulong),
                            ("dmPelsHeight", ctypes.c_ulong),
                            ("dmDisplayFlags", ctypes.c_ulong),
                            ("dmDisplayFrequency", ctypes.c_ulong)]
            
            dm = DEVMODE()
            dm.dmSize = ctypes.sizeof(dm)
            # -1 代表获取当前设置 (ENUM_CURRENT_SETTINGS)
            if ctypes.windll.user32.EnumDisplaySettingsW(None, -1, ctypes.byref(dm)):
                return int(dm.dmDisplayFrequency)
        except Exception:
            pass
        return 60 # 获取失败时的保守默认值

    def print_statistics(values):
        n = len(values)
        log_func("\n\n=== TEST COMPLETE ===")
        if n < 2: 
            log_func("未收集到足够的有效延迟值。")
            return
        minimum, maximum, avg = min(values), max(values), sum(values) / n
        variance = sum((x - avg) ** 2 for x in values) / (n - 1)
        stddev = math.sqrt(variance)
        log_func(f"有效测量次数: {n}")
        log_func(f"最小延迟: {minimum:.0f} µs ({minimum/1000:.2f} ms)")
        log_func(f"最大延迟: {maximum:.0f} µs ({maximum/1000:.2f} ms)")
        log_func(f"平均延迟: {avg:.0f} µs ({avg/1000:.2f} ms)")
        log_func(f"样本标准差: {stddev:.0f} µs ({stddev/1000:.2f} ms)")

    def measure_rtt(trials=600):
        prev_timeout = serial_manager.timeout
        serial_manager.timeout = 0.05
        serial_manager.reset_buffers()
        rtts = []
        for _ in range(trials):
            try:
                t0 = time.perf_counter()
                serial_manager.write(b'R')
                resp = serial_manager.ser.read(1)
                t1 = time.perf_counter()
                if resp: rtts.append((t1 - t0) * 1_000_000.0)
            except Exception: pass
            time.sleep(0.001)
        serial_manager.timeout = prev_timeout
        return (sum(rtts) / len(rtts)) if rtts else 0.0

    def finalize_and_exit():
        print_statistics([v for v in state["latencies"] if v is not None])
        log_func(f"\n[RTT] RTT 平均值 = {state['rtt_avg_us']:.1f} µs")
        state["is_measuring"] = False
        state["finalize_and_exit"] = True

    def check_serial_for_result(dt):
        if serial_manager.ser.in_waiting > 0:
            raw = serial_manager.readline_str()
            if raw == "ERR_BRIGHT":
                log_func("[ERROR] 传感器过曝 (读数为0)！环境太亮或阈值不合适，测试终止。")
                finalize_and_exit() # 或者只是停止本次测量 state["is_measuring"] = False
                return
            if raw == "ERR_DARK":
                log_func("[ERROR] 传感器截止 (读数4095)！屏幕太暗或未对准，测试终止。")
                finalize_and_exit()
                return            
            if raw.isdigit():
                latency_us = int(raw)
                if latency_us == 0: 
                    log_func("[RESULT] 超时 (Pico端未检测到变暗)")
                    state["latencies"].append(None)
                else:
                    corrected = latency_us + (state["rtt_avg_us"] / 2.0)
                    state["latencies"].append(corrected if corrected > 0 else 0.0)
                    log_func(f"[RESULT] raw={latency_us} µs  corrected={corrected:.0f} µs")
                
                pyglet.clock.unschedule(check_serial_for_result)
                state["measurement_idx"] += 1
                if state["measurement_idx"] < TOTAL_MEASUREMENTS: 
                    pyglet.clock.schedule_once(start_next_measurement, random.uniform(0.05, 0.1))
                else: 
                    finalize_and_exit()
                return

        if time.time() - state["measurement_start_time"] > TIMEOUT_SECONDS:
            log_func("[ERROR] 等待Pico响应超时 (Python端).")
            pyglet.clock.unschedule(check_serial_for_result)
            finalize_and_exit()

    def send_start_signal(dt):
        gl.glClearColor(0.6, 0.6, 0.6, 1) # 变暗
        window.clear()
        window.flip()
        serial_manager.write(b'S') # 通知Pico开始计时
        state["measurement_start_time"] = time.time()
        log_func(f"\n[MEAS] 子测量 #{state['measurement_idx'] + 1}/{TOTAL_MEASUREMENTS}")
        pyglet.clock.schedule_interval(check_serial_for_result, 1 / 1000)

    def start_next_measurement(dt=0):
        gl.glClearColor(1, 1, 1, 1) # 变白
        window.clear()
        window.flip()
        pyglet.clock.schedule_once(send_start_signal, 0.06)

    @window.event
    def on_draw(): 
        window.clear()
        fps_display.draw()
        if not state["is_measuring"]: label.draw()

    @window.event
    def on_key_press(symbol, modifiers):
        if symbol == pyglet.window.key.SPACE and not state["is_measuring"]:
            state["is_measuring"] = True
            log_func(f"\n=== 开始 {TOTAL_MEASUREMENTS} 次延迟测试 ===")
            
            # --- [修改开始] 智能匹配全屏模式 ---
            try:
                log_func("[INFO] 正在分析显示器模式...")
                display = pyglet.display.get_display()
                screen = display.get_default_screen()
                modes = screen.get_modes()
                
                # 1. 获取当前桌面的分辨率
                current_w = screen.width
                current_h = screen.height
                
                # 2. 获取当前桌面的刷新率 (Windows API)
                current_hz = get_current_windows_refresh_rate()
                log_func(f"[SYS] 检测到当前桌面: {current_w}x{current_h} @ {current_hz}Hz")

                target_mode = None
                
                # 3. 在所有可用模式中，寻找完全匹配的一项
                candidates = []
                for m in modes:
                    if m.width == current_w and m.height == current_h:
                        candidates.append(m)
                
                # 从同分辨率的候选者中，找刷新率最接近的
                if candidates:
                    candidates.sort(key=lambda m: abs(m.rate - current_hz))
                    target_mode = candidates[0]
                
                if target_mode:
                    log_func(f"[MODE] 锁定独占模式: {target_mode.width}x{target_mode.height} @ {target_mode.rate}Hz")
                    window.set_fullscreen(True, screen=screen, mode=target_mode)
                else:
                    log_func("[WARN] 未找到完美匹配的模式，使用默认全屏")
                    window.set_fullscreen(True, screen=screen)

            except Exception as e:
                log_func(f"[ERROR] 全屏切换异常: {e}")
                window.set_fullscreen(True)
            # --- [修改结束] ---
            
            log_func(f"[INFO] 等待 {FULLSCREEN_STABILIZE:.1f}s 以稳定全屏...")
            
            def after_fullscreen_settle(dt):
                log_func("[CALIB] 正在通知Pico进行光感校准 (0.5s)...")
                serial_manager.write(b'C')
                time.sleep(1.0)
                log_func("[CALIB] 校准完成。")

                log_func("[INFO] 正在执行RTT测量...")
                state["rtt_avg_us"] = measure_rtt()
                log_func(f"[INFO] RTT 平均值 = {state['rtt_avg_us']:.1f} µs")
                
                gl.glClearColor(1, 1, 1, 1)
                window.clear()
                window.flip()
                pyglet.clock.schedule_once(start_next_measurement, 0.5)

            pyglet.clock.schedule_once(after_fullscreen_settle, FULLSCREEN_STABILIZE)
        elif symbol == pyglet.window.key.ESCAPE: 
            finalize_and_exit()


    while not state["finalize_and_exit"] and not window.has_exit:
        pyglet.clock.tick()
        window.dispatch_events()
        window.dispatch_event('on_draw')
        window.flip()
    
    window.close()
    pyglet.clock.unschedule(check_serial_for_result)
    pyglet.clock.unschedule(send_start_signal)
    pyglet.clock.unschedule(start_next_measurement)
    log_func("[PYGLET] 窗口已关闭。")
