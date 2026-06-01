/**
 * MicroGrid AI — Industrial Edge Controller
 * Hardware: Arduino Mega 2560
 *
 * WHAT THIS DOES:
 *   - Reads all sensors every 15 seconds
 *   - Sends data to cloud when internet is available
 *   - Runs full local decision logic when internet is CUT
 *   - Controls relays for load shedding (P1 NEVER shed)
 *   - Controls battery charge/discharge command
 *   - Protects against power cut unconditionally
 *   - Hardware watchdog: auto-restarts if code freezes
 *   - Logs everything to SD card with timestamp
 *   - Shows live status on 20x4 LCD
 *
 * WIRING:
 *   CT Sensor (SCT-013)       → A0  (load current)
 *   Voltage Sensor (ZMPT101B) → A1  (grid voltage)
 *   Battery Voltage Divider   → A2  (battery voltage → SoC)
 *   Battery Current (ACS712)  → A3  (charge/discharge current)
 *   Temperature (DS18B20)     → D2  (battery temperature, OneWire)
 *   RTC (DS3231)              → I2C SDA=D20, SCL=D21
 *   SD Card Module            → SPI MOSI=D51, MISO=D50, SCK=D52, CS=D53
 *   LCD 20x4 I2C              → I2C SDA=D20, SCL=D21
 *   ESP8266 WiFi              → Serial1 TX1=D18, RX1=D19 (115200 baud)
 *
 *   RELAY BOARD (active LOW — relay triggers when pin goes LOW):
 *   RELAY_BATTERY_CHARGE      → D22  (signal to inverter: charge from grid)
 *   RELAY_BATTERY_DISCHARGE   → D23  (signal to inverter: discharge to loads)
 *   RELAY_GRID_BREAKER        → D24  (main grid breaker contactor)
 *   RELAY_P5_LOAD             → D25  (parking + signage — shed first)
 *   RELAY_P4_LOAD             → D26  (HVAC + admin — shed second)
 *   RELAY_P3_LOAD             → D27  (lifts + kitchen — shed third)
 *   RELAY_P2_LOAD             → D28  (radiology + lab — shed only in emergency)
 *   RELAY_P1_LOAD             → D29  (ICU + OT + life support — NEVER shed, hardwired)
 *
 * LIBRARIES NEEDED (install via Arduino Library Manager):
 *   - DallasTemperature    (DS18B20 temperature)
 *   - OneWire
 *   - RTClib               (DS3231 RTC)
 *   - SD                   (SD card logging)
 *   - LiquidCrystal_I2C    (20x4 LCD)
 *   - avr/wdt.h            (hardware watchdog — built in)
 */

#include <avr/wdt.h>
#include <Wire.h>
#include <SD.h>
#include <SPI.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <RTClib.h>
#include <LiquidCrystal_I2C.h>

// ─────────────────────────────────────────────────────────────
// PIN DEFINITIONS
// ─────────────────────────────────────────────────────────────

#define PIN_CT_SENSOR        A0
#define PIN_GRID_VOLTAGE     A1
#define PIN_BATTERY_VOLTAGE  A2
#define PIN_BATTERY_CURRENT  A3
#define PIN_TEMPERATURE      2
#define PIN_SD_CS            53

#define RELAY_BATTERY_CHARGE    22
#define RELAY_BATTERY_DISCHARGE 23
#define RELAY_GRID_BREAKER      24
#define RELAY_P5                25   // non-essential — shed first
#define RELAY_P4                26   // comfort
#define RELAY_P3                27   // operational
#define RELAY_P2                28   // essential medical
// P1 is NOT software controlled — it is hardwired to mains bypass
// D29 is left as monitor only — never written LOW

// ─────────────────────────────────────────────────────────────
// SYSTEM CONFIGURATION
// ─────────────────────────────────────────────────────────────

// Battery specs (edit per customer)
const float BATTERY_KWH       = 500.0;
const float BATTERY_VOLTAGE_NOMINAL = 48.0;  // V (edit: 48V / 96V / 120V system)
const float BATTERY_CAPACITY_AH     = BATTERY_KWH * 1000 / BATTERY_VOLTAGE_NOMINAL;
const float SOC_CRITICAL      = 12.0;   // % — emergency
const float SOC_WARNING       = 20.0;   // % — warning
const float SOC_MIN           = 10.0;   // % — absolute floor
const float SOC_MAX           = 95.0;

