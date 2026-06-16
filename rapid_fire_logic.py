# -*- coding: utf-8 -*-
import time
import threading
from ctypes import (
    wintypes, cast, Structure, c_ulong, WINFUNCTYPE, windll, c_int, 
    POINTER, byref, c_size_t
)

# --- Windows API 定义 ---
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104 
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012

class KBDLLHOOKSTRUCT(Structure):
    _fields_ = [
        ('vkCode', wintypes.DWORD),
        ('scanCode', wintypes.DWORD),
        ('flags', wintypes.DWORD),
        ('time', wintypes.DWORD),
        ('dwExtraInfo', wintypes.DWORD)
    ]

user32 = windll.user32
kernel32 = windll.kernel32
LRESULT = c_size_t
HOOKProc = WINFUNCTYPE(LRESULT, c_int, wintypes.WPARAM, wintypes.LPARAM)

SetWindowsHookExA = user32.SetWindowsHookExA
SetWindowsHookExA.argtypes = (c_int, HOOKProc, wintypes.HINSTANCE, wintypes.DWORD)
SetWindowsHookExA.restype = wintypes.HHOOK

CallNextHookEx = user32.CallNextHookEx
CallNextHookEx.argtypes = (wintypes.HHOOK, c_int, wintypes.WPARAM, wintypes.LPARAM)
CallNextHookEx.restype = LRESULT

UnhookWindowsHookEx = user32.UnhookWindowsHookEx
UnhookWindowsHookEx.argtypes = (wintypes.HHOOK,)
UnhookWindowsHookEx.restype = wintypes.BOOL

GetModuleHandleW = kernel32.GetModuleHandleW
GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
GetModuleHandleW.restype = wintypes.HMODULE

PostThreadMessageA = user32.PostThreadMessageA
PostThreadMessageA.argtypes = (wintypes.DWORD, c_int, wintypes.WPARAM, wintypes.LPARAM)

GetCurrentThreadId = kernel32.GetCurrentThreadId
GetCurrentThreadId.restype = wintypes.DWORD

# --- 全局变量 ---
_target_key = None
_log_func = None
_dwell_times = [] # 存储触底时间数据
_key_down_timestamp = {} # 记录按下的时刻: {vkCode: time}

def std(data):
    if len(data) < 2: return 0.0
    mean = sum(data)/len(data)
    variance = sum((x-mean)**2 for x in data)/(len(data)-1)
    std_dev = variance**0.5
    return std_dev 

def report_rapid_fire(dt, vk_code):
    if _log_func:
        dt_ms = dt * 1000.0
        _dwell_times.append(dt_ms)
        
        # 统计计算
        min_v = min(_dwell_times)
        max_v = max(_dwell_times)
        avg_v = sum(_dwell_times) / len(_dwell_times)
        std_v = std(_dwell_times)

        # 格式化输出
        # 格式：第N次: [键名] 持续时长 | 统计信息
        msg = (f"第{len(_dwell_times)}次: [{hex(vk_code)}] 触底: {dt_ms:.2f} ms | "
               f"Min: {min_v:.2f}, Avg: {avg_v:.2f}, Max: {max_v:.2f}, Std: {std_v:.3f}")
        
        _log_func(msg)

def hook_proc(nCode, wParam, lParam):
    global _target_key, _key_down_timestamp
    
    if nCode >= 0:
        kb_struct = cast(lParam, POINTER(KBDLLHOOKSTRUCT)).contents
        key_code = kb_struct.vkCode
        current_time = time.perf_counter()

        # --- 绑定逻辑 ---
        if _target_key is None:
            # 忽略抬起事件，只在按下时绑定
            if wParam == WM_KEYDOWN or wParam == WM_SYSKEYDOWN:
                _target_key = key_code
                # 立即记录这次按下的时间，否则第一次点击无法统计
                _key_down_timestamp[key_code] = current_time
                if _log_func: _log_func(f"[BIND] 目标键已绑定: {hex(key_code)}。开始疯狂点击吧！")
        
        # --- 测试逻辑 ---
        elif key_code == _target_key:
            
            # 1. 按下 (Down)
            if wParam == WM_KEYDOWN or wParam == WM_SYSKEYDOWN:
                # 只有当键不在按下状态时才更新时间 (防止长按重复触发)
                # Windows 键盘长按会发送连续的 WM_KEYDOWN，利用 flags 判断 bit 30 (previous key state)
                # flags & 0x40000000 (bit 30): 1 if key was down before the message is sent
                was_down = (kb_struct.flags >> 30) & 1
                if not was_down:
                    _key_down_timestamp[key_code] = current_time

            # 2. 抬起 (Up)
            elif wParam == WM_KEYUP or wParam == WM_SYSKEYUP:
                if key_code in _key_down_timestamp:
                    start_time = _key_down_timestamp[key_code]
                    duration = current_time - start_time
                    
                    # 过滤异常短的杂波（可选，这里暂不过滤）
                    report_rapid_fire(duration, key_code)
                    
                    # 清除记录，准备下一次
                    del _key_down_timestamp[key_code]

    return CallNextHookEx(None, nCode, wParam, lParam)

_hook_c_func = HOOKProc(hook_proc)

def run_rapid_fire_test(serial_manager, log_func, stop_event):
    global _log_func, _target_key, _dwell_times, _key_down_timestamp
    
    # 初始化
    _log_func = log_func
    _target_key = None
    _dwell_times = []
    _key_down_timestamp = {}
    
    log_func("[INFO] 启动速点 (触底时间) 测试")
    log_func("说明: 请按下任意键进行绑定。")
    log_func("      随后快速点击该键，测量每次按下的持续时长。")
    
    try:
        h_hook = SetWindowsHookExA(WH_KEYBOARD_LL, _hook_c_func, GetModuleHandleW(None), 0)
        if not h_hook:
            log_func("[ERROR] 钩子安装失败")
            return
        
        log_func("[SYSTEM] 键盘钩子已就绪。")
        
        thread_id = GetCurrentThreadId()
        def watcher():
            while not stop_event.is_set():
                time.sleep(0.1)
            PostThreadMessageA(thread_id, WM_QUIT, 0, 0)
        
        t_watcher = threading.Thread(target=watcher, daemon=True)
        t_watcher.start()
        
        msg = wintypes.MSG()
        while user32.GetMessageA(byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(byref(msg))
            user32.DispatchMessageA(byref(msg))
            
    except Exception as e:
        log_func(f"[ERROR] 速点测试异常: {e}")
    finally:
        if h_hook:
            UnhookWindowsHookEx(h_hook)
        log_func("[INFO] 速点测试结束。")
