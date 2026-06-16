// unified_firmware.ino
#include <Arduino.h>

// ------------------ 引脚定义 ------------------
const int SENSOR_PIN = 26;        // 光敏接模拟口 GP26 (ADC0)
const int START_PIN  = 16;        // 外部触发 / KEYMOUSE 输入
const int LED_PIN    = LED_BUILTIN;

// ------------------ 模式定义 ------------------
enum TestMode : uint8_t {
  MODE_IDLE = 0,
  MODE_DISPLAY,        // M1: 显示器延迟 (白->黑)
  MODE_INPUT_TRIGGER,  // M2: 游戏全链路 (动态光感范围)
  MODE_KEYMOUSE,       // M3: 键鼠硬件延迟
  MODE_REACTION,       // M4: 反应测试 (抬起触发)
  MODE_GRAY_TEST       // M5: 灰阶响应 (GtG)
};
volatile TestMode currentMode = MODE_IDLE;

// ------------------ M1 全局变量 ------------------
int sensorThreshold_M1 = 600; 
int sensorThreshold_Auto = 600; 
// ------------------ M2 配置 ------------------
const int START_ACTIVE_STATE = LOW;
const int START_IDLE_STATE   = HIGH;
const unsigned long SAMPLE_US    = 2UL;
const unsigned long TIMEOUT_US   = 2000000UL; // 2秒超时
const unsigned long TIMEOUT_REPORT = 9999999UL; 

// ------------------ M3(KEYMOUSE) 参数 ------------------
static const uint16_t KM_INTERVAL_MS    = 150;
static const uint16_t KM_DEBOUNCE_COUNT = 5;
static const uint32_t KM_TIMEOUT_MS     = 60;
static volatile bool km_waitingHost = false;
static volatile bool km_gotDEvent   = false;
static uint16_t km_debCnt           = 0;
static unsigned long km_start_us    = 0;

// ------------------ M5(GRAY TEST) 变量 ------------------
int grayCalibValues[8] = {0}; // 存储8个灰阶的校准ADC值

// ------------------ 通用缓冲 ------------------
static String lineBuf;

// ------------------ 前置声明 ------------------
void handle_display_test();
void handle_input_trigger_test();
void handle_keymouse_test();
void handle_reaction_test();
void perform_m1_calibration();
void handle_gray_calibration(int idx);
void handle_gray_transition(int fromIdx, int toIdx);

// ------------------ 辅助函数 ------------------

static void handleLine(const String &line) {
  String s = line;
  s.trim();
  if (s.length() == 0) return;
  if (s.equalsIgnoreCase(F("HELLO"))) {
    Serial.println(F("READY"));
  }
}

