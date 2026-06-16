import tkinter as tk
from tkinter import ttk, messagebox
import math

class LatencyPlotPanel(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.pack(fill=tk.BOTH, expand=True)
        self.canvas_height = 250
        self._create_ui()

    def _create_ui(self):
        calc_frame = ttk.LabelFrame(self, text="全链路延迟拆解计算器", padding=(10, 5))
        calc_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        input_frame = ttk.Frame(calc_frame)
        input_frame.pack(fill=tk.X, pady=5)

        self.calc_entries = {}
        
        headers = ["测试项目", "平均值 (ms)", "标准差 (ms)"]
        for col, text in enumerate(headers):
            ttk.Label(input_frame, text=text, font=("SimHei", 11)).grid(row=0, column=col, padx=5, pady=5)

        rows = [
            ("keymouse", "KeyMouse (键鼠)"),
            ("display", "Display Test (显示器延迟)"),
            ("pyglet", "Pyglet (理想游戏)"),
            ("game", "Game Test (真实游戏)"),
            ("gray", "Gray Test (灰阶)")
        ]

        for i, (key, label) in enumerate(rows, start=1):
            ttk.Label(input_frame, text=label).grid(row=i, column=0, sticky="e", padx=5, pady=2)
            e_avg = ttk.Entry(input_frame, width=10)
            e_avg.grid(row=i, column=1, padx=5, pady=2)
            e_std = ttk.Entry(input_frame, width=10)
            e_std.grid(row=i, column=2, padx=5, pady=2)
            e_avg.insert(0, "0")
            e_std.insert(0, "0")
            self.calc_entries[key] = {"avg": e_avg, "std": e_std}

        btn_calc = ttk.Button(calc_frame, text="计算并绘制统计图", command=self.perform_latency_calculation)
        btn_calc.pack(fill=tk.X, pady=10)

        self.result_label = ttk.Label(calc_frame, text="等待计算...", justify=tk.LEFT, foreground="blue")
        self.result_label.pack(pady=5, anchor="w")
        
        self.plot_canvas = tk.Canvas(calc_frame, bg="white", height=self.canvas_height)
        self.plot_canvas.pack(fill=tk.BOTH, expand=True, pady=5)

    def perform_latency_calculation(self):
        try:
            data = {}
            for key, widgets in self.calc_entries.items():
                avg = float(widgets["avg"].get())
                std = float(widgets["std"].get())
                data[key] = {"avg": avg, "std": std}

            # 计算逻辑
            sys_lat_avg = data["pyglet"]["avg"] - data["keymouse"]["avg"] - data["display"]["avg"]
            sys_lat_std = math.sqrt(data["pyglet"]["std"]**2 + data["keymouse"]["std"]**2 + data["display"]["std"]**2)
            
            game_extra_avg = data["game"]["avg"] - data["pyglet"]["avg"]
            game_extra_std = math.sqrt(data["game"]["std"]**2 + data["pyglet"]["std"]**2)

            display_sys_avg = max(0, sys_lat_avg)
            display_game_avg = max(0, game_extra_avg)

            res_text = (
                f"计算结果:\n"
                f"1. 外设硬件: {data['keymouse']['avg']:.1f}±{data['keymouse']['std']:.1f} ms\n"
                f"2. 系统内部: {sys_lat_avg:.1f}±{sys_lat_std:.1f} ms\n"
                f"3. 游戏额外: {game_extra_avg:.1f}±{game_extra_std:.1f} ms\n"
                f"4. 显示信号: {data['display']['avg']:.1f}±{data['display']['std']:.1f} ms\n"
                f"5. 显示灰阶: {data['gray']['avg']:.1f}±{data['gray']['std']:.1f} ms"
            )
            self.result_label.config(text=res_text)

            # 绘图逻辑
            self.plot_canvas.delete("all") 
            
            components = ['外设', '系统', '游戏', '显示', '灰阶']
            means = [data['keymouse']['avg'], display_sys_avg, display_game_avg, data['display']['avg'], data['gray']['avg']]
            colors = ['#FF9999', '#66B2FF', '#99FF99', '#FFCC99', '#D3D3D3']
            
            w = self.plot_canvas.winfo_width()
            if w < 100: w = 400 
            h = self.canvas_height
            margin_left = 40
            margin_bottom = 30
            margin_top = 20
            
            bar_width = (w - margin_left - 20) / len(components) * 0.6
            max_val = max(means) * 1.2 if max(means) > 0 else 10
            scale_y = (h - margin_bottom - margin_top) / max_val
            
            # 绘制坐标轴
            self.plot_canvas.create_line(margin_left, h - margin_bottom, w, h - margin_bottom, fill="black", width=2) # X轴
            self.plot_canvas.create_line(margin_left, h - margin_bottom, margin_left, margin_top, fill="black", width=2) # Y轴
            
            # 绘制柱状图
            for i, val in enumerate(means):
                x0 = margin_left + 20 + i * ((w - margin_left) / len(components))
                y0 = h - margin_bottom
                y1 = y0 - (val * scale_y)
                self.plot_canvas.create_rectangle(x0, y0, x0 + bar_width, y1, fill=colors[i], outline="black")
                self.plot_canvas.create_text(x0 + bar_width/2, y1 - 10, text=f"{val:.1f}", font=("Arial", 9))
                self.plot_canvas.create_text(x0 + bar_width/2, y0 + 15, text=components[i], font=("Microsoft YaHei", 9))
            
            # 绘制刻度线
            for i in range(4):
                val = max_val * (i / 3)
                y = h - margin_bottom - (val * scale_y)
                self.plot_canvas.create_line(margin_left-5, y, margin_left, y, fill="black")
                self.plot_canvas.create_text(margin_left-10, y, text=f"{int(val)}", anchor="e", font=("Arial", 8))

            self.plot_canvas.create_text(w/2, 10, text="延迟成分占比 (ms)", font=("Microsoft YaHei", 10, "bold"))

        except ValueError:
            messagebox.showerror("输入错误", "请输入有效数字")
        except Exception as e:
            messagebox.showerror("计算错误", str(e))