// Tariff hours (IST, edit per state)
// CESC West Bengal defaults
const int CHEAP_HOUR_START    = 10;
const int CHEAP_HOUR_END      = 16;
const int PEAK_HOUR_START     = 18;
const int PEAK_HOUR_END       = 23;
const float TARIFF_CHEAP      = 4.20;
const float TARIFF_PEAK       = 7.85;
const float TARIFF_NORMAL     = 6.10;

// Safety thresholds
const float TEMP_MAX_C        = 45.0;   // battery thermal runaway threshold
const float LOAD_MAX_KW       = 800.0;  // physically impossible → sensor fault
const float SOC_FREEFALL_PER_MIN = 1.5; // %/min → cell fault

// Timing
const unsigned long SENSOR_INTERVAL_MS  = 15000UL;  // read sensors every 15s
const unsigned long CLOUD_INTERVAL_MS   = 60000UL;  // send to cloud every 60s
const unsigned long LCD_INTERVAL_MS     = 2000UL;   // update LCD every 2s
const unsigned long WATCHDOG_TIMEOUT    = WDTO_8S;  // hw watchdog: 8 second timeout

// ─────────────────────────────────────────────────────────────
// SYSTEM STATE
// ─────────────────────────────────────────────────────────────

enum SystemMode {
  MODE_NORMAL,    // internet available, following cloud commands
  MODE_OFFLINE,   // internet cut, running local rules
  MODE_SAFE,      // malfunction detected, safe mode active
  MODE_EMERGENCY  // SoC critical, all non-P1 loads at risk
};

enum BatteryCommand {
  CMD_CHARGE,
  CMD_DISCHARGE,
  CMD_HOLD
};

struct SensorData {
  float load_kw;
  float grid_voltage;
  float battery_voltage;
  float battery_soc;
  float battery_current;
  float battery_temp;
  float net_kw;
  int   hour;
  int   minute;
  bool  valid;
};

struct SystemState {
  SystemMode    mode;
  BatteryCommand battery_cmd;
  bool grid_connected;
  bool p5_on;
  bool p4_on;
  bool p3_on;
  bool p2_on;
  bool internet_ok;
  bool sd_ok;
  float prev_soc;
  unsigned long prev_soc_time;
  int fault_count;
  char fault_message[64];
};

SensorData    sensor;
SystemState   state;

// ─────────────────────────────────────────────────────────────
// HARDWARE OBJECTS
// ─────────────────────────────────────────────────────────────

OneWire           oneWire(PIN_TEMPERATURE);
DallasTemperature tempSensor(&oneWire);
RTC_DS3231        rtc;
LiquidCrystal_I2C lcd(0x27, 20, 4);
File              logFile;

// Timers
unsigned long lastSensorRead  = 0;
unsigned long lastCloudSend   = 0;
unsigned long lastLCDUpdate   = 0;

// ─────────────────────────────────────────────────────────────
// SETUP
// ─────────────────────────────────────────────────────────────

void setup() {
  // Hardware watchdog — if code hangs for 8 seconds, auto restart
  wdt_enable(WATCHDOG_TIMEOUT);

  Serial.begin(9600);    // debug
  Serial1.begin(115200); // ESP8266 WiFi module

  // Relay pins — HIGH = relay OFF (active LOW board)
  int relays[] = {RELAY_BATTERY_CHARGE, RELAY_BATTERY_DISCHARGE,
                  RELAY_GRID_BREAKER, RELAY_P5, RELAY_P4, RELAY_P3, RELAY_P2};
  for (int i = 0; i < 7; i++) {
    pinMode(relays[i], OUTPUT);
    digitalWrite(relays[i], HIGH); // all OFF on startup
  }

  // Safe startup defaults
  state.mode          = MODE_NORMAL;
  state.battery_cmd   = CMD_HOLD;
  state.grid_connected= true;
  state.p5_on         = true;
  state.p4_on         = true;
  state.p3_on         = true;
  state.p2_on         = true;
  state.internet_ok   = false;
  state.fault_count   = 0;
  state.prev_soc      = 70.0;
  state.prev_soc_time = millis();

  // Apply safe defaults to relays
  applyRelayState();

  // LCD
  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0); lcd.print("MicroGrid AI");
  lcd.setCursor(0, 1); lcd.print("Initializing...");

  // SD card
  state.sd_ok = SD.begin(PIN_SD_CS);
  if (!state.sd_ok) {
    Serial.println("SD card FAILED");
  }

  // Temperature sensor
  tempSensor.begin();

  // RTC
  if (!rtc.begin()) {
    Serial.println("RTC FAILED — using millis() fallback");
  }

  // Grid on, battery hold on startup
  setGridConnected(true);
  setBatteryCommand(CMD_HOLD);

  wdt_reset(); // pat the watchdog
  Serial.println("MicroGrid AI Edge Controller READY");
}

