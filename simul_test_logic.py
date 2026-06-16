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
WM_QUIT = 0x0012

class KBDLLHOOKSTRUCT(Structure):
    _fields_ = [
        ('vkCode', wintypes.DWORD),
        ('scanCode', wintypes.DWORD),
        ('flags', wintypes.DWORD),
        ('time', wintypes.DWORD),
        ('dwExtraInfo', wintypes.DWORD)
    ]

# 加载 DLL
user32 = windll.user32
kernel32 = windll.kernel32
LRESULT = c_size_t

# 定义回调函数原型
HOOKProc = WINFUNCTYPE(LRESULT, c_int, wintypes.WPARAM, wintypes.LPARAM)

# API 函数签名
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

# --- 全局变量 (用于 Hook 回调) ---
_key1 = None
_key2 = None
_key_time = {}
_deltatimes = []
_log_func = None  # 用于在 Hook 中打印
_key_time_maxlen = 2

def std(data):
    if len(data) < 2: return 0.0
    mean = sum(data)/len(data)
    variance = sum((x-mean)**2 for x in data)/(len(data)-1) # 修正为样本方差
    std_dev = variance**0.5
    return std_dev 

def showdeltatime(dt, event1, event2):
    if _log_func:
        dt_ms = dt * 1000.0
        _deltatimes.append(dt_ms)
        
        min_v = min(_deltatimes)
        max_v = max(_deltatimes)
        avg_v = sum(_deltatimes) / len(_deltatimes)
        std_v = std(_deltatimes)
        
        msg = (f"第{len(_deltatimes)}次: [{event1}] 比 [{event2}] 早 {dt_ms:.2f} ms | "
               f"Min: {min_v:.2f}, Avg: {avg_v:.2f}, Max: {max_v:.2f}, Std: {std_v:.3f}")
        _log_func(msg)

def hook_proc(nCode, wParam, lParam):
    global _key1, _key2, _key_time
    
    if nCode >= 0:
        if wParam == WM_KEYDOWN:
            kb_struct = cast(lParam, POINTER(KBDLLHOOKSTRUCT)).contents
            key_code = kb_struct.vkCode
            
            # 逻辑: 如果不在当前按下的列表中，且列表未满，且 (是目标键 或 目标键还没定)
            if (key_code not in _key_time) and (len(_key_time) < _key_time_maxlen):
                if (_key1 is None or _key2 is None) or (key_code in [_key1, _key2]):
                    
                    # 记录时间
                    _key_time[key_code] = time.perf_counter()
                    
                    # 如果两个键都按下了
                    if len(_key_time) == _key_time_maxlen:
                        # 如果是第一次，绑定这两个键
                        if _key1 is None and _key2 is None:
                            keys = list(_key_time.keys())
                            _key1, _key2 = keys[0], keys[1]
                            if _log_func:
                                _log_func(f"[BIND] 已绑定按键: {hex(_key1)} 和 {hex(_key2)}")
                        
                        # 计算时间差
                        try:
                            t1 = _key_time[_key1]
                            t2 = _key_time[_key2]
                            diff = t1 - t2
                            # 无论正负都传进去，showdeltatime 只是打印相对值
                            # 但为了“早按下”，通常我们取绝对值或者特定的逻辑，原代码是 t1-t2
                            showdeltatime(abs(diff), _key1 if diff < 0 else _key2, _key2 if diff < 0 else _key1)
                        except KeyError:
                            pass # 容错

        elif wParam == WM_KEYUP:
            kb_struct = cast(lParam, POINTER(KBDLLHOOKSTRUCT)).contents
            key_code = kb_struct.vkCode
            if key_code in _key_time:
                del _key_time[key_code]

    return CallNextHookEx(None, nCode, wParam, lParam)

# 必须保持引用，防止被垃圾回收
_hook_c_func = HOOKProc(hook_proc)

def run_simul_test(serial_manager, log_func, stop_event):
    """
    同按测试主函数
    注意：不需要 serial_manager，这是纯软件测试
    """
    global _log_func, _key1, _key2, _key_time, _deltatimes
    
    # --- 初始化全局状态 ---
    _log_func = log_func
    _key1 = None
    _key2 = None
    _key_time = {}
    _deltatimes = []
    
    log_func("[INFO] 启动同按测试 (Simultaneous Press Test)")
    log_func("说明: 请同时按下两个你想要测试的键 (例如 Z 和 X)。")
    log_func("      系统会自动绑定前两个按下的键进行比较。")
    
    # --- 安装钩子 ---
    try:
        h_hook = SetWindowsHookExA(
            WH_KEYBOARD_LL, 
            _hook_c_func, 
            GetModuleHandleW(None), 
            0
        )
        if not h_hook:
            log_func("[ERROR] 无法安装键盘钩子！")
            return
        
        log_func("[SYSTEM] 键盘钩子已安装。")
        
        # --- 消息循环与退出控制 ---
        thread_id = GetCurrentThreadId()
        
        # 启动一个监视线程，用于检测 stop_event 并发送 WM_QUIT
        def watcher():
            while not stop_event.is_set():
                time.sleep(0.1)
            # 发送退出消息给当前线程的消息循环
            PostThreadMessageA(thread_id, WM_QUIT, 0, 0)
        
        t_watcher = threading.Thread(target=watcher, daemon=True)
        t_watcher.start()
        
        # 进入消息循环 (阻塞，直到收到 WM_QUIT)
        msg = wintypes.MSG()
        while user32.GetMessageA(byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(byref(msg))
            user32.DispatchMessageA(byref(msg))
            
    except Exception as e:
        log_func(f"[ERROR] 同按测试发生异常: {e}")
    finally:
        # --- 卸载钩子 ---
        if h_hook:
            UnhookWindowsHookEx(h_hook)
            log_func("[SYSTEM] 键盘钩子已卸载。")
        
        log_func("[INFO] 同按测试已停止。")

