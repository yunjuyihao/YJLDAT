# keymouse_logic.py

import time
import threading
import math

# 导出给 GUI 用的模式映射
KEYMOUSE_MODES = {
    "kb_down":   "键盘按下(右方向键)",
    "kb_up":     "键盘抬起(右方向键)",
    "mouse_left":"鼠标左键按下",
    "mouse_right":"鼠标右键按下",
    "mouse_move":"鼠标移动",
}

LISTENED_KEY = "right"       # 要监听的键
DELETE_KEY   = "backspace"   # 删除上次
DELAY_THRESHOLD_MS = 60.0    # 超阈值丢弃
KM_INTERVAL_MS     = 150     # 固件节流(仅用于提示)

try:
    import keyboard
    import mouse
    from mouse import ButtonEvent, MoveEvent
except Exception:
    keyboard = None
    mouse = None
    ButtonEvent = None
    MoveEvent = None

def _std(values):
    n = len(values)
    if n < 2: return 0.0
    m = sum(values) / n
    v = sum((x - m) ** 2 for x in values) / (n - 1)
    return math.sqrt(v)

def _measure_rtt(serial_manager, trials=600, inter_delay=0.001):
    prev = serial_manager.timeout
    try:
        serial_manager.timeout = 0.05
        serial_manager.reset_buffers()
        samples = []
        for _ in range(trials):
            t0 = time.perf_counter()
            serial_manager.write(b'R')
            b = serial_manager.ser.read(1)
            t1 = time.perf_counter()
            if b:
                samples.append((t1 - t0) * 1_000_000.0)
            time.sleep(inter_delay)
        if not samples:
            return 0.0
        return sum(samples) / len(samples)
    finally:
        serial_manager.timeout = prev

class _Controller:
    def __init__(self, serial_manager, rtt_us, log_func):
        self.sm = serial_manager
        self.rtt_us = rtt_us
        self.log = log_func
        self.busy = threading.Event()
        self.delays = []
        self.lock = threading.Lock()

    def delete_last(self):
        with self.lock:
            if self.delays:
                self.delays.pop()
                self.log("[KEYMOUSE] 已删除上次结果。")

    def trigger_once(self):
        # 忙闲门控：仅当空闲时触发，内部统一发送 'D' 并启动读取线程
        if self.busy.is_set():
            return
        self.busy.set()
        try:
            self.sm.write(b'D')
        except Exception:
            self.busy.clear()
            return
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        prev = self.sm.timeout
        try:
            self.sm.timeout = (60.0 / 1000.0) + 0.3  # 固件 TIMEOUT_MS=60ms
            line = self.sm.readline_str()
        finally:
            self.sm.timeout = prev
            self.busy.clear()

        if not line:
            return
        try:
            us = int(line)
        except ValueError:
            return

        corrected_ms = max(0.0, (us / 1000.0) - (self.rtt_us / 1000.0) / 2.0)
        if corrected_ms > DELAY_THRESHOLD_MS:
            return

        with self.lock:
            self.delays.append(corrected_ms)
            n = len(self.delays)
            mn, mx = min(self.delays), max(self.delays)
            avg, sd = sum(self.delays)/n, _std(self.delays)

        self.log(f"[KEYMOUSE] 第{n}次 延迟: {corrected_ms:.2f} ms | min/avg/max/std={mn:.2f}/{avg:.2f}/{mx:.2f}/{sd:.3f} ms")

    def stats(self):
        with self.lock:
            n = len(self.delays)
            if n == 0:
                return (0.0, 0.0, 0.0, 0.0, 0)
            d = self.delays
            return (min(d), sum(d)/n, max(d), _std(d), n)