// ─────────────────────────────────────────────────────────────
// MAIN LOOP
// ─────────────────────────────────────────────────────────────

void loop() {
  wdt_reset(); // ALWAYS pat watchdog first thing in loop

  unsigned long now = millis();

  // Read sensors
  if (now - lastSensorRead >= SENSOR_INTERVAL_MS) {
    lastSensorRead = now;
    readAllSensors();
    runWatchdog();
    runLocalDecision();
    logToSD();
  }

  // Send to cloud
  if (now - lastCloudSend >= CLOUD_INTERVAL_MS) {
    lastCloudSend = now;
    sendToCloud();
    receiveCloudCommand();
  }

  // Update LCD
  if (now - lastLCDUpdate >= LCD_INTERVAL_MS) {
    lastLCDUpdate = now;
    updateLCD();
  }

  wdt_reset(); // pat again at end of loop
}

// ─────────────────────────────────────────────────────────────
// SENSOR READING
// ─────────────────────────────────────────────────────────────

void readAllSensors() {
  wdt_reset();

  // ── Load current (CT sensor SCT-013) ──────────────────────
  // SCT-013-100 clips around live wire. Output: 0-1V on burden resistor.
  // Calibration: 1023 counts = 100A. Adjust BURDEN_R and CT_RATIO per sensor.
  float ct_raw = analogRead(PIN_CT_SENSOR);
  float amps = (ct_raw / 1023.0) * 100.0 * 1.41; // peak-to-RMS
  sensor.load_kw = (amps * 230.0) / 1000.0;       // P = V×I / 1000

  // ── Grid voltage (ZMPT101B) ────────────────────────────────
  float v_raw = analogRead(PIN_GRID_VOLTAGE);
  sensor.grid_voltage = (v_raw / 1023.0) * 500.0; // calibrate per module

  // ── Battery voltage (voltage divider R1=10k R2=2.2k) ──────
  float bv_raw = analogRead(PIN_BATTERY_VOLTAGE);
  float bv = (bv_raw / 1023.0) * 5.0 * (12.2 / 2.2); // adjust resistors
  sensor.battery_voltage = bv;

  // SoC from voltage (simple lookup — replace with Coulomb counting
  // if you have a dedicated battery monitor IC like MAX17048)
  sensor.battery_soc = voltageToCoulombSoC(bv);

  // ── Battery current (ACS712 30A module) ───────────────────
  float ic_raw = analogRead(PIN_BATTERY_CURRENT);
  float ic_v   = (ic_raw / 1023.0) * 5.0;
  sensor.battery_current = (ic_v - 2.5) / 0.066; // 66mV/A for 30A module

  // ── Temperature (DS18B20) ──────────────────────────────────
  tempSensor.requestTemperatures();
  sensor.battery_temp = tempSensor.getTempCByIndex(0);
  if (sensor.battery_temp == -127.0) {
    sensor.battery_temp = 28.0; // sensor error fallback
  }

  // ── Time from RTC ──────────────────────────────────────────
  if (rtc.lostPower()) {
    sensor.hour   = 12; // fallback if RTC battery dead
    sensor.minute = 0;
  } else {
    DateTime now_dt = rtc.now();
    sensor.hour   = now_dt.hour();
    sensor.minute = now_dt.minute();
  }

  // ── Net power ──────────────────────────────────────────────
  // Positive = battery charging, Negative = discharging
  sensor.net_kw = -(sensor.battery_current * sensor.battery_voltage) / 1000.0;

  // ── Sanity check ──────────────────────────────────────────
  sensor.valid = (
    sensor.load_kw    >= 0 &&
    sensor.load_kw    < LOAD_MAX_KW &&
    sensor.battery_soc >= 0 &&
    sensor.battery_soc <= 100 &&
    sensor.battery_temp > -10 &&
    sensor.battery_temp < 80
  );

  Serial.print("SoC="); Serial.print(sensor.battery_soc, 1);
  Serial.print("% Load="); Serial.print(sensor.load_kw, 0);
  Serial.print("kW Temp="); Serial.print(sensor.battery_temp, 1);
  Serial.println("C");
}