static void pollSerial() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();

    // --- 模式切换指令 (M1-M5) ---
    if (c == 'M') {
      while (Serial.available() == 0) { }
      char m = (char)Serial.read();
      if (m == '1') {
        currentMode = MODE_DISPLAY;
        digitalWrite(LED_PIN, LOW);
        Serial.println(F("[PICO] Mode 1 (Display)."));
      } else if (m == '2') {
        currentMode = MODE_INPUT_TRIGGER;
        digitalWrite(LED_PIN, LOW);
        Serial.println(F("[PICO] Mode 2 (Game)."));
      } else if (m == '3') {
        currentMode = MODE_KEYMOUSE;
        digitalWrite(LED_PIN, LOW);
        km_waitingHost = false;
        km_gotDEvent = false;
        Serial.println(F("[PICO] Mode 3 (KeyMouse)."));
      } else if (m == '4') { 
        currentMode = MODE_REACTION;
        digitalWrite(LED_PIN, LOW);
        Serial.println(F("[PICO] Mode 4 (Reaction)."));
      } else if (m == '5') {
        currentMode = MODE_GRAY_TEST;
        digitalWrite(LED_PIN, LOW);
        Serial.println(F("[PICO] Mode 5 (GtG)."));
      } 
      continue;
    }

    // --- 通用指令 ---
    // RTT Echo
    if (c == 'R') {
      Serial.write('r');
      continue;
    }

    // --- M1/M2 专用: 校准 (C) ---
    if ((currentMode == MODE_DISPLAY || currentMode == MODE_INPUT_TRIGGER) && c == 'C') {
      perform_m1_calibration();
      continue;
    }

    // --- M1 专用: 开始 (S) ---
    if (currentMode == MODE_DISPLAY && c == 'S') {
      handle_display_test();
      continue;
    }

    // --- M3 专用: 主机确认 (D) ---
    if (currentMode == MODE_KEYMOUSE && c == 'D') {
      if (km_waitingHost) km_gotDEvent = true;
      continue;
    }

    // --- M5 专用: 校准(Cx) 与 测试(Txy) ---
    if (currentMode == MODE_GRAY_TEST) {
      // 校准指令: C0 - C7
      if (c == 'C') {
        while (Serial.available() == 0) {}
        char idxChar = (char)Serial.read();
        int idx = idxChar - '0';
        if (idx >= 0 && idx <= 7) {
          handle_gray_calibration(idx);
        }
        continue;
      }
      // 测试指令: Txy (x=start, y=end)
      if (c == 'T') {
         while (Serial.available() < 2) {} 
         char startChar = (char)Serial.read();
         char endChar = (char)Serial.read();
         int startIdx = startChar - '0';
         int endIdx = endChar - '0';
         if (startIdx >= 0 && startIdx <= 7 && endIdx >= 0 && endIdx <= 7) {
           handle_gray_transition(startIdx, endIdx);
         }
         continue;
      }
    }

    // --- 行协议处理 ---
    if (c == '\n') {
      handleLine(lineBuf);
      lineBuf = "";
    } else if (c != '\r') {
      if (lineBuf.length() < 64) lineBuf += c;
      else lineBuf = "";
    }
  }
}

void setup() {
  Serial.begin(115200);
  analogReadResolution(12); // 0-4095
  pinMode(SENSOR_PIN, INPUT);
  pinMode(START_PIN, INPUT_PULLUP);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  randomSeed(analogRead(27) + micros()); 
  delay(1000);
  Serial.println(F("[PICO] Firmware Ready."));
}

void loop() {
  pollSerial();
  
  // 主动轮询模式的处理
  switch (currentMode) {
    case MODE_INPUT_TRIGGER: // M2 需持续监听
      handle_input_trigger_test(); 
      break;
    case MODE_KEYMOUSE:      // M3 需持续监听
      handle_keymouse_test();      
      break;
    case MODE_REACTION:      // M4 需持续监听
      handle_reaction_test();
      break;
    default:
      // M1, M5 是被动响应指令，无需在 loop 中轮询
      break;
  }
}

// ==================== M1/M2 通用校准 ====================
void perform_m1_calibration() {
  digitalWrite(LED_PIN, HIGH); 
  
  unsigned long start = millis();
  int max_val = 0;

  while (millis() - start < 500) {
    int val = analogRead(SENSOR_PIN);
    if (val > max_val) max_val = val;
    delayMicroseconds(50); 
  }

  // M1 阈值更新
  sensorThreshold_M1 = max_val + 8; 

  digitalWrite(LED_PIN, LOW);
}

// ==================== M1: Display Test ====================
void handle_display_test() {
  digitalWrite(LED_PIN, HIGH);
  unsigned long startTime = micros();
  
  while (true) {
    int val = analogRead(SENSOR_PIN);

    // 安全检查
    if (val == 0) { Serial.println(F("ERR_BRIGHT")); break; }
    if (val >= 4095) { Serial.println(F("ERR_DARK")); break; }

    if (val > sensorThreshold_M1) {
      unsigned long endTime = micros();
      Serial.println(endTime - startTime);
      break;
    }
    if (micros() - startTime > 2000000UL) {
      Serial.println(0); 
      break;
    }
  }
  Serial.flush();
  digitalWrite(LED_PIN, LOW);
}

