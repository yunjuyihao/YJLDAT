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
_key1 = None
_key2 = None
_log_func = None
_deltatimes = [] # 用于统计历史数据

_last_down_event = {'key': None, 'time': 0}
_last_up_event = {'key': None, 'time': 0}

_SOCD_THRESHOLD = 0.2 

def std(data):
    if len(data) < 2: return 0.0
    mean = sum(data)/len(data)
    variance = sum((x-mean)**2 for x in data)/(len(data)-1)
    std_dev = variance**0.5
    return std_dev 

def report_socd(dt, key_down, key_up):
    if _log_func:
        dt_ms = dt * 1000.0
        _deltatimes.append(dt_ms)
        
        # 统计计算
        min_v = min(_deltatimes)
        max_v = max(_deltatimes)
        avg_v = sum(_deltatimes) / len(_deltatimes)
        std_v = std(_deltatimes)

        # 判断类型
        tag = ""
        if dt > 0:
            tag = "[GAP 间隙]" 
            desc = f"{hex(key_up)}抬起 -> {hex(key_down)}按下"
        elif dt < 0:
            tag = "[OVR 重叠]" 
            desc = f"{hex(key_down)}按下 -> {hex(key_up)}抬起"
        else:
            tag = "[PER 完美]"
            desc = "Perfect Switch"
            
        # 组合输出字符串
        # 格式参考：第N次: [类型] 差值 | 详情 | 统计信息
        msg = (f"第{len(_deltatimes)}次: {tag} {dt_ms:+.2f} ms | {desc} | "
               f"Min: {min_v:+.2f}, Avg: {avg_v:+.2f}, Max: {max_v:+.2f}, Std: {std_v:.3f}")
        
        _log_func(msg)

def hook_proc(nCode, wParam, lParam):
    global _key1, _key2, _last_down_event, _last_up_event
    
    if nCode >= 0:
        kb_struct = cast(lParam, POINTER(KBDLLHOOKSTRUCT)).contents
        key_code = kb_struct.vkCode
        current_time = time.perf_counter()

        if _key1 is None:
            _key1 = key_code
            if _log_func: _log_func(f"[BIND] 键1已绑定: {hex(key_code)}")
        elif _key2 is None and key_code != _key1:
            _key2 = key_code
            if _log_func: _log_func(f"[BIND] 键2已绑定: {hex(key_code)}。开始测试...")
        
        elif key_code == _key1 or key_code == _key2:
            # 1. Down
            if wParam == WM_KEYDOWN or wParam == WM_SYSKEYDOWN:
                _last_down_event['key'] = key_code
                _last_down_event['time'] = current_time
                
                other_key = _key2 if key_code == _key1 else _key1
                if (_last_up_event['key'] == other_key and 
                    current_time - _last_up_event['time'] < _SOCD_THRESHOLD):
                    
                    diff = current_time - _last_up_event['time']
                    report_socd(diff, key_code, other_key)

            # 2. Up
            elif wParam == WM_KEYUP or wParam == WM_SYSKEYUP:
                _last_up_event['key'] = key_code
                _last_up_event['time'] = current_time
                
                other_key = _key2 if key_code == _key1 else _key1
                if (_last_down_event['key'] == other_key and 
                    current_time - _last_down_event['time'] < _SOCD_THRESHOLD):
                    
                    diff = _last_down_event['time'] - current_time
                    report_socd(diff, other_key, key_code)

    return CallNextHookEx(None, nCode, wParam, lParam)

_hook_c_func = HOOKProc(hook_proc)

def run_socd_test(serial_manager, log_func, stop_event):
    global _log_func, _key1, _key2, _last_down_event, _last_up_event, _deltatimes
    
    # 初始化
    _log_func = log_func
    _key1 = None
    _key2 = None
    _deltatimes = []
    _last_down_event = {'key': None, 'time': 0}
    _last_up_event = {'key': None, 'time': 0}
    
    log_func("[INFO] 启动 SOCD (切指) 测试")
    log_func("说明: 绑定两键后快速交替按下。")
    log_func("      正值(+): 有间隙(Gap)；负值(-): 有重叠(Overlap)。")
    
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
        log_func(f"[ERROR] SOCD 测试异常: {e}")
    finally:
        if h_hook:
            UnhookWindowsHookEx(h_hook)
        log_func("[INFO] SOCD 测试结束。")