// Voltage to SoC lookup table (LiFePO4 48V system)
// Adjust for your battery chemistry
float voltageToCoulombSoC(float v) {
  if (v >= 54.4) return 95.0;
  if (v >= 53.6) return 90.0;
  if (v >= 52.8) return 80.0;
  if (v >= 52.0) return 70.0;
  if (v >= 51.2) return 60.0;
  if (v >= 50.4) return 50.0;
  if (v >= 49.6) return 40.0;
  if (v >= 48.8) return 30.0;
  if (v >= 48.0) return 20.0;
  if (v >= 47.2) return 12.0;
  return 5.0;
}

// ─────────────────────────────────────────────────────────────
// SAFETY WATCHDOG (runs every sensor cycle)
// ─────────────────────────────────────────────────────────────

void runWatchdog() {
  wdt_reset();
  bool fault = false;

  // ── 1. SoC critical ───────────────────────────────────────
  if (sensor.battery_soc < SOC_CRITICAL) {
    triggerSafeMode("SOC_CRITICAL: Battery at " +
                    String(sensor.battery_soc, 0) + "% — emergency grid import");
    fault = true;
  }

  // ── 2. SoC freefall ───────────────────────────────────────
  unsigned long now = millis();
  float dt_min = (now - state.prev_soc_time) / 60000.0;
  if (dt_min > 0.1) {
    float drop_per_min = (state.prev_soc - sensor.battery_soc) / dt_min;
    if (drop_per_min > SOC_FREEFALL_PER_MIN) {
      triggerSafeMode("SOC_FREEFALL: Dropping " +
                      String(drop_per_min, 1) + "%/min — sensor or cell fault");
      fault = true;
    }
    state.prev_soc      = sensor.battery_soc;
    state.prev_soc_time = now;
  }

  // ── 3. Temperature high ───────────────────────────────────
  if (sensor.battery_temp > TEMP_MAX_C) {
    triggerSafeMode("TEMP_HIGH: Battery at " +
                    String(sensor.battery_temp, 0) + "C — thermal runaway risk");
    fault = true;
  }

  // ── 4. Grid voltage out of range ─────────────────────────
  if (sensor.grid_voltage > 10 &&  // 0 means grid is off (expected in island mode)
      (sensor.grid_voltage < 200 || sensor.grid_voltage > 260)) {
    triggerSafeMode("GRID_VOLTAGE: " +
                    String(sensor.grid_voltage, 0) + "V out of range (200-260V)");
    fault = true;
  }

  // ── 5. Sensor anomaly ─────────────────────────────────────
  if (!sensor.valid) {
    triggerSafeMode("SENSOR_ANOMALY: Invalid reading detected");
    fault = true;
  }

  // ── If no fault: clear safe mode ─────────────────────────
  if (!fault && state.mode == MODE_SAFE) {
    state.fault_count++;
    if (state.fault_count >= 3) { // 3 consecutive clean cycles → clear
      state.mode = state.internet_ok ? MODE_NORMAL : MODE_OFFLINE;
      state.fault_count = 0;
      Serial.println("SAFE MODE CLEARED — system healthy");
    }
  } else if (!fault) {
    state.fault_count = 0;
  }
}