// ==================== M2: Game Test ====================
void handle_input_trigger_test() {
  int active_min = 0;
  int active_max = 4095;
  int next_min = 4095;
  int next_max = 0;
  unsigned long swap_timer = millis();
  
  // --- 1. 动态校准 ---
  while (digitalRead(START_PIN) == START_IDLE_STATE) {
    if (Serial.available()) return;

    int val = analogRead(SENSOR_PIN);
    
    if (val < next_min) next_min = val;
    if (val > next_max) next_max = val;
    
    if (millis() - swap_timer > 100) {
      active_min = next_min;
      active_max = next_max;
      next_min = 4095;
      next_max = 0;
      swap_timer = millis();
    }
  }

  // --- 2. 消抖 ---
  for (unsigned int i = 1; i < 5; ++i) {
    delayMicroseconds(SAMPLE_US);
    if (digitalRead(START_PIN) == START_IDLE_STATE) return; 
  }

  // --- 3. 测量 ---
  unsigned long t_start = micros();
  digitalWrite(LED_PIN, HIGH);

  bool triggered = false;
  unsigned long t_end = 0;
  int margin = 8;
  int lower_bound = active_min - margin;
  int upper_bound = active_max + margin;

  while (micros() - t_start < TIMEOUT_US) {
    int val = analogRead(SENSOR_PIN);
    
    // 安全检查 (强制退出)
    if (val == 0) { 
      Serial.println(F("ERR_BRIGHT")); 
      digitalWrite(LED_PIN, LOW); 
      while (digitalRead(START_PIN) == START_ACTIVE_STATE) delay(1); 
      return; 
    }
    if (val >= 4095) { 
      Serial.println(F("ERR_DARK")); 
      digitalWrite(LED_PIN, LOW); 
      while (digitalRead(START_PIN) == START_ACTIVE_STATE) delay(1); 
      return; 
    }

    if (val < lower_bound || val > upper_bound) {
      t_end = micros();
      triggered = true;
      break;
    }
  }

  // --- 4. 报告 ---
  if (triggered && (t_end - t_start)>1000) Serial.println(t_end - t_start);
  else           Serial.println(TIMEOUT_REPORT);
  
  Serial.flush();
  digitalWrite(LED_PIN, LOW);

  while (digitalRead(START_PIN) == START_ACTIVE_STATE) { delay(1); }
  delay(50);
}

// ==================== M3: KeyMouse Test ====================
void handle_keymouse_test() {
  if (!km_waitingHost) {
    if (digitalRead(START_PIN) == LOW) {
      if (++km_debCnt >= KM_DEBOUNCE_COUNT) {
        km_waitingHost = true;
        km_gotDEvent = false;
        km_debCnt = 0;
        km_start_us = micros();
        digitalWrite(LED_PIN, HIGH);
      }
    } else {
      km_debCnt = 0;
    }
    return;
  }
  if (km_gotDEvent) {
    unsigned long delta = micros() - km_start_us;
    Serial.println(delta);
    Serial.flush();
    delay(KM_INTERVAL_MS);
    digitalWrite(LED_PIN, LOW);
    km_waitingHost = false;
    km_gotDEvent = false;
    return;
  }
  if ((micros() - km_start_us) / 1000UL > KM_TIMEOUT_MS) {
    digitalWrite(LED_PIN, LOW);
    km_waitingHost = false;
    km_gotDEvent = false;
  }
}

// ==================== M4: Reaction Test ====================
void handle_reaction_test() {
  if (digitalRead(START_PIN) == HIGH) { delay(10); return; } // 等待按下
  delay(20);
  if (digitalRead(START_PIN) == HIGH) return; 

  unsigned long wait_time = random(3000, 5001);
  unsigned long start_wait = millis();
  bool early_release = false;

  while (millis() - start_wait < wait_time) {
    if (Serial.available()) return; // 允许PC中断
    if (digitalRead(START_PIN) == HIGH) {
      delay(5); 
      if (digitalRead(START_PIN) == HIGH) {
        early_release = true;
        break;
      }
    }
  }

  if (early_release) {
    Serial.println(F("EARLY")); 
    delay(500); 
    return; 
  }

  digitalWrite(LED_PIN, HIGH);
  unsigned long t_start = micros();
  bool triggered = false;
  unsigned long t_result = 0;

  while (micros() - t_start < 1000000UL) {
    if (digitalRead(START_PIN) == HIGH) {
      t_result = micros() - t_start;
      triggered = true;
      break;
    }
  }

  digitalWrite(LED_PIN, LOW);
  
  if (triggered) {
    Serial.println(t_result);
  } else {
    Serial.println(F("TIMEOUT"));
    while(digitalRead(START_PIN) == LOW); 
  }
  delay(100);
}

