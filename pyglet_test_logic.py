# pyglet_test_logic.py
import pyglet
import pyglet.gl as gl
from pyglet.window import FPSDisplay
import time
import math

def run_pyglet_test(serial_manager, log_func):
    """
    运行理想游戏全链路延迟测试 (Pyglet Test)
    必须在主线程运行
    """
    # --- 配置 ---
    try:
        serial_manager.write(b'M2') # 注意：这里使用 M2 (Game Mode) 配合屏幕变黑
        time.sleep(0.1)
        pyglet.options['vsync'] = False
    except Exception as e:
        log_func(f"[ERROR] 串口通信失败: {e}")
        return

    PER_MEAS_TIMEOUT_S = 2.0 
    CHECK_INTERVAL = 1 / 1000.0
    MAX_ACCEPTABLE_US = 150000
    
    state = {
        "is_measuring": False, 
        "latencies": [], 
        "waiting_for_response": False, 
        "measurement_start_time": 0.0, 
        "current_color": (1.0, 1.0, 1.0, 1.0), 
        "should_exit": False
    }
    
    try:
        config = gl.Config(double_buffer=True, vsync=False)
        window = pyglet.window.Window(800, 600, caption="Ideal Game Latency Test", config=config, resizable=False)
    except Exception as e: 
        log_func(f"[PYGLET ERROR] 创建窗口失败: {e}")
        return
    
    label = pyglet.text.Label('按空格开始\n按鼠标左键触发变色\n按esc退出', 
                              font_name='SimHei', font_size=18, x=window.width // 2, y=window.height // 2, 
                              anchor_x='center', anchor_y='center', color=(0, 0, 0, 255), multiline=True, width=600)
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

    def finalize_and_exit(): 
        print_statistics(state["latencies"])
        state["should_exit"] = True

    def force_redraw(): 
        r, g, b, a = state["current_color"]
        gl.glClearColor(r, g, b, a)
        window.clear()
        window.flip()

    def prepare_for_next_click(dt=0): 
        state["current_color"] = (1.0, 1.0, 1.0, 1.0)
        force_redraw()

    def check_serial_for_result(dt):
        try:
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
                if raw and raw.lstrip('-').isdigit():
                    latency_us = int(raw)
                    if latency_us == 0: 
                        log_func(f"[RESULT] 超时 (Pico端未检测到变黑)")
                    elif latency_us > MAX_ACCEPTABLE_US: 
                        log_func(f"[RESULT] raw={latency_us} µs  -> 过大. 丢弃.")
                    else: 
                        state["latencies"].append(latency_us)
                        log_func(f"[RESULT] raw={latency_us} µs  -> 接受 ({len(state['latencies'])})")
                    
                    pyglet.clock.unschedule(check_serial_for_result)
                    state["waiting_for_response"] = False
                    pyglet.clock.schedule_once(prepare_for_next_click, 0.05)
                    return
            
            if time.time() - state["measurement_start_time"] > PER_MEAS_TIMEOUT_S: 
                log_func("[WARN] 等待MCU响应超时.")
                pyglet.clock.unschedule(check_serial_for_result)
                state["waiting_for_response"] = False
                pyglet.clock.schedule_once(prepare_for_next_click, 0.05)
        except Exception as e: 
            log_func(f"[ERROR] 串口读取时出错: {e}")
            pyglet.clock.unschedule(check_serial_for_result)
            state["waiting_for_response"] = False

    @window.event
    def on_draw(): 
        r, g, b, a = state["current_color"]
        gl.glClearColor(r, g, b, a)
        window.clear()
        fps_display.draw()
        if not state["is_measuring"]: label.draw()

    @window.event
    def on_mouse_press(x, y, button, modifiers):
        if not state["is_measuring"] or button != pyglet.window.mouse.LEFT: return
        if state["waiting_for_response"]: 
            log_func("[WARN] 仍在等待上一次响应，本次点击忽略。")
            return
        
        serial_manager.reset_buffers()
        
        # 立即变黑
        state["current_color"] = (0.6, 0.6, 0.6, 1.0)
        force_redraw()
        
        state["waiting_for_response"] = True
        state["measurement_start_time"] = time.time()
        pyglet.clock.schedule_interval(check_serial_for_result, CHECK_INTERVAL)
        log_func(f"\n[MEAS] 点击触发于 ({x},{y}). 等待MCU响应...")

    @window.event
    def on_key_press(symbol, modifiers):
        if symbol == pyglet.window.key.SPACE and not state["is_measuring"]:
            state["is_measuring"] = True
            state["latencies"] = []
            
            # --- [修改开始] 智能匹配全屏模式 ---
            try:
                log_func("[INFO] 正在分析显示器模式...")
                display = pyglet.display.get_display()
                screen = display.get_default_screen()
                modes = screen.get_modes()
                
                current_w = screen.width
                current_h = screen.height
                current_hz = get_current_windows_refresh_rate()
                log_func(f"[SYS] 检测到当前桌面: {current_w}x{current_h} @ {current_hz}Hz")

                target_mode = None
                candidates = []
                for m in modes:
                    if m.width == current_w and m.height == current_h:
                        candidates.append(m)
                
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
            
            state["current_color"] = (1.0, 1.0, 1.0, 1.0)
            force_redraw()

            def perform_calibration_sequence(dt):
                log_func("[INFO] 独占全屏模式已就绪。")
                log_func("[CALIB] 发送校准指令 'C' (用于M2模式)...")
                serial_manager.write(b'C') 
                # M2 模式下，发送 'C' 会触发光感适应
            
            pyglet.clock.schedule_once(perform_calibration_sequence, 5.0)

        elif symbol == pyglet.window.key.ESCAPE: 
            finalize_and_exit()


    while not state["should_exit"] and not window.has_exit:
        pyglet.clock.tick()
        window.dispatch_events()
        window.dispatch_event('on_draw')
        window.flip()
    
    pyglet.clock.unschedule(check_serial_for_result)
    pyglet.clock.unschedule(prepare_for_next_click)
    window.close()
    log_func("[PYGLET] 窗口已关闭。")