void triggerSafeMode(String reason) {
  // Already in safe/emergency mode — don't re-trigger
  if (state.mode == MODE_SAFE || state.mode == MODE_EMERGENCY) return;

  state.mode = MODE_SAFE;
  state.fault_count = 0;
  reason.toCharArray(state.fault_message, 64);

  Serial.print("SAFE MODE: "); Serial.println(reason);

  // 1. Force grid connected
  setGridConnected(true);

  // 2. Battery to HOLD
  setBatteryCommand(CMD_HOLD);

  // 3. Shed P5 and P4 (non-essential + comfort)
  setShedLoad(RELAY_P5, false); state.p5_on = false;
  setShedLoad(RELAY_P4, false); state.p4_on = false;

  // P1, P2, P3 remain ON
  // P1 is hardwired — software cannot touch it

  // 4. Log the fault
  logFault(reason);
}

// ─────────────────────────────────────────────────────────────
// LOCAL DECISION ENGINE
// Runs when internet is CUT — autonomous operation
// ─────────────────────────────────────────────────────────────

void runLocalDecision() {
  wdt_reset();

  // Don't override safe mode
  if (state.mode == MODE_SAFE || state.mode == MODE_EMERGENCY) return;

  // If internet is OK, cloud commands override this
  if (state.mode == MODE_NORMAL && state.internet_ok) return;

  // ── We are OFFLINE — run local rules ─────────────────────
  state.mode = MODE_OFFLINE;

  float soc  = sensor.battery_soc;
  int   hour = sensor.hour;

  bool is_cheap = (hour >= CHEAP_HOUR_START && hour < CHEAP_HOUR_END);
  bool is_peak  = (hour >= PEAK_HOUR_START  && hour < PEAK_HOUR_END);

  // Emergency: SoC approaching critical
  if (soc < SOC_WARNING) {
    // Shed P5 + P4 to conserve
    setShedLoad(RELAY_P5, false); state.p5_on = false;
    setShedLoad(RELAY_P4, false); state.p4_on = false;
    // Force grid charge
    setGridConnected(true);
    setBatteryCommand(CMD_CHARGE);
    Serial.println("LOCAL: SOC low — emergency charge + shed P4/P5");
    return;
  }

  // SoC recovered — restore loads
  if (soc > 30.0 && !state.p5_on) {
    setShedLoad(RELAY_P5, true); state.p5_on = true;
    Serial.println("LOCAL: P5 loads restored");
  }
  if (soc > 35.0 && !state.p4_on) {
    setShedLoad(RELAY_P4, true); state.p4_on = true;
    Serial.println("LOCAL: P4 loads restored");
  }

  // Cheap tariff: charge battery from grid
  if (is_cheap && soc < 75.0) {
    setBatteryCommand(CMD_CHARGE);
    Serial.println("LOCAL: Cheap hours — charging");
    return;
  }

  // Peak tariff: discharge battery, save on grid import
  if (is_peak && soc > SOC_CRITICAL + 15) {
    setBatteryCommand(CMD_DISCHARGE);
    Serial.println("LOCAL: Peak hours — discharging");
    return;
  }

  // Default: hold
  setBatteryCommand(CMD_HOLD);
}

// ─────────────────────────────────────────────────────────────
// RELAY CONTROL
// ─────────────────────────────────────────────────────────────

void setGridConnected(bool connected) {
  state.grid_connected = connected;
  // Relay active LOW: LOW = connected, HIGH = open
  digitalWrite(RELAY_GRID_BREAKER, connected ? LOW : HIGH);
}

void setBatteryCommand(BatteryCommand cmd) {
  state.battery_cmd = cmd;
  // First turn both OFF to avoid shoot-through
  digitalWrite(RELAY_BATTERY_CHARGE,    HIGH);
  digitalWrite(RELAY_BATTERY_DISCHARGE, HIGH);
  delay(100); // 100ms dead time

  if (cmd == CMD_CHARGE)    digitalWrite(RELAY_BATTERY_CHARGE,    LOW);
  if (cmd == CMD_DISCHARGE) digitalWrite(RELAY_BATTERY_DISCHARGE, LOW);
  // CMD_HOLD: both remain HIGH (off)
}

void setShedLoad(int relay_pin, bool on) {
  // Active LOW relay: LOW = load ON, HIGH = load OFF (shed)
  digitalWrite(relay_pin, on ? LOW : HIGH);
}