// ==================== M5: Gray-to-Gray Test ====================

// M5 校准: 为了保险起见，取1秒窗口的中间600ms进行采样
void handle_gray_calibration(int idx) {
  digitalWrite(LED_PIN, HIGH);
  
  // 1. 初始延时: 避开屏幕翻转的过渡期和通信抖动 (200ms)
  delay(200); 
  
  long sum = 0;
  int count = 0;
  // 2. 采样窗口: 持续 600ms
  unsigned long start = millis();
  
  while (millis() - start < 600) {
    int val = analogRead(SENSOR_PIN);
    
    // 安全检查
    if (val == 0) {
      Serial.println(F("ERR_BRIGHT"));
      digitalWrite(LED_PIN, LOW);
      return;
    }
    if (val >= 4095) {
      Serial.println(F("ERR_DARK"));
      digitalWrite(LED_PIN, LOW);
      return;
    }
    
    sum += val;
    count++;
    // 适当间隔，防止数据溢出
    delayMicroseconds(500); 
  }
  
  // 3. 计算并存储
  if (count > 0) {
    grayCalibValues[idx] = sum / count;
    Serial.print(F("CAL_OK:"));
    Serial.println(grayCalibValues[idx]); 
  } else {
    Serial.println(F("ERR_CAL"));
  }
  
  // 4. 剩余时间不做处理，自然结束
  digitalWrite(LED_PIN, LOW);
}


void handle_gray_transition(int fromIdx, int toIdx) {
  int startBase = grayCalibValues[fromIdx];
  int endBase   = grayCalibValues[toIdx];
  int delta = endBase - startBase;



  // 计算 10% 和 90% 的阈值
  // 注意：如果是下降沿 (White -> Black)，delta 是负数，逻辑依然成立
  // 阈值计算必须使用 float 防止整数截断误差太大，最后转回 int
  int thresh10 = startBase + (int)(delta * 0.1f);
  int thresh90 = startBase + (int)(delta * 0.9f);

  // 判断方向
  bool rising = (delta > 0);

  unsigned long timeout = micros() + 1000000UL; // 1秒超时
  unsigned long t_10pct = 0;
  unsigned long t_90pct = 0;
  
  digitalWrite(LED_PIN, HIGH);

  // --- 阶段 1: 等待越过 10% 阈值 ---
  while (true) {
    if (micros() > timeout) { Serial.println(0); digitalWrite(LED_PIN, LOW); return; }
    
    int val = analogRead(SENSOR_PIN);
    if (val == 0 || val == 4095) { Serial.println(val == 0 ? F("ERR_BRIGHT") : F("ERR_DARK")); digitalWrite(LED_PIN, LOW); return; }

    bool crossed10 = rising ? (val >= thresh10) : (val <= thresh10);
    
    if (crossed10) {
      t_10pct = micros();
      break;
    }
  }

  // --- 阶段 2: 等待越过 90% 阈值 ---
  while (true) {
    if (micros() > timeout) { Serial.println(0); digitalWrite(LED_PIN, LOW); return; }
    
    int val = analogRead(SENSOR_PIN);
    
    bool crossed90 = rising ? (val >= thresh90) : (val <= thresh90);

    if (crossed90) {
      t_90pct = micros();
      break;
    }
  }
  
  // 返回结果
  if (t_90pct > t_10pct) {
    Serial.println(t_90pct - t_10pct);
  } else {
    Serial.println(1); 
  }
  
  digitalWrite(LED_PIN, LOW);
}
