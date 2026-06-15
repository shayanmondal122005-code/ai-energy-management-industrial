/*
 * MicroGrid AI — ESP32 meter gateway (BRING-UP firmware)
 * ------------------------------------------------------------------
 * Purpose: prove the ESP32 talks to the production backend over your
 * real WiFi BEFORE the smart meter is wired. It posts a reading every
 * POST_EVERY_MS using a placeholder load value.
 *
 * When the Selec MFM384 arrives, replace readMeterLoadWatts() with the
 * real Modbus read (see the TODO block). NOTHING ELSE in this file
 * changes — WiFi, auth, posting, retry and the watchdog stay the same.
 *
 * Libraries (Arduino IDE → Library Manager): ArduinoJson.
 * Board: any ESP32 dev board (esp32 by Espressif).
 *
 * ── One-time setup before flashing ──
 *  1. Set WIFI_SSID / WIFI_PASS to your network.
 *  2. Mint a device key for this site (admin JWT required):
 *       POST https://<backend>/api/v1/devices   body: {"site_id":"<SITE_ID>","label":"meter-1"}
 *     Copy the returned dk_..._... into DEVICE_KEY. It is shown ONCE.
 *  3. Set SITE_ID to the same site_id you minted the key for.
 *  4. Flash, open Serial Monitor @115200, watch for "POST /ingest -> 200".
 *  5. Verify server-side:  GET /api/v1/telemetry/latest?site_id=<SITE_ID>
 */

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// ── Config — FILL THESE IN ──────────────────────────────────────
const char* WIFI_SSID  = "YOUR_WIFI_NAME";
const char* WIFI_PASS  = "YOUR_WIFI_PASSWORD";
const char* BASE_URL   = "https://ai-energy-management-industrial-production.up.railway.app";
const char* SITE_ID    = "sim-hospital-01";                 // the site this device belongs to
const char* DEVICE_KEY = "dk_REPLACE_WITH_YOUR_MINTED_KEY"; // from POST /api/v1/devices

// ── Timing ──────────────────────────────────────────────────────
const unsigned long POST_EVERY_MS = 10000;   // post every 10 s during bring-up

unsigned long lastPost = 0;

// ────────────────────────────────────────────────────────────────
// PLACEHOLDER until the MFM384 is wired. Returns a fake load so we can
// confirm the cloud link. Replace the body with the Modbus read below.
//
// TODO (when the meter is connected):
//   #include <ModbusMaster.h>  + a MAX485 on Serial2 (GPIO16/17, DE/RE GPIO4)
//   ModbusMaster meter; meter.begin(1, Serial2);   // slave id 1, 9600 8N1
//   read input registers (FC04), IEEE-754 float, high word first:
//     total kW @ reg 42 -> return kW * 1000.0;     // watts
//   See the meter install sheet for the full register map.
float readMeterLoadWatts() {
  // Smooth fake curve around 300 kW so the dashboard shows life during bring-up.
  float t = millis() / 1000.0;
  return 300000.0 + 40000.0 * sin(t / 30.0);   // ~260–340 kW, in watts
}

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
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println(" ok: " + WiFi.localIP().toString());
    return true;
  }
  Serial.println(" FAILED");
  return false;
}

void postReading(float loadW) {
  if (!connectWiFi()) return;

  WiFiClientSecure client;
  client.setInsecure();                  // Railway uses a valid cert; pin later if needed
  HTTPClient https;
  String url = String(BASE_URL) + "/api/v1/ingest";
  if (!https.begin(client, url)) { Serial.println("https.begin failed"); return; }
  https.addHeader("Content-Type", "application/json");
  https.addHeader("Authorization", String("Bearer ") + DEVICE_KEY);

  // SimTelemetry shape the backend expects. For a meter-only bring-up we send
  // real load; battery/solar are 0 (no such hardware yet).
  JsonDocument doc;
  doc["site_id"]      = SITE_ID;
  doc["ts"]           = (long)(millis() / 1000);
  doc["soc_pct"]      = 0;
  doc["solar_w"]      = 0;
  doc["total_load_w"] = roundf(loadW);
  doc["grid_on"]      = true;
  doc["battery_on"]   = false;
  doc["solar_on"]     = false;
  doc["dg_on"]        = false;

  String body; serializeJson(doc, body);
  int code = https.POST(body);
  if (code > 0) Serial.printf("POST /ingest -> %d  (load %.0f W)\n", code, loadW);
  else          Serial.printf("POST failed: %s\n", https.errorToString(code).c_str());
  https.end();
}

// ────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\nMicroGrid AI — ESP32 meter bring-up");
  connectWiFi();
}

void loop() {
  unsigned long now = millis();
  if (now - lastPost >= POST_EVERY_MS) {
    lastPost = now;
    postReading(readMeterLoadWatts());
  }
  delay(50);
}