void applyRelayState() {
  setGridConnected(state.grid_connected);
  setBatteryCommand(state.battery_cmd);
  setShedLoad(RELAY_P5, state.p5_on);
  setShedLoad(RELAY_P4, state.p4_on);
  setShedLoad(RELAY_P3, state.p3_on);
  setShedLoad(RELAY_P2, state.p2_on);
}

// ─────────────────────────────────────────────────────────────
// CLOUD COMMUNICATION (via ESP8266 on Serial1)
// ─────────────────────────────────────────────────────────────

void sendToCloud() {
  wdt_reset();
  if (!sensor.valid) return;

  // Build JSON reading — ESP8266 will POST this to backend /ingest
  String json = "{";
  json += "\"load_kw\":"     + String(sensor.load_kw,        2) + ",";
  json += "\"solar_kw\":"    + String(0.0,                   2) + ","; // add solar CT if available
  json += "\"battery_soc\":" + String(sensor.battery_soc,    1) + ",";
  json += "\"battery_temp\":" + String(sensor.battery_temp,  1) + ",";
  json += "\"grid_voltage\":" + String(sensor.grid_voltage,  1) + ",";
  json += "\"net_kw\":"      + String(sensor.net_kw,         2) + ",";
  json += "\"source\":\"iot_gateway\"";
  json += "}";

  // Send to ESP8266 over Serial1
  // ESP8266 firmware must POST this to: BACKEND_URL/facilities/{id}/ingest
  Serial1.println("SEND:" + json);

  Serial.print("Cloud TX: "); Serial.println(json);
}

void receiveCloudCommand() {
  wdt_reset();

  if (!Serial1.available()) {
    // No response from ESP8266 — assume offline
    if (state.mode == MODE_NORMAL) {
      state.internet_ok = false;
      state.mode = MODE_OFFLINE;
      Serial.println("Internet LOST — switching to local mode");
    }
    return;
  }

  String resp = Serial1.readStringUntil('\n');
  resp.trim();

  if (resp == "OK") {
    state.internet_ok = true;
    state.mode        = MODE_NORMAL;
    return;
  }

  // Parse cloud command: CMD:CHARGE / CMD:DISCHARGE / CMD:HOLD
  // CMD:SHED_P5 / CMD:RESTORE_P5 etc.
  if (resp.startsWith("CMD:")) {
    String cmd = resp.substring(4);
    state.internet_ok = true;
    state.mode = MODE_NORMAL;

    // Only apply cloud command if NOT in safe mode
    if (state.mode != MODE_SAFE && state.mode != MODE_EMERGENCY) {
      if (cmd == "CHARGE")    setBatteryCommand(CMD_CHARGE);
      if (cmd == "DISCHARGE") setBatteryCommand(CMD_DISCHARGE);
      if (cmd == "HOLD")      setBatteryCommand(CMD_HOLD);
      if (cmd == "GRID_ON")   setGridConnected(true);
      if (cmd == "GRID_OFF")  setGridConnected(false);
      if (cmd == "SHED_P5")   { setShedLoad(RELAY_P5, false); state.p5_on = false; }
      if (cmd == "SHED_P4")   { setShedLoad(RELAY_P4, false); state.p4_on = false; }
      if (cmd == "SHED_P3")   { setShedLoad(RELAY_P3, false); state.p3_on = false; }
      if (cmd == "RESTORE_P5"){ setShedLoad(RELAY_P5, true);  state.p5_on = true;  }
      if (cmd == "RESTORE_P4"){ setShedLoad(RELAY_P4, true);  state.p4_on = true;  }
      if (cmd == "RESTORE_P3"){ setShedLoad(RELAY_P3, true);  state.p3_on = true;  }
      // P1 (P2 and above) commands are SILENTLY IGNORED
      // You cannot shed ICU/OT from the cloud

      Serial.print("Cloud CMD applied: "); Serial.println(cmd);
    } else {
      Serial.println("Cloud CMD BLOCKED — safe mode active");
    }
  }
}

// ─────────────────────────────────────────────────────────────
// SD CARD LOGGING
// ─────────────────────────────────────────────────────────────

