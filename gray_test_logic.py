import pyglet
import pyglet.gl as gl
from pyglet.window import FPSDisplay
import time
import ctypes

# 0-255 分为 8 份
GRAY_LEVELS = [0, 36, 73, 109, 146, 182, 219, 255]

def run_gray_test(serial_manager, log_func):
    """
    运行灰阶响应时间测试 (M5模式)
    必须在主线程运行
    """
    # --- 1. 初始配置 ---
    try:
        serial_manager.write(b'M5')
        time.sleep(0.2) # 给点时间切换模式
        pyglet.options['vsync'] = False
    except Exception as e:
        log_func(f"[ERROR] 串口通信失败: {e}")
        return

    # --- 2. 状态变量 ---
    FULLSCREEN_STABILIZE = 5.0
    
    # 状态机状态
    # 0: 等待开始 (按空格)
    # 1: 全屏稳定中
    # 2: 校准中 (0-7)
    # 3: 准备下一个测试组合
    # 4: 等待测试结果
    # 5: 完成
    state = {
        "status": 0,
        "current_idx": 0,      # 用于校准阶段 (0-7)
        "combo_list": [],      # 待测试的组合列表 [(start_idx, end_idx), ...]
        "combo_idx": 0,        # 当前测试到的组合索引
        "results": {},         # 结果字典 {(from, to): latency_us}
        "wait_start_time": 0,  # 用于超时的计时器
        "current_gray": 0      # 当前屏幕显示的灰阶值 (0-255)
    }

    # 生成 56 种组合 (排除自身到自身)
    for i in range(8):
        for j in range(8):
            if i != j:
                state["combo_list"].append((i, j))

    # --- 3. Pyglet 窗口设置 ---
    try:
        config = gl.Config(double_buffer=True, vsync=False)
        window = pyglet.window.Window(600, 400, caption="Gray-to-Gray Response Test", config=config, resizable=False)
    except Exception as e:
        log_func(f"[PYGLET ERROR] 创建窗口失败: {e}")
        return

    # UI 标签
    font_style = dict(font_name='SimHei', font_size=16, color=(0, 255, 0, 255)) # 绿色黑体
    
    label_center = pyglet.text.Label('按空格键开始灰阶测试 (M5)', 
                              x=window.width // 2, y=window.height // 2, 
                              anchor_x='center', anchor_y='center', **font_style)
    
    label_status = pyglet.text.Label('', x=10, y=10, **font_style)

    fps_display = FPSDisplay(window=window)

    # --- 4. 核心逻辑函数 ---
    # --- 新增辅助函数：获取 Windows 当前刷新率 ---
    def get_current_windows_refresh_rate():
        try:
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

    def set_window_color(gray_val):
        # 归一化到 0.0-1.0
        c = gray_val / 255.0
        gl.glClearColor(c, c, c, 1.0)
        state["current_gray"] = gray_val
    
    def finish_test():
        state["status"] = 5
        window.close()
        log_func("\n" + "="*30)
        log_func("   灰阶响应测试报告 (GtG) (VESA 10%-90%)，请注意0-36和36-0的数据不具有参考价值")
        log_func("="*30)
        
        # 打印矩阵头
        header = "From\\To\t" + "\t".join([f"{v:3d}" for v in GRAY_LEVELS])
        log_func(header)
        
        total_sum = 0
        total_count = 0
        
        # 打印每一行
        for start_idx in range(8):
            row_str = f"{GRAY_LEVELS[start_idx]:3d}\t"
            for end_idx in range(8):
                if start_idx == end_idx:
                    row_str += " - \t"
                else:
                    val = state["results"].get((start_idx, end_idx))
                    if val is None:
                        row_str += "ERR\t"
                    else:
                        ms = val / 1000.0
                        row_str += f"{ms:.1f}\t"
                        total_sum += val
                        total_count += 1
            log_func(row_str)
            
        if total_count > 0:
            avg = (total_sum / total_count) / 1000.0
            log_func("-" * 50)
            log_func(f"平均响应时间: {avg:.2f} ms")
        else:
            log_func("[ERROR] 无有效数据")

    def error_handler(err_type):
        if err_type == "ERR_BRIGHT":
            log_func("[CRITICAL] 传感器过曝 (太亮)！测试终止。")
        elif err_type == "ERR_DARK":
            log_func("[CRITICAL] 传感器截止 (太暗)！测试终止。")
        else:
            log_func(f"[ERROR] 未知错误: {err_type}")
        window.close()

    # --- 调度逻辑 ---

    def step_measurement(dt):
        # 状态 4: 等待单片机返回结果
        if state["status"] == 4:
            if serial_manager.ser.in_waiting > 0:
                line = serial_manager.readline_str()
                
                # 错误检查
                if line.startswith("ERR"):
                    error_handler(line)
                    pyglet.clock.unschedule(step_measurement)
                    return

                if line.isdigit():
                    us = int(line)
                    # 获取当前正在测的组合
                    s_idx, e_idx = state["combo_list"][state["combo_idx"]]
                    
                    if us == 0:
                        log_func(f"[TIMEOUT] {GRAY_LEVELS[s_idx]}->{GRAY_LEVELS[e_idx]} 超时")
                        state["results"][(s_idx, e_idx)] = None
                    else:
                        state["results"][(s_idx, e_idx)] = us
                        # 实时显示进度
                        if state["combo_idx"] % 5 == 0:
                            log_func(f"[PROG] 已测 {state['combo_idx']+1}/56: {GRAY_LEVELS[s_idx]}->{GRAY_LEVELS[e_idx]} = {us}us")

                    # 准备下一个
                    state["combo_idx"] += 1
                    if state["combo_idx"] >= len(state["combo_list"]):
                        finish_test()
                        pyglet.clock.unschedule(step_measurement)
                    else:
                        # 进入状态 3: 准备下一组
                        state["status"] = 3
                        # 这里的延时50ms很重要：需要先切回 Start 颜色，并等待稳定
                        pyglet.clock.schedule_once(prepare_next_combo, 0.05)
            
            # 超时保护 (上位机端的保护，防止死锁)
            elif time.time() - state["wait_start_time"] > 2.0:
                log_func("[ERROR] 串口响应超时。")
                error_handler("TIMEOUT")
                pyglet.clock.unschedule(step_measurement)

    def trigger_transition(dt):
        # 实际触发颜色跳变
        s_idx, e_idx = state["combo_list"][state["combo_idx"]]
        
        # 1. 发送测试指令 Txy
        cmd = f"T{s_idx}{e_idx}".encode()
        serial_manager.write(cmd)
        time.sleep(0.01)
        
        # 2. 立即翻转颜色 (Pyglet 会在下一个 draw call 生效，但逻辑上这里已经改变)
        set_window_color(GRAY_LEVELS[e_idx])
        
        # 3. 进入等待结果状态
        state["status"] = 4
        state["wait_start_time"] = time.time()

    def prepare_next_combo(dt):
        # 显示 Start 颜色
        s_idx, _ = state["combo_list"][state["combo_idx"]]
        set_window_color(GRAY_LEVELS[s_idx])
        
        # 给屏幕 200ms 时间从上一个颜色稳定到 Start 颜色
        pyglet.clock.schedule_once(trigger_transition, 0.2)

    def step_calibration(dt):
        # 读取校准回执
        if serial_manager.ser.in_waiting > 0:
            line = serial_manager.readline_str()
            if line.startswith("CAL_OK"):
                # 校准成功，进入下一个灰阶
                val = line.split(":")[1]
                log_func(f"[CALIB] {GRAY_LEVELS[state['current_idx']]}/255 基准值: {val}")
                
                state["current_idx"] += 1
                if state["current_idx"] >= 8:
                    # 校准完成，开始测试
                    log_func("[INFO] 校准完成，开始 56 组 GtG 测试...")
                    state["status"] = 3 # 准备测试
                    state["combo_idx"] = 0
                    pyglet.clock.unschedule(step_calibration) # 停止校准循环
                    pyglet.clock.schedule_interval(step_measurement, 0.01) # 启动测试循环
                    prepare_next_combo(0) # 启动第一组
                else:
                    # 继续下一个校准
                    send_calibration_cmd(0)
            
            elif line.startswith("ERR"):
                error_handler(line)
                pyglet.clock.unschedule(step_calibration)

    def send_calibration_cmd(dt):
        idx = state["current_idx"]
        gray = GRAY_LEVELS[idx]
        
        # 1. 屏幕变色
        set_window_color(gray)
        label_status.text = f"正在校准灰阶: {gray} ({idx+1}/8)..."
        
        # 2. 延时发送指令 (等待屏幕物理变色稳定 + 消除全屏切换可能的闪烁)
        # 在 start_calibration 中首次调用时已经有延时，这里主要是为了后续循环
        # 但由于 send_calibration_cmd 是被 schedule_once 调用的，所以这里直接发指令即可
        # 真正的稳定等待由固件中的 delay(200) 进一步保证
        cmd = f"C{idx}".encode()
        serial_manager.write(cmd)

    def start_calibration(dt):
        state["status"] = 2
        state["current_idx"] = 0
        log_func("[INFO] 开始灰阶校准 (采集 8 个基准点)...")
        pyglet.clock.schedule_interval(step_calibration, 0.05)
        send_calibration_cmd(0)

    # --- 5. Pyglet 事件 ---

    @window.event
    def on_draw():
        window.clear()
        # 注意：背景色由 glClearColor 控制，这里不需要画矩形
        
        if state["status"] == 0:
            label_center.draw()
        else:
            # 测试过程中显示当前状态，放在左上角
            if state["status"] == 3 or state["status"] == 4:
                s_idx, e_idx = state["combo_list"][state["combo_idx"]]
                label_status.text = f"Testing: {GRAY_LEVELS[s_idx]} -> {GRAY_LEVELS[e_idx]} ({state['combo_idx']+1}/56)"
            label_status.draw()
            fps_display.draw()

    @window.event
    def on_key_press(symbol, modifiers):
        if symbol == pyglet.window.key.SPACE and state["status"] == 0:
            state["status"] = 1
            log_func("[INFO] 准备进入全屏测试...")
            
            # --- [修改开始] 智能匹配全屏模式 ---
            try:
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
                # 我们允许 1Hz 的误差 (例如 59Hz vs 60Hz)
                candidates = []
                for m in modes:
                    if m.width == current_w and m.height == current_h:
                        candidates.append(m)
                
                # 从同分辨率的候选者中，找刷新率最接近的
                if candidates:
                    # 按刷新率差值排序
                    candidates.sort(key=lambda m: abs(m.rate - current_hz))
                    target_mode = candidates[0]
                
                if target_mode:
                    log_func(f"[MODE] 锁定独占模式: {target_mode.width}x{target_mode.height} @ {target_mode.rate}Hz")
                    # 这里的 mode 参数是触发显卡驱动切换“真独占”的关键
                    window.set_fullscreen(True, screen=screen, mode=target_mode)
                else:
                    log_func("[WARN] 未找到完美匹配的模式，使用默认全屏")
                    window.set_fullscreen(True, screen=screen)

            except Exception as e:
                log_func(f"[ERROR] 全屏切换异常: {e}")
                window.set_fullscreen(True)
            # --- [修改结束] ---

            log_func(f"[INFO] 等待 {FULLSCREEN_STABILIZE} 秒预热 (请勿触碰)...")
            pyglet.clock.schedule_once(start_calibration, FULLSCREEN_STABILIZE)
            
        elif symbol == pyglet.window.key.ESCAPE:
            state["status"] = 5
            window.close()


    # --- 6. 启动 ---
    pyglet.app.run(0)
