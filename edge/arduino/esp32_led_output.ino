/*
 * MicroGrid AI — ESP32 LED output (relay stand-in)
 * ------------------------------------------------------------------
 * Pairs with laptop_feeder.py. The laptop feeds telemetry; the cloud
 * brain decides; THIS ESP32 polls that decision and shows it on an LED:
 *
 *     CHARGING  (grid_charge_relay) -> LED solid ON
 *     DISCHARGING (battery_discharge) -> LED blinking
 *     idle                            -> LED off
 *
 * It only READS commands — no control, no telemetry. When you later add
 * a real relay/contactor, drive it from the same `charging`/`discharging`
 * flags instead of (or alongside) the LED.
 *
 * Library: ArduinoJson.  Board: any ESP32 dev board.
 * LED: GPIO2 is the onboard LED on most ESP32 devkits. For an external
 * LED use any GPIO -> 220Ω -> LED -> GND and set LED_PIN to that pin.
 */

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// ── Config — FILL THESE IN (match laptop_feeder.py) ─────────────
const char* WIFI_SSID  = "YOUR_WIFI_NAME";
const char* WIFI_PASS  = "YOUR_WIFI_PASSWORD";
const char* BASE_URL   = "https://ai-energy-management-industrial-production.up.railway.app";
const char* SITE_ID    = "sim-hospital-01";
const char* DEVICE_KEY = "dk_REPLACE_WITH_YOUR_MINTED_KEY";

const int LED_PIN = 2;                  // onboard LED on most ESP32 devkits

const unsigned long POLL_EVERY_MS  = 2000;   // ask the brain every 2 s
const unsigned long BLINK_EVERY_MS = 250;    // discharge blink rate

// ── State ───────────────────────────────────────────────────────
bool charging = false, discharging = false;
unsigned long lastPoll = 0, lastBlink = 0;
bool blinkOn = false;

// ────────────────────────────────────────────────────────────────
bool connectWiFi(unsigned long timeoutMs = 20000) {
  if (WiFi.status() == WL_CONNECTED) return true;
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("WiFi connecting");
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < timeoutMs) {
    delay(300); Serial.print(".");
  }
  bool ok = WiFi.status() == WL_CONNECTED;
  Serial.println(ok ? (" ok: " + WiFi.localIP().toString()) : " FAILED");
  return ok;
}

void pollCommands() {
  if (!connectWiFi()) return;
  WiFiClientSecure client; client.setInsecure();
  HTTPClient https;
  String url = String(BASE_URL) + "/api/v1/commands/latest?site_id=" + SITE_ID;
  if (!https.begin(client, url)) { Serial.println("https.begin failed"); return; }
  https.addHeader("Authorization", String("Bearer ") + DEVICE_KEY);

  int code = https.GET();
  if (code == 200) {
    JsonDocument doc;
    if (!deserializeJson(doc, https.getString())) {
      charging    = doc["grid_charge_relay"] | false;
      discharging = doc["battery_discharge"] | false;
      Serial.printf("brain: charge=%d discharge=%d\n", charging, discharging);
    }
  } else {
    Serial.printf("GET /commands -> %d\n", code);
  }
  https.end();
}

void driveLed() {
  if (charging) {
    digitalWrite(LED_PIN, HIGH);                 // solid = charging
  } else if (discharging) {
    if (millis() - lastBlink >= BLINK_EVERY_MS) {
      lastBlink = millis();
      blinkOn = !blinkOn;
      digitalWrite(LED_PIN, blinkOn ? HIGH : LOW);  // blink = discharging
    }
  } else {
    digitalWrite(LED_PIN, LOW);                  // off = idle
  }
}

// ────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(200);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  Serial.println("\nMicroGrid AI — ESP32 LED output");
  connectWiFi();
}

void loop() {
  unsigned long now = millis();
  if (now - lastPoll >= POLL_EVERY_MS) {
    lastPoll = now;
    pollCommands();
  }
  driveLed();
  delay(10);
}
