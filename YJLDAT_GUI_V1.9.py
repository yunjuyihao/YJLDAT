#YJLDAT_GUI
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import serial
import serial.tools.list_ports
import time
import threading
import queue

from plot_panel import LatencyPlotPanel

from game_test_logic import run_game_test
from keymouse_logic import run_keymouse_test, KEYMOUSE_MODES
from impulse_test_logic import run_impulse_test
from display_test_logic import run_display_test 
from pyglet_test_logic import run_pyglet_test
from reaction_test_logic import run_reaction_test 
from gray_test_logic import run_gray_test
from simul_test_logic import run_simul_test
from socd_test_logic import run_socd_test
from rapid_fire_logic import run_rapid_fire_test
from mouse_rate_logic import run_mouse_rate_test


class SerialManager:
    def __init__(self):
        self.ser = None

    def connect(self, port, baudrate=115200, timeout=0.5): 
        try:
            self.ser = serial.Serial(port, baudrate, timeout=timeout)
            time.sleep(1.5)
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            return True, f"成功连接到 {port} @ {baudrate}"
        except serial.SerialException as e:
            self.ser = None
            return False, f"无法打开串口 {port}: {e}"

    def disconnect(self):
        if self.ser and self.ser.is_open:
            try: self.ser.close()
            except Exception: pass
        return True, "串口已断开"
    
    def readline_str(self):
        if self.is_open:
            try: return self.ser.readline().decode(errors='ignore').strip()
            except Exception: return ""
        return ""

    def write(self, data):
        if self.is_open: self.ser.write(data)
    
    def reset_buffers(self):
        if self.is_open:
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            
    @property
    def is_open(self): return self.ser and self.ser.is_open
    
    @property
    def timeout(self): return self.ser.timeout if self.is_open else None
        
    @timeout.setter
    def timeout(self, value):
        if self.is_open: self.ser.timeout = value


class LatencyTesterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("YJLDAT外设延迟测试系统")
        self.root.geometry("1366x768") 
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.is_connected = False
        self.is_testing = False
        self.serial_manager = SerialManager()    
        self.test_thread = None
        self.stop_event = threading.Event()
        self.log_queue = queue.Queue()
        
        # 主界面布局
        self.main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.left_frame = ttk.Frame(self.main_paned)
        self.right_frame = ttk.Frame(self.main_paned)      
        self.main_paned.add(self.left_frame, weight=2) 
        self.main_paned.add(self.right_frame, weight=1)
        
        self._create_widgets_left()
        self.plot_panel = LatencyPlotPanel(self.right_frame)
        
        self.refresh_serial_ports()
        self.root.after(100, self.process_log_queue)

    def _create_widgets_left(self):
        serial_frame = ttk.LabelFrame(self.left_frame, text="串口控制", padding=(10, 5))
        serial_frame.pack(padx=5, pady=5, fill=tk.X)
        serial_frame.columnconfigure(1, weight=1)
        ttk.Label(serial_frame, text="选择串口:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.serial_port_var = tk.StringVar()
        self.port_combobox = ttk.Combobox(serial_frame, textvariable=self.serial_port_var, state="readonly")
        self.port_combobox.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.refresh_button = ttk.Button(serial_frame, text="刷新", command=self.refresh_serial_ports)
        self.refresh_button.grid(row=0, column=2, padx=5, pady=5)
        self.connect_button = ttk.Button(serial_frame, text="连接", command=self.connect_serial)
        self.connect_button.grid(row=0, column=3, padx=5, pady=5)

        test_frame = ttk.LabelFrame(self.left_frame, text="测试模式", padding=(10, 5))
        test_frame.pack(padx=5, pady=5, fill=tk.X)
        
        self.test_buttons = {}
        self.test_modes_threaded = [
            "game_test", "keymouse", 
            "reaction_test", "mouse_rate_test",
            "simul_test", "socd_test", "rapid_fire_test"
        ] 

        row1_config = [
            ("keymouse", "键鼠延迟测试"),
            ("display_test", "显示器延迟测试"),
            ("pyglet_test", "理想游戏全链路延迟"),
            ("game_test", "游戏全链路延迟")
        ]
        
        row2_config = [
            ("reaction_test", "硬件反应速度测试"),
            ("impulse_test", "软件反应速度测试"),
            ("rapid_fire_test", "速点测试"), 
            ("mouse_rate_test", "鼠标回报率测试")
        ]

        row3_config = [
            ("gray_test", "灰阶测试"),
            ("simul_test", "同按测试"),
            ("socd_test", "SOCD测试"),
            ("about_info", "关于")
        ]

        for i, (mode, label) in enumerate(row1_config):
            btn = ttk.Button(test_frame, text=label, command=lambda m=mode: self.start_test(m))
            btn.grid(row=0, column=i, padx=5, pady=5, sticky="ew")
            test_frame.columnconfigure(i, weight=1)
            self.test_buttons[mode] = btn

        for i, (mode, label) in enumerate(row2_config):
            btn = ttk.Button(test_frame, text=label, command=lambda m=mode: self.start_test(m))
            btn.grid(row=1, column=i, padx=5, pady=5, sticky="ew")
            self.test_buttons[mode] = btn

        for i, (mode, label) in enumerate(row3_config):
            btn = ttk.Button(test_frame, text=label, command=lambda m=mode: self.start_test(m))
            btn.grid(row=2, column=i, padx=5, pady=5, sticky="ew")
            self.test_buttons[mode] = btn

        control_frame = ttk.Frame(self.left_frame, padding=(0, 5))
        control_frame.pack(padx=5, pady=0, fill=tk.X)
        
        self.stop_test_button = ttk.Button(control_frame, text="退出当前测试模式", command=self.stop_current_test)
        self.stop_test_button.pack(side=tk.LEFT)
        
        self.clear_log_button = ttk.Button(control_frame, text="清空输出", command=self.clear_log)
        self.clear_log_button.pack(side=tk.RIGHT)

        # 新增提示按钮，pack自动居中于左右按钮之间
        self.tips_button = ttk.Button(control_frame, text="提示", command=self.show_tips)
        self.tips_button.pack(expand=True)
        
        log_frame = ttk.LabelFrame(self.left_frame, text="命令行输出", padding=(10, 5))
        log_frame.pack(padx=5, pady=5, fill=tk.BOTH, expand=True)
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, state="disabled")
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.update_ui_states()
    
    def show_tips(self):
        """显示操作提示信息"""
        tips_text = (
            "光敏二极管连接至GP26\n"
            "铜箔连接至GP16\n"
            "注意：测试键盘时请让本窗口失焦。"
        )
        messagebox.showinfo("测试提示", tips_text)

    def show_about(self):
        """显示关于信息的弹窗"""
        about_win = tk.Toplevel(self.root)
        about_win.title("关于")
        about_win.geometry("400x300")
        about_win.transient(self.root) 
        about_win.grab_set() 
        about_win.resizable(False, False)
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 175
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 100
        about_win.geometry(f"+{x}+{y}")
        content_frame = ttk.Frame(about_win, padding=20)
        content_frame.pack(fill=tk.BOTH, expand=True)
        title_font = ("SimHei", 16, "bold") 
        text_font = ("SimHei", 11)       
        ttk.Label(content_frame, text="YJLDAT V1.9", font=title_font, justify=tk.CENTER).pack(pady=(10, 5))
        ttk.Label(content_frame, text="2026/03/14", font=text_font, justify=tk.CENTER).pack(pady=(0, 15))
        ttk.Separator(content_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)
        ttk.Label(content_frame, text="作者：云居一号", font=text_font, justify=tk.CENTER).pack(pady=5)
        ttk.Label(content_frame, text="国防科技大学系统工程学院", font=text_font, justify=tk.CENTER).pack(pady=5)

        ttk.Button(content_frame, text="确定", command=about_win.destroy).pack(side=tk.BOTTOM, pady=10)

    def log(self, message):
        self.log_queue.put(str(message))

    def process_log_queue(self):
        try:
            while not self.log_queue.empty():
                message = self.log_queue.get_nowait()
                self.log_text.config(state="normal")
                self.log_text.insert(tk.END, message + "\n")
                self.log_text.see(tk.END)
                self.log_text.config(state="disabled")
        finally:
            self.root.after(100, self.process_log_queue)

    def update_ui_states(self):
        def _update():
            # 判断当前是否在运行支持多线程中途停止的测试
            is_threaded_test = getattr(self, "is_testing", False) and getattr(self, "current_test_mode", "") in self.test_modes_threaded
            
            self.port_combobox['state'] = 'readonly' if not self.is_connected else 'disabled'
            self.refresh_button['state'] = 'normal' if not self.is_connected else 'disabled'
            self.connect_button['text'] = '断开' if self.is_connected else '连接'
            self.connect_button['state'] = 'normal' if not self.is_testing else 'disabled'

            # 定义不依赖硬件(RP2040)的独立测试模式
            independent_modes = {
                "impulse_test",     # 软件反应速度测试
                "rapid_fire_test",  # 速点测试
                "mouse_rate_test",  # 鼠标回报率测试
                "simul_test",       # 同按测试
                "socd_test",        # SOCD测试
                "about_info"        # 关于
            }

            for mode, btn in self.test_buttons.items():
                if self.is_testing:
                    # 如果正在测试中，屏蔽所有测试按钮
                    btn['state'] = 'disabled'
                elif mode in independent_modes:
                    # 如果是独立模块，只要没在测试中，随时可用
                    btn['state'] = 'normal'
                else:
                    # 硬件依赖模块，必须连接串口才能用
                    btn['state'] = 'normal' if self.is_connected else 'disabled'
            
            self.stop_test_button['state'] = 'normal' if is_threaded_test else 'disabled'
            
        self.root.after(0, _update)


    def ask_keymouse_mode(self):
        win = tk.Toplevel(self.root)
        win.title("选择 KeyMouse 测试模式")
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)

        var = tk.StringVar(value="kb_down")
        ttk.Label(win, text="请选择测试模式：").pack(padx=12, pady=(12, 6), anchor="w")
        for k in ["kb_down", "kb_up", "mouse_left", "mouse_right", "mouse_move"]:
            ttk.Radiobutton(win, text=KEYMOUSE_MODES[k], variable=var, value=k).pack(anchor="w", padx=18, pady=2)

        result = {"value": None}
        def on_ok():
            result["value"] = var.get()
            win.destroy()
        def on_cancel():
            result["value"] = None
            win.destroy()
        btn_frame = ttk.Frame(win)
        btn_frame.pack(fill="x", padx=12, pady=(8, 12))
        ttk.Button(btn_frame, text="确定", command=on_ok).pack(side="right", padx=6)
        ttk.Button(btn_frame, text="取消", command=on_cancel).pack(side="right")

        win.protocol("WM_DELETE_WINDOW", on_cancel)
        win.wait_window()
        return result["value"]

    def start_test(self, mode):
        if mode == "keymouse":
            sel = self.ask_keymouse_mode()
            if not sel:
                self.log("[KEYMOUSE] 已取消选择。")
                return
            self.keymouse_mode_key = sel

        self.is_testing = True
        self.current_test_mode = mode
        self.update_ui_states()
        self.log(f"\n{'='*15} [ 开始测试: {mode} ] {'='*15}")
        
        if mode in self.test_modes_threaded:
            self.stop_event.clear()
            self.test_thread = threading.Thread(target=self._test_runner_threaded, args=(mode,))
            self.test_thread.daemon = True
            self.test_thread.start()
        else:
            # 主线程运行 (Pyglet 需要在主线程)
            try:
                if mode == "display_test": run_display_test(self.serial_manager, self.log)
                elif mode == "pyglet_test": run_pyglet_test(self.serial_manager, self.log)
                elif mode == "impulse_test": run_impulse_test(self.log)
                elif mode == "about_info":
                    self.show_about()
                    return
                
                elif mode == "gray_test":
                    run_gray_test(self.serial_manager, self.log)                   

            except Exception as e:
                self.log(f"[ERROR] 测试 '{mode}' 过程中发生严重错误: {e}")
                import traceback
                self.log(traceback.format_exc())
            finally:
                self.is_testing = False
                self.update_ui_states()
                self.log(f"{'='*15} [ 测试结束: {mode} ] {'='*15}\n")

    def stop_current_test(self):
        if self.is_testing and self.current_test_mode in self.test_modes_threaded:
            self.log("[CONTROL] 正在发送停止信号...")
            self.stop_event.set()
            self.stop_test_button['state'] = 'disabled'
        else:
            self.log("[INFO] 当前测试不支持中途停止 (请按 ESC 退出窗口)。")
            
    def _test_runner_threaded(self, mode):
        # 子线程运行
        try:
            if mode == "game_test":
                self.serial_manager.write(b'M2')
                run_game_test(self.serial_manager, self.log, self.stop_event)
            elif mode == "keymouse":
                self.serial_manager.write(b'M3')
                time.sleep(0.05)
                sel = getattr(self, "keymouse_mode_key", "kb_down")
                self.log(f"[KEYMOUSE] 选择模式：{KEYMOUSE_MODES.get(sel, sel)}")
                run_keymouse_test(self.serial_manager, self.log, self.stop_event, sel)
            elif mode == "reaction_test":
                self.serial_manager.write(b'M4')
                time.sleep(0.1)
                run_reaction_test(self.serial_manager, self.log, self.stop_event)
            elif mode == "mouse_rate_test":
                run_mouse_rate_test(self.log, self.stop_event)
            elif mode == "simul_test":
                run_simul_test(self.serial_manager, self.log, self.stop_event)
            elif mode == "socd_test":
                run_socd_test(self.serial_manager, self.log, self.stop_event)
            elif mode == "rapid_fire_test":
                run_rapid_fire_test(self.serial_manager, self.log, self.stop_event)

        except Exception as e:
            self.log(f"[ERROR] 线程测试 '{mode}' 发生错误: {e}")
        finally:
            self.is_testing = False
            self.update_ui_states()
            self.log(f"{'='*15} [ 测试结束: {mode} ] {'='*15}\n")

    def on_closing(self):
        self.log("[App] 正在关闭...")
        if self.is_testing and self.test_thread and self.test_thread.is_alive():
            self.stop_event.set()
            self.test_thread.join(1)
        if self.is_connected:
            self.serial_manager.disconnect()
        self.root.destroy()

    def refresh_serial_ports(self):
        self.log("[INFO] 正在扫描可用串口...")
        ports = serial.tools.list_ports.comports()
        port_list = [port.device for port in ports]
        self.port_combobox['values'] = port_list
        if port_list: self.serial_port_var.set(port_list[0])
        else: self.serial_port_var.set("")
        self.log(f"[INFO] 扫描完成: {len(port_list)} 个串口。")

    def connect_serial(self):
        if self.is_connected:
            _, message = self.serial_manager.disconnect()
            self.log(f"[SERIAL] {message}")
            self.is_connected = False
        else:
            port = self.serial_port_var.get()
            if not port:
                messagebox.showwarning("连接错误", "请先选择一个串口！")
                return
            self.log(f"[SERIAL] 正在尝试连接 {port}...")
            self.connect_button['state'] = 'disabled'
            self.root.update_idletasks()
            success, message = self.serial_manager.connect(port)
            self.log(f"[SERIAL] {message}")
            if success: self.is_connected = True
            else: messagebox.showerror("连接失败", message)
        self.update_ui_states()

    def clear_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state="disabled")

if __name__ == "__main__":
    root = tk.Tk()
    app = LatencyTesterApp(root)
    root.mainloop()
