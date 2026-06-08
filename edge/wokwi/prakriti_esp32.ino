/*
 * Prakriti Energy AI — ESP32 Edge Controller (Wokwi simulation)
 * ----------------------------------------------------------------
 * - Connects to Wokwi-GUEST WiFi
 * - Simulates a hospital microgrid: solar curve, battery (Coulomb counting),
 *   4 circuits, ToD tariff, and autonomous grid-charge decision logic
 * - POSTs telemetry to the backend every 5s
 * - GETs relay commands every 10s and applies them
 * - Shows live status on a 128x64 SSD1306 OLED
 *
 * Libraries (Library Manager): ArduinoJson, Adafruit SSD1306, Adafruit GFX
 *
 * Relays:  GPIO25 solar | GPIO26 battery | GPIO27 grid | GPIO14 DG | GPIO33 grid-charge
 * OLED:    I2C SDA=21, SCL=22, addr 0x3C
 */

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// ── Config ──────────────────────────────────────────────────────
const char* WIFI_SSID = "Wokwi-GUEST";
const char* WIFI_PASS = "";
const char* BASE_URL  = "https://ai-energy-management-industrial-production.up.railway.app";
const char* SITE_ID   = "sim-hospital-01";

// ── Pins ────────────────────────────────────────────────────────
const int PIN_SOLAR       = 25;
const int PIN_BATTERY     = 26;
const int PIN_GRID        = 27;
const int PIN_DG          = 14;
const int PIN_GRID_CHARGE = 33;

// ── OLED ────────────────────────────────────────────────────────
#define SCREEN_W 128
#define SCREEN_H 64
Adafruit_SSD1306 display(SCREEN_W, SCREEN_H, &Wire, -1);

// ── Plant constants ─────────────────────────────────────────────
const float BATTERY_WH        = 5000.0;   // 5 kWh pack
const float SOLAR_PEAK_W      = 4000.0;   // 4 kW array
const float MAX_GRID_CHARGE_W = 1500.0;

// Circuits: name, rated watts, shed-below-SoC threshold (ICU never shed = -1)
struct Circuit { const char* name; float watts; float shedSoc; bool active; };
Circuit circuits[] = {
  { "ICU",     2800.0, -1.0, true },   // never shed
  { "HVAC",    3100.0, 20.0, true },   // shed below 20%
  { "Lights",   900.0, 15.0, true },   // shed below 15%
  { "General", 1300.0, 10.0, true },   // shed below 10%
};
const int N_CIRCUITS = 4;

// ── Simulation state ────────────────────────────────────────────
float soc          = 55.0;             // % state of charge
float simHour      = 22.5;             // start just before off-peak
const float SIM_HOURS_PER_SEC = 0.05;  // 1 real sec = 0.05 sim hour → full day in ~8 min
const float MAX_DSOC_PER_STEP = 1.5;   // clamp per-tick SoC change for a stable curve

// ── Relay command state (from dashboard) ────────────────────────
bool cmdGrid        = true;
bool cmdSolar       = true;
bool cmdBattery     = true;
bool cmdDg          = false;
bool cmdGridCharge  = false;           // grid-charge decision FROM THE CLOUD BRAIN

// Cloud link health — if the brain goes silent, edge falls back to local rules
bool cloudOnline           = false;
unsigned long lastCmdOkMs  = 0;
const unsigned long CLOUD_TIMEOUT_MS = 30000;  // 30s without a command = offline

// ── Live derived values (for OLED) ──────────────────────────────
float solarW = 0, loadW = 0, gridChargeW = 0;
String chargeSource = "none";
String tariffPeriod = "NORMAL";
float  tariffRs = 7.0;
bool   gridChargeActive = false;

// ── Timing ──────────────────────────────────────────────────────
unsigned long lastSim = 0, lastPost = 0, lastCmd = 0, lastOled = 0;

// ────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  pinMode(PIN_SOLAR, OUTPUT);
  pinMode(PIN_BATTERY, OUTPUT);
  pinMode(PIN_GRID, OUTPUT);
  pinMode(PIN_DG, OUTPUT);
  pinMode(PIN_GRID_CHARGE, OUTPUT);

  Wire.begin(21, 22);
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("SSD1306 init failed");
  }
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.println("Prakriti Energy AI");
  display.println("Booting...");
  display.display();

  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("WiFi");
  while (WiFi.status() != WL_CONNECTED) { delay(300); Serial.print("."); }
  Serial.println(" connected: " + WiFi.localIP().toString());
}

