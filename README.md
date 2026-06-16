

[中文文档](./README_CN.md) | English

![YJLDAT GUI](./images/图1.png)

**YJLDAT** (Yunju Latency and Display Analysis Tool) is a low-cost, high-precision measurement toolkit for analyzing end-to-end latency across PC peripherals, displays, and games.

This project includes a Windows GUI application and firmware for RP2040 microcontrollers to measure:

- Mouse / keyboard input latency
- Display response time
- End-to-end latency in Pyglet benchmark environment
- Real-world game input-to-photon latency
- Mouse polling rate
- Rapid fire, SOCD, reaction time, and other peripheral behaviors

> This project is protected by Chinese invention patent.  
> Patent No.: `ZL 2026 1 0104896.0`

---

## Features

- Physics-based input trigger detection
- Photosensitive sensor for screen brightness changes
- Full-chain latency breakdown (peripheral → display → game)
- Dynamic ambient light support for display response testing
- Statistical analysis (mean, standard deviation, stability metrics)
- Low-cost hardware setup
- Graphical Windows interface

---

## Installation

### Option 1: Download Pre-built Binaries (Recommended)

Visit the [Releases](https://github.com/yunjuyihao/YJLDAT/releases) page to download:

- `YJLDAT_GUI_V1.9.exe` - Windows GUI application (no Python required)
- `unified_firmware.uf2` - Pre-compiled firmware for RP2040

**Firmware Installation:**

1. Hold the `BOOTSEL` button on your RP2040 board
2. Connect the board to your PC via USB while holding the button
3. The board will appear as a USB drive (e.g., `RPI-RP2`)
4. Drag and drop `unified_firmware.uf2` onto the drive
5. The board will reboot automatically

**GUI Usage:**

1. Download `YJLDAT_GUI_V1.9.exe`
2. Run directly - no installation needed

---

### Option 2: Build from Source

**Requirements:**

- Python 3.8+
- Arduino IDE (for firmware compilation)

**Steps:**

1. Clone this repository:
   ```bash
   git clone https://github.com/yunjuyihao/YJLDAT.git
   cd YJLDAT
   ```

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the GUI:
   ```bash
   python YJLDAT_GUI_V1.9.py
   ```

4. (Optional) Compile firmware:
   - Open `unified_firmware/unified_firmware.ino` in Arduino IDE
   - Select board: `Raspberry Pi Pico` or `Raspberry Pi Pico 2`
   - Compile and upload

---

## Hardware Requirements

**Basic Components:**

- RP2040 development board
- Alligator clip cables
- Copper foil tape
- Photodiode / photosensitive sensor module
- Jumper wires
- Windows PC

**Typical Wiring:**

```text
GP16 → Alligator clip → Copper foil tape → Surface of button under test

USB connector shell / GND → Alligator clip → Hand-held ground

GP26 → Photosensor AO
3.3V → Photosensor VCC
GND  → Photosensor GND
```

**Tip:** Place an empty female jumper connector on GP17 to prevent accidental contact with the GP16 alligator clip.

---

## Software Structure

```text
YJLDAT 1124/
├── display_test_logic.py       # Display latency test logic
├── game_test_logic.py          # Game end-to-end latency test logic
├── gray_test_logic.py          # Gray scale / brightness response test logic
├── impulse_test_logic.py       # Impulse test logic
├── keymouse_logic.py           # Keyboard / mouse input latency test logic
├── mouse_rate_logic.py         # Mouse polling rate test logic
├── plot_panel.py               # Plotting and data visualization panel
├── pyglet_test_logic.py        # Pyglet benchmark end-to-end test logic
├── rapid_fire_logic.py         # Rapid fire test logic
├── reaction_test_logic.py      # Reaction time test logic
├── simul_test_logic.py         # Simultaneous / simulation test logic
├── socd_test_logic.py          # SOCD test logic
├── YJLDAT_GUI_V1.9.py          # Main GUI application
└── YJLDAT_GUI_V1.9.spec        # PyInstaller packaging configuration
```

---

## Main Test Modes

### 1. Key / Mouse Test

Measures input latency of mice, keyboards, and other input devices.

**Procedure:**

1. Attach copper foil tape to the surface of the button under test
2. Hold the grounded alligator clip in your hand
3. Tap the copper foil with moderate force
4. Repeat 30+ times until standard deviation stabilizes

**Principle:**

```text
Copper foil contact → MCU records start time
PC receives peripheral input signal → Host notifies MCU
MCU receives feedback → Records end time
```

Note: Results may be slightly inflated due to system input processing overhead.

---

### 2. Display Test

Measures display latency from software frame flip to optical brightness change detection.

**Procedure:**

1. Position the photosensor facing the screen
2. Start `display_test`
3. Press spacebar to enter fullscreen
4. Wait for automatic test completion

**Important:**

- Screen will flash rapidly between black and white
- Do not look directly at the screen during the test
- Do not move the photosensor
- Frame rate should exceed 5000 FPS after entering fullscreen

**Principle:**

```text
Software flips frame → Start time
Photosensor detects brightness change → End time
```

---

### 3. Pyglet Test

Measures end-to-end latency in a minimal rendering environment.

**Procedure:**

1. Attach copper foil tape to the left mouse button
2. Position the photosensor properly
3. Start the test and press spacebar to enter fullscreen
4. Tap the left mouse button (screen turns black then white)
5. Repeat approximately 30 times

**Principle:**

```text
Copper foil contact → Software receives mouse input → Screen changes → Photosensor detects change
```

---

### 4. Game Test

Measures end-to-end latency in real game scenarios.

**Procedure:**

1. Find a game scenario where pressing a key causes an "instant color change"
2. Attach copper foil tape to the corresponding key surface
3. Position the photosensor at the screen area that changes
4. Start the test
5. Repeat tapping approximately 30 times

**Principle:**

```text
Copper foil contact → Game receives input → Game screen changes → Photosensor detects change
```

---

## Accuracy Notes

Under ideal test conditions, this system can achieve sub-millisecond statistical stability.

**Example Test Performance:**

- 8000Hz reference input device: Standard deviation ≈ `0.05 ms`
- 8000Hz mouse: Standard deviation ≈ `0.08 ms - 0.1 ms`
- 300Hz gaming monitor: Standard deviation ≈ `0.91 ms - 0.94 ms`

**Factors Affecting Results:**

- USB polling rate
- Operating system scheduling
- Power plan settings
- Display refresh rate
- Screen brightness and PWM dimming
- Photosensor mounting stability
- Manual tapping consistency

---

## Recommended Test Environment

To minimize measurement jitter:

- Use high-performance power plan
- Disable CPU deep power-saving states
- Reduce background workload during testing
- Keep serial RTT below `200 μs`
- Use exclusive fullscreen mode
- Disable V-Sync in Display / Pyglet tests
- Repeat each test at least 30 times per dataset

---

## Known Limitations

1. The `keyboard` library conflicts with some GUI frameworks. You may need to click the taskbar to defocus the window before reading keyboard input.

2. Manual tapping introduces random error. For higher consistency, consider using mechanical structures or motors with known speeds to trigger the copper foil.

3. Display brightness, refresh rate, and PWM dimming methods vary across monitors and affect photoelectric test stability.

4. This project involves rapid screen flashing. Avoid prolonged direct viewing of the screen.

---

## Safety Notice

This project involves:

- Rapid screen flashing
- USB devices
- External wiring
- Photosensitive sensors
- Human contact with conductive materials

Ensure safe use at your own discretion.

**Do not look directly at rapidly flashing screens.**  
**Do not connect devices unless you are certain the wiring is safe.**

---

## License

This project is source-available for non-commercial use only.

- Copyright: 云居一号 (Yunju Yihao)
- Patent No.: `ZL 2026 1 0104896.0`
- Commercial use is prohibited without prior written permission
- No patent license is granted

See [`LICENSE`](./LICENSE) for details.

---

## Author

云居一号 (Yunju Yihao)

---

## Disclaimer

This project is provided for research, learning, verification, and non-commercial personal use only.

The author is not responsible for hardware damage, data loss, personal injury, business loss, or any other consequences caused by improper use.