def run_keymouse_test(serial_manager, log_func, stop_event, mode_key):
    """
    在后台线程中运行 keymouse 测试（M3 模式）。
    参数:
      - serial_manager: GUI 传入的 SerialManager
      - log_func: GUI 的 log()
      - stop_event: 外部停止事件
      - mode_key: 'kb_down'/'kb_up'/'mouse_left'/'mouse_right'/'mouse_move'
    """
    if keyboard is None or mouse is None:
        log_func("[ERROR] 未安装 keyboard/mouse 库，无法运行 keymouse 测试。请先 pip install keyboard mouse")
        return

    if mode_key not in KEYMOUSE_MODES:
        log_func(f"[ERROR] 未知模式: {mode_key}")
        return

    # 切换固件为 M3
    try:
        serial_manager.write(b'M3')
        time.sleep(0.05)
    except Exception as e:
        log_func(f"[ERROR] 发送 M3 失败: {e}")
        return

    # HELLO 握手
    try:
        serial_manager.reset_buffers()
        serial_manager.ser.write(b"HELLO\n")
        prev = serial_manager.timeout
        serial_manager.timeout = 1.5
        resp = serial_manager.readline_str()
        serial_manager.timeout = prev
        if resp != "READY":
            log_func("[ERROR] 握手失败（未收到 READY）。")
            return
        log_func("[KEYMOUSE] 握手成功：READY")
    except Exception as e:
        log_func(f"[ERROR] 握手错误: {e}")
        return

    # RTT 测量
    rtt_us = 0.0
    try:
        rtt_us = _measure_rtt(serial_manager)
        if rtt_us > 0:
            log_func(f"[RTT] 平均 RTT = {rtt_us:.0f} µs (结果中减半校准)")
        else:
            log_func("[RTT] 无样本，使用 0。")
    except Exception as e:
        log_func(f"[ERROR] RTT 测量失败: {e}")

    ctrl = _Controller(serial_manager, rtt_us, log_func)

    log_func(f"[KEYMOUSE] 当前模式：{KEYMOUSE_MODES[mode_key]}")
    log_func(f"[KEYMOUSE] 参数：间隔 {KM_INTERVAL_MS}ms  阈值 {DELAY_THRESHOLD_MS:.0f}ms  删除上次：{DELETE_KEY}")

    # 钩子回调
    def kb_cb(ev):
        try:
            if ev.event_type == "down":
                # Backspace 删除，所有模式下有效
                if ev.name == DELETE_KEY:
                    ctrl.delete_last()
                    return
                # 键盘按下模式
                if mode_key == "kb_down" and ev.name == LISTENED_KEY:
                    ctrl.trigger_once()
            elif ev.event_type == "up":
                # 键盘抬起模式
                if mode_key == "kb_up" and ev.name == LISTENED_KEY:
                    ctrl.trigger_once()
        except Exception:
            pass

    def ms_cb(ev):
        try:
            if mode_key in ("mouse_left", "mouse_right"):
                if isinstance(ev, ButtonEvent):
                    if ev.event_type in ("down", "double"):
                        if mode_key == "mouse_left" and ev.button == "left":
                            ctrl.trigger_once()
                        elif mode_key == "mouse_right" and ev.button == "right":
                            ctrl.trigger_once()
            elif mode_key == "mouse_move":
                if isinstance(ev, MoveEvent):
                    ctrl.trigger_once()  # 忙闲门控避免风暴
        except Exception:
            pass

    # 安装钩子
    keyboard.hook(kb_cb, suppress=False)
    mouse_hooked = False
    try:
        if mode_key in ("mouse_left", "mouse_right", "mouse_move"):
            mouse.hook(ms_cb)
            mouse_hooked = True
    except Exception:
        # 鼠标钩子安装失败不致命，但会影响鼠标模式
        log_func("[WARN] 鼠标钩子安装失败。")

    log_func("[KEYMOUSE] 钩子已安装。按 ESC 退出窗口不会停止测试，请用 GUI 的“退出当前测试模式”。")

    # 主循环
    try:
        while not stop_event.is_set():
            time.sleep(0.2)
    finally:
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        if mouse_hooked:
            try:
                mouse.unhook_all()
            except Exception:
                pass
        mn, avg, mx, sd, n = ctrl.stats()
        log_func(f"[KEYMOUSE] 总计 {n} 次 | min/avg/max/std={mn:.2f}/{avg:.2f}/{mx:.2f}/{sd:.3f} ms")
        log_func("[KEYMOUSE] 已退出。")