// ── Tariff by sim hour ──────────────────────────────────────────
void computeTariff(float h) {
  if (h >= 23.0 || h < 6.0)      { tariffPeriod = "OFF-PEAK"; tariffRs = 5.25; }
  else if (h >= 18.0 && h < 22.0){ tariffPeriod = "PEAK";     tariffRs = 9.50; }
  else                          { tariffPeriod = "NORMAL";   tariffRs = 7.00; }
}

// ── Grid-charge decision logic ──────────────────────────────────
bool decideGridCharge(float h, float socNow, float solarNow) {
  bool stop      = socNow >= 90.0;          // stop when full
  bool emergency = socNow < 15.0;           // emergency overrides tariff
  bool offPeak   = (h >= 23.0 || h < 6.0);  // 11pm–6am
  bool solarGood = solarNow > 500.0;        // free solar available → don't grid-charge
  if (stop) return false;
  if (emergency) return true;
  if (offPeak && !solarGood) return true;
  return false;
}

// ── Advance the simulation by dt sim-hours ──────────────────────
void stepSim(float dtSimH) {
  // Solar curve 6am–6pm
  if (cmdSolar && simHour >= 6.0 && simHour < 18.0) {
    solarW = SOLAR_PEAK_W * sin(PI * (simHour - 6.0) / 12.0);
    if (solarW < 0) solarW = 0;
  } else {
    solarW = 0;
  }

  // Circuit shedding by SoC
  loadW = 0;
  for (int i = 0; i < N_CIRCUITS; i++) {
    circuits[i].active = (circuits[i].shedSoc < 0) || (soc >= circuits[i].shedSoc);
    if (circuits[i].active) loadW += circuits[i].watts;
  }

  // ── Decision: CLOUD BRAIN decides; EDGE keeps safety reflexes + offline fallback ──
  if (millis() - lastCmdOkMs > CLOUD_TIMEOUT_MS) cloudOnline = false;

  bool localStop      = soc >= 90.0;   // hard safety: stop charging when full
  bool localEmergency = soc < 15.0;    // hard safety: must charge NOW
  bool decision;
  if (localStop)            decision = false;                                  // safety overrides everything
  else if (localEmergency)  decision = true;                                   // safety overrides everything
  else if (cloudOnline)     decision = cmdGridCharge;                          // obey the cloud brain
  else                      decision = decideGridCharge(simHour, soc, solarW); // brain offline → local rules

  gridChargeActive = cmdGrid && decision;
  gridChargeW = gridChargeActive ? MAX_GRID_CHARGE_W : 0.0;

  // Energy balance
  float surplus = max(0.0f, solarW - loadW);
  float deficit = max(0.0f, loadW - solarW);
  float chargeW = 0, dischargeW = 0;

  if (cmdSolar && surplus > 0 && soc < 100) chargeW += surplus;     // solar soak
  if (gridChargeActive)                     chargeW += gridChargeW; // grid charge

  if (deficit > 0) {
    if (cmdBattery && soc > 5.0)   dischargeW += deficit;  // battery covers
    // else grid/DG covers — no SoC change
  }

  // charge source label
  if (chargeW > 0) {
    if (surplus > 0 && gridChargeActive) chargeSource = "grid+solar";
    else if (gridChargeActive)           chargeSource = "grid";
    else                                 chargeSource = "solar";
  } else {
    chargeSource = "none";
  }

  // Coulomb counting (clamped for a smooth, stable curve)
  float dSoc = (chargeW - dischargeW) * dtSimH / BATTERY_WH * 100.0;
  if (dSoc >  MAX_DSOC_PER_STEP) dSoc =  MAX_DSOC_PER_STEP;
  if (dSoc < -MAX_DSOC_PER_STEP) dSoc = -MAX_DSOC_PER_STEP;
  soc += dSoc;
  if (soc > 100) soc = 100;
  if (soc < 0)   soc = 0;

  // Refresh circuit shed-state against the UPDATED SoC so telemetry is consistent
  loadW = 0;
  for (int i = 0; i < N_CIRCUITS; i++) {
    circuits[i].active = (circuits[i].shedSoc < 0) || (soc >= circuits[i].shedSoc);
    if (circuits[i].active) loadW += circuits[i].watts;
  }

  computeTariff(simHour);

  // Advance clock
  simHour += dtSimH;
  if (simHour >= 24.0) simHour -= 24.0;
}

// ── Apply relays to GPIO ────────────────────────────────────────
void applyRelays() {
  digitalWrite(PIN_SOLAR,       cmdSolar ? HIGH : LOW);
  digitalWrite(PIN_BATTERY,     cmdBattery ? HIGH : LOW);
  digitalWrite(PIN_GRID,        cmdGrid ? HIGH : LOW);
  digitalWrite(PIN_DG,          cmdDg ? HIGH : LOW);
  digitalWrite(PIN_GRID_CHARGE, gridChargeActive ? HIGH : LOW);
}