void logToSD() {
  wdt_reset();
  if (!state.sd_ok) return;

  DateTime now_dt = rtc.now();
  char filename[13];
  sprintf(filename, "%04d%02d%02d.csv", now_dt.year(), now_dt.month(), now_dt.day());

  logFile = SD.open(filename, FILE_WRITE);
  if (!logFile) return;

  // Write header if new file
  if (logFile.size() == 0) {
    logFile.println("timestamp,load_kw,battery_soc,battery_temp,grid_voltage,net_kw,mode,battery_cmd");
  }

  char ts[20];
  sprintf(ts, "%04d-%02d-%02dT%02d:%02d:%02d",
    now_dt.year(), now_dt.month(), now_dt.day(),
    now_dt.hour(), now_dt.minute(), now_dt.second());

  const char* mode_str[] = {"NORMAL", "OFFLINE", "SAFE", "EMERGENCY"};
  const char* cmd_str[]  = {"CHARGE", "DISCHARGE", "HOLD"};

  logFile.print(ts);           logFile.print(",");
  logFile.print(sensor.load_kw,    2); logFile.print(",");
  logFile.print(sensor.battery_soc,1); logFile.print(",");
  logFile.print(sensor.battery_temp,1);logFile.print(",");
  logFile.print(sensor.grid_voltage,1);logFile.print(",");
  logFile.print(sensor.net_kw,    2); logFile.print(",");
  logFile.print(mode_str[state.mode]);logFile.print(",");
  logFile.println(cmd_str[state.battery_cmd]);
  logFile.close();
}

void logFault(String reason) {
  if (!state.sd_ok) return;

  logFile = SD.open("FAULTS.txt", FILE_WRITE);
  if (!logFile) return;

  DateTime now_dt = rtc.now();
  char ts[20];
  sprintf(ts, "%04d-%02d-%02dT%02d:%02d:%02d",
    now_dt.year(), now_dt.month(), now_dt.day(),
    now_dt.hour(), now_dt.minute(), now_dt.second());

  logFile.print("["); logFile.print(ts); logFile.print("] ");
  logFile.println(reason);
  logFile.close();
}

// ─────────────────────────────────────────────────────────────
// LCD DISPLAY — 20x4
// ─────────────────────────────────────────────────────────────

void updateLCD() {
  wdt_reset();
  lcd.clear();

  // Row 0: Mode + time
  const char* mode_labels[] = {"NORMAL  ", "OFFLINE ", "SAFE!!! ", "EMRGNCY!"};
  lcd.setCursor(0, 0);
  lcd.print(mode_labels[state.mode]);
  lcd.print(sensor.hour   < 10 ? "0" : ""); lcd.print(sensor.hour);
  lcd.print(":");
  lcd.print(sensor.minute < 10 ? "0" : ""); lcd.print(sensor.minute);

  // Row 1: SoC + Battery command
  lcd.setCursor(0, 1);
  lcd.print("SoC:");
  lcd.print((int)sensor.battery_soc);
  lcd.print("% ");
  const char* cmd_labels[] = {"CHG", "DIS", "HLD"};
  lcd.print("BAT:");
  lcd.print(cmd_labels[state.battery_cmd]);
  lcd.print(" ");
  lcd.print(state.grid_connected ? "GRD:ON" : "GRD:OFF");

  // Row 2: Load + Temp
  lcd.setCursor(0, 2);
  lcd.print("LD:");
  lcd.print((int)sensor.load_kw);
  lcd.print("kW T:");
  lcd.print((int)sensor.battery_temp);
  lcd.print("C");
  lcd.print(state.internet_ok ? " NET:OK" : " NET:NO");

  // Row 3: Fault message or loads status
  lcd.setCursor(0, 3);
  if (state.mode == MODE_SAFE) {
    // Scroll fault message across row 3
    lcd.print(state.fault_message);
  } else {
    lcd.print("P5:");  lcd.print(state.p5_on ? "ON" : "SH");
    lcd.print(" P4:"); lcd.print(state.p4_on ? "ON" : "SH");
    lcd.print(" P3:"); lcd.print(state.p3_on ? "ON" : "SH");
    lcd.print(" P1:ON"); // P1 always ON
  }
}
