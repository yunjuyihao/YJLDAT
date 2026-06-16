# impulse_test_logic.py
import pyglet
import pyglet.gl as gl
from pyglet.window import key, mouse
from pyglet.window import FPSDisplay
import pyglet.shapes
import random
import time
import math

def run_impulse_test(log_func):
    """
    运行软件反应速度测试 (Impulse Speed Test)
    必须在主线程调用
    """
    pyglet.options['vsync'] = False 
    # --- 配置参数 ---
    WAIT_MIN_S = 3.0
    WAIT_MAX_S = 5.0
    TIMEOUT_S  = 1.0
    BOX_SIZE   = 300  # 中心方块的大小 (像素)
    
    # --- 状态机定义 ---
    STATE_IDLE       = 0  
    STATE_WAIT_RED   = 1  # 红色，等待随机时间
    STATE_GO_GREEN   = 2  # 绿色，等待用户输入
    
    # --- 共享状态字典 ---
    ctx = {
        "state": STATE_IDLE,
        "reaction_times": [],     # 存储单位: ms
        "green_start_time": 0.0,  # 变绿的时间戳
        "should_exit": False,
        "fullscreen_mode": None
    }

    # --- 窗口初始化 ---
    try:
        config = gl.Config(double_buffer=True, vsync=False)
        window = pyglet.window.Window(800, 600, caption="Impulse Speed Test", config=config, resizable=False)
    except Exception as e:
        log_func(f"[ERROR] 创建 Pyglet 窗口失败: {e}")
        return

    # FPS 显示 (左下角)
    fps_display = FPSDisplay(window=window)

    # 1. 说明文字
    instructions = (
        "软件反应速度测试 (Impulse Test)\n\n"
        "1. 按 [空格键] 进入全屏并开始。\n"
        "2. 屏幕中间方块变 [红色] 时请保持专注，不要操作。\n"
        "3. 方块变 [绿色] 时，立即按下 [鼠标左键] 或 [键盘右方向键]。\n"
        "4. 按 [ESC] 退出测试并查看统计。\n\n"
        "注意：抢跑(红色时操作)或超时(>1秒)将被记录并重置当前轮次。"
    )
    
    label_intro = pyglet.text.Label(
        instructions,
        font_name='Microsoft YaHei',
        font_size=18,
        x=window.width // 2,
        y=window.height // 2,
        width=window.width - 100,
        anchor_x='center',
        anchor_y='center',
        multiline=True,
        color=(255, 255, 255, 255) # 白色文字
    )

    # 2. 状态提示文字 (在测试进行中显示在方块上方)
    label_status = pyglet.text.Label(
        "",
        font_name='Microsoft YaHei',
        font_size=14,
        x=window.width // 2,
        y=window.height // 2 + BOX_SIZE // 2 + 30,
        anchor_x='center',
        anchor_y='center',
        color=(200, 200, 200, 255)
    )

    # 3. 中心方块 (使用 pyglet.shapes)
    # 初始化时不重要，因为我们在 on_draw 里会动态更新位置
    center_rect = pyglet.shapes.Rectangle(0, 0, BOX_SIZE, BOX_SIZE, color=(50, 50, 50))
    center_rect.anchor_x = BOX_SIZE // 2 # 设置锚点为中心
    center_rect.anchor_y = BOX_SIZE // 2

    # --- 辅助函数 ---
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

    def print_stats():
        values = ctx["reaction_times"]
        n = len(values)
        log_func("\n" + "="*20 + " 测试结果 " + "="*20)
        if n < 1:
            log_func("未收集到有效数据。")
        else:
            minimum = min(values)
            maximum = max(values)
            avg = sum(values) / n
            if n > 1:
                variance = sum((x - avg) ** 2 for x in values) / (n - 1)
                stddev = math.sqrt(variance)
            else:
                stddev = 0.0
            
            log_func(f"成功次数: {n}")
            log_func(f"最快反应: {minimum:.2f} ms")
            log_func(f"最慢反应: {maximum:.2f} ms")
            log_func(f"平均速度: {avg:.2f} ms")
            log_func(f"稳定性(SD): {stddev:.2f} ms")
        log_func("="*50)

    def set_fullscreen():
        # --- [修改开始] 智能匹配全屏模式 ---
        try:
            log_func("[INFO] 正在分析显示器模式...")
            display = pyglet.display.get_display()
            screen = display.get_default_screen()
            modes = screen.get_modes()
            
            # 1. 获取当前桌面信息
            current_w = screen.width
            current_h = screen.height
            current_hz = get_current_windows_refresh_rate() # 使用新增的辅助函数
            log_func(f"[SYS] 检测到当前桌面: {current_w}x{current_h} @ {current_hz}Hz")

            target_mode = None
            
            # 2. 筛选匹配分辨率的模式
            candidates = []
            for m in modes:
                if m.width == current_w and m.height == current_h:
                    candidates.append(m)
            
            # 3. 筛选最接近的刷新率
            if candidates:
                candidates.sort(key=lambda m: abs(m.rate - current_hz))
                target_mode = candidates[0]
            
            if target_mode:
                log_func(f"[MODE] 锁定独占模式: {target_mode.width}x{target_mode.height} @ {target_mode.rate}Hz")
                window.set_fullscreen(True, screen=screen, mode=target_mode)
            else:
                log_func("[WARN] 未找到完美匹配的模式，使用默认全屏。")
                window.set_fullscreen(True, screen=screen)

            # 全屏后更新文字和方块位置
            label_intro.x = window.width // 2
            label_intro.y = window.height // 2
            label_status.x = window.width // 2
            label_status.y = window.height // 2 + BOX_SIZE // 2 + 30 
            return True
        except Exception as e:
            log_func(f"[ERROR] 全屏切换失败: {e}")
            return False
        # --- [修改结束] ---


    def on_timeout(dt):
        """1秒超时回调"""
        if ctx["state"] == STATE_GO_GREEN:
            log_func("[FAIL] 超时 (>1000ms)！")
            label_status.text = "超时! (>1000ms)"
            start_next_round_red()

    def turn_green(dt):
        """时间到，变绿，开始计时"""
        ctx["state"] = STATE_GO_GREEN
        
        # 启动1秒超时检测
        pyglet.clock.schedule_once(on_timeout, TIMEOUT_S)
        
        # 强制刷新一帧以确保颜色立即变化
        window.dispatch_event('on_draw')
        window.flip()
        ctx["green_start_time"] = time.perf_counter()

    def start_next_round_red(dt=0):
        """开始新的一轮：变红，随机等待"""
        pyglet.clock.unschedule(turn_green)
        pyglet.clock.unschedule(on_timeout)
        
        ctx["state"] = STATE_WAIT_RED
        wait_time = random.uniform(WAIT_MIN_S, WAIT_MAX_S)
        
        # 安排 wait_time 秒后变绿
        pyglet.clock.schedule_once(turn_green, wait_time)
        
        # 如果不是超时提示，清空状态文字
        if "超时" not in label_status.text and "抢跑" not in label_status.text and "ms" not in label_status.text:
             label_status.text = "等待变绿..."

    # --- 事件处理 ---

    @window.event
    def on_draw():
        window.clear()
        
        # 全局背景始终为深灰色/黑色
        gl.glClearColor(0.05, 0.05, 0.05, 1) 

        if ctx["state"] == STATE_IDLE:
            label_intro.draw()
            
        else:
            # 更新方块位置 (防止窗口大小变化导致偏移)
            center_rect.x = window.width // 2
            center_rect.y = window.height // 2
            
            # 根据状态设置方块颜色
            if ctx["state"] == STATE_WAIT_RED:
                center_rect.color = (200, 0, 0) # 红色
                if label_status.text == "": label_status.text = "Wait..."
            elif ctx["state"] == STATE_GO_GREEN:
                center_rect.color = (0, 200, 0) # 绿色
                label_status.text = "GO!"
            
            center_rect.draw()
            label_status.draw()
            
        # 始终显示 FPS
        fps_display.draw()

    @window.event
    def on_key_press(symbol, modifiers):
        if symbol == key.ESCAPE:
            ctx["should_exit"] = True
            return pyglet.event.EVENT_HANDLED
        
        if ctx["state"] == STATE_IDLE:
            if symbol == key.SPACE:
                if set_fullscreen():
                    pyglet.clock.schedule_once(start_next_round_red, 1.0)
                else:
                    start_next_round_red()
            return pyglet.event.EVENT_HANDLED

        if symbol == key.RIGHT:
            handle_input_trigger()
            return pyglet.event.EVENT_HANDLED

    @window.event
    def on_mouse_press(x, y, button, modifiers):
        if ctx["state"] != STATE_IDLE and button == mouse.LEFT:
            handle_input_trigger()
            return pyglet.event.EVENT_HANDLED
    def handle_input_trigger():
        """处理用户触发逻辑"""
        if ctx["state"] == STATE_WAIT_RED:
            # 抢跑
            log_func("[WARN] 抢跑！(Early Start)")
            label_status.text = "抢跑! (Early)"
            pyglet.clock.unschedule(turn_green)
            start_next_round_red()
            
        elif ctx["state"] == STATE_GO_GREEN:
            # 成功
            now = time.perf_counter()
            delta_ms = (now - ctx["green_start_time"]) * 1000.0
            
            pyglet.clock.unschedule(on_timeout)
            
            ctx["reaction_times"].append(delta_ms)
            msg = f"{delta_ms:.2f} ms"
            log_func(f"[RESULT] 反应时间: {msg}")
            label_status.text = msg # 在屏幕上显示这次成绩
            
            start_next_round_red()

    # --- 主循环 ---
    log_func("[IMPULSE] 窗口已启动，等待用户操作...")
    
    while not ctx["should_exit"] and not window.has_exit:
        pyglet.clock.tick()
        window.dispatch_events()
        window.dispatch_event('on_draw')
        window.flip()

    # --- 清理 ---
    pyglet.clock.unschedule(turn_green)
    pyglet.clock.unschedule(on_timeout)
    pyglet.clock.unschedule(start_next_round_red)
    window.close()
    
    print_stats()
    log_func("[IMPULSE] 测试结束，窗口已关闭。")

if __name__ == "__main__":
    def dummy_log(msg): print(msg)
    run_impulse_test(dummy_log)