// ── POST telemetry ──────────────────────────────────────────────
void postTelemetry() {
  if (WiFi.status() != WL_CONNECTED) return;
  WiFiClientSecure client; client.setInsecure();
  HTTPClient https;
  String url = String(BASE_URL) + "/api/v1/ingest";
  if (!https.begin(client, url)) { Serial.println("begin failed"); return; }
  https.addHeader("Content-Type", "application/json");

  JsonDocument doc;
  doc["site_id"]            = SITE_ID;
  doc["ts"]                 = (long)(millis() / 1000);
  doc["soc_pct"]            = roundf(soc * 10) / 10.0;
  doc["solar_w"]            = roundf(solarW);
  doc["total_load_w"]       = roundf(loadW);
  doc["grid_charge_active"] = gridChargeActive;
  doc["grid_charge_w"]      = gridChargeW;
  doc["charge_source"]      = chargeSource;
  doc["tariff_period"]      = tariffPeriod;
  doc["tariff_rs_kwh"]      = tariffRs;
  doc["sim_hour"]           = roundf(simHour * 10) / 10.0;
  doc["grid_on"]            = cmdGrid;
  doc["battery_on"]         = cmdBattery;
  doc["solar_on"]           = cmdSolar;
  doc["dg_on"]              = cmdDg;
  JsonArray arr = doc["circuits"].to<JsonArray>();
  for (int i = 0; i < N_CIRCUITS; i++) {
    JsonObject c = arr.add<JsonObject>();
    c["name"]   = circuits[i].name;
    c["watts"]  = circuits[i].watts;
    c["active"] = circuits[i].active;
  }

  String body; serializeJson(doc, body);
  int code = https.POST(body);
  Serial.printf("POST /ingest -> %d\n", code);
  https.end();
}

// ── GET relay commands ──────────────────────────────────────────
void fetchCommands() {
  if (WiFi.status() != WL_CONNECTED) return;
  WiFiClientSecure client; client.setInsecure();
  HTTPClient https;
  String url = String(BASE_URL) + "/api/v1/commands/latest?site_id=" + SITE_ID;
  if (!https.begin(client, url)) return;
  int code = https.GET();
  if (code == 200) {
    String payload = https.getString();
    JsonDocument doc;
    if (!deserializeJson(doc, payload)) {
      cmdGrid       = doc["grid_relay"]        | true;
      cmdSolar      = doc["solar_relay"]       | true;
      cmdBattery    = doc["battery_relay"]     | true;
      cmdDg         = doc["dg_relay"]          | false;
      cmdGridCharge = doc["grid_charge_relay"] | false;
      cloudOnline   = true;                 // brain reachable
      lastCmdOkMs   = millis();
      Serial.printf("BRAIN cmd: grid=%d solar=%d batt=%d dg=%d gc=%d\n",
                    cmdGrid, cmdSolar, cmdBattery, cmdDg, cmdGridCharge);
    }
  }
  https.end();
}

// ── OLED ────────────────────────────────────────────────────────
void drawOled() {
  display.clearDisplay();
  display.setCursor(0, 0);
  display.printf("SoC %.0f%%  %.1fh\n", soc, simHour);
  display.printf("Src:%s\n", chargeSource.c_str());
  display.printf("Sol%4.0fW Ld%5.0fW\n", solarW, loadW);
  display.printf("%s Rs%.2f\n", tariffPeriod.c_str(), tariffRs);
  display.printf("G%d S%d B%d D%d C%d\n",
                 cmdGrid, cmdSolar, cmdBattery, cmdDg, gridChargeActive);
  const char* mode = (soc < 15.0) ? "EMERGENCY"
                   : (soc >= 90.0) ? "FULL/STOP"
                   : (cloudOnline ? "CLOUD-BRAIN" : "LOCAL-FALLBK");
  display.printf("Decide:%s", mode);
  display.display();
}

// ────────────────────────────────────────────────────────────────
void loop() {
  unsigned long now = millis();

  // Simulation step (every 200ms, scaled time)
  if (now - lastSim >= 200) {
    float dtSimH = (now - lastSim) / 1000.0 * SIM_HOURS_PER_SEC;
    lastSim = now;
    stepSim(dtSimH);
    applyRelays();
  }

  // OLED refresh (every 400ms)
  if (now - lastOled >= 400) { lastOled = now; drawOled(); }

  // POST telemetry every 5s
  if (now - lastPost >= 5000) { lastPost = now; postTelemetry(); }

  // GET commands every 10s
  if (now - lastCmd >= 10000) { lastCmd = now; fetchCommands(); }
}
