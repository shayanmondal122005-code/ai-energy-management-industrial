/**
 * MicroGrid AI — ESP8266 WiFi Bridge
 * Flash this to a separate ESP8266 (NodeMCU / Wemos D1 Mini)
 *
 * WHAT THIS DOES:
 *   - Sits between Arduino Mega and your cloud backend
 *   - Receives JSON from Arduino via Serial (9600 baud)
 *   - POSTs it to your Railway backend /ingest endpoint
 *   - Receives cloud commands and forwards to Arduino
 *   - Reconnects WiFi automatically if connection drops
 *   - Buffers up to 96 readings in RAM when offline
 *   - Flushes buffer to cloud when internet returns
 *
 * WIRING:
 *   ESP8266 TX → Arduino Mega RX1 (D19)
 *   ESP8266 RX → Arduino Mega TX1 (D18)
 *   Both share GND
 *   ESP8266 powered from 3.3V (separate regulator — not Arduino 3.3V pin)
 *
 * EDIT THESE before flashing:
 */

#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClient.h>
#include <ArduinoJson.h>

// ── EDIT THESE ────────────────────────────────────────────────
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* BACKEND_URL   = "https://your-app.railway.app";
const char* FACILITY_ID   = "00000000-0000-0000-0000-000000000010";
const char* API_KEY       = "your-iot-gateway-api-key";
// ─────────────────────────────────────────────────────────────

// Offline buffer — stores readings when internet is cut
const int BUFFER_SIZE = 96;  // 96 × 15s = 24 hours of data
String    buffer[BUFFER_SIZE];
int       buf_head = 0;
int       buf_tail = 0;
int       buf_count= 0;

// Timing
unsigned long lastWifiCheck = 0;
unsigned long lastCommandPoll = 0;

void setup() {
  Serial.begin(9600);  // to/from Arduino Mega
  connectWiFi();
}

void loop() {
  // Read from Arduino
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();

    if (line.startsWith("SEND:")) {
      String json = line.substring(5);
      handleReading(json);
    }
  }

  // Reconnect WiFi if lost
  if (millis() - lastWifiCheck > 10000) {
    lastWifiCheck = millis();
    if (WiFi.status() != WL_CONNECTED) {
      connectWiFi();
    }
  }

  // Flush offline buffer when internet returns
  if (WiFi.status() == WL_CONNECTED && buf_count > 0) {
    flushBuffer();
  }

  // Poll cloud for commands every 30 seconds
  if (millis() - lastCommandPoll > 30000 && WiFi.status() == WL_CONNECTED) {
    lastCommandPoll = millis();
    pollCommands();
  }
}

void handleReading(String json) {
  if (WiFi.status() == WL_CONNECTED) {
    bool sent = postToCloud(json);
    if (sent) {
      Serial.println("OK");  // tells Arduino: internet is working
    } else {
      bufferReading(json);
      Serial.println("BUFFERED");
    }
  } else {
    bufferReading(json);
    // No response = Arduino detects offline
  }
}

bool postToCloud(String json) {
  WiFiClientSecure client;
  client.setInsecure(); // for dev — use proper cert in production
  HTTPClient http;

  String url = String(BACKEND_URL) + "/facilities/" + FACILITY_ID + "/ingest";
  http.begin(client, url);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Authorization", "Bearer " + String(API_KEY));
  http.setTimeout(8000);

  int code = http.POST(json);
  http.end();

  return (code == 200 || code == 201);
}

void bufferReading(String json) {
  if (buf_count >= BUFFER_SIZE) {
    // Buffer full — drop oldest reading
    buf_head = (buf_head + 1) % BUFFER_SIZE;
    buf_count--;
  }
  buffer[buf_tail] = json;
  buf_tail = (buf_tail + 1) % BUFFER_SIZE;
  buf_count++;
}

void flushBuffer() {
  int flushed = 0;
  while (buf_count > 0 && flushed < 10) { // flush max 10 per cycle
    String json = buffer[buf_head];
    if (postToCloud(json)) {
      buf_head = (buf_head + 1) % BUFFER_SIZE;
      buf_count--;
      flushed++;
    } else {
      break; // still offline
    }
    delay(200);
  }
  if (flushed > 0) {
    Serial.println("FLUSH:" + String(flushed) + " buffered readings sent");
  }
}

void pollCommands() {
  WiFiClientSecure client;
  client.setInsecure();
  HTTPClient http;

  String url = String(BACKEND_URL) + "/facilities/" + FACILITY_ID + "/grid/state";
  http.begin(client, url);
  http.addHeader("Authorization", "Bearer " + String(API_KEY));
  http.setTimeout(5000);

  int code = http.GET();
  if (code == 200) {
    String body = http.getString();
    DynamicJsonDocument doc(512);
    deserializeJson(doc, body);

    String battery_cmd = doc["battery_command"].as<String>();

    // Forward command to Arduino
    if (battery_cmd == "CHARGE")    Serial.println("CMD:CHARGE");
    if (battery_cmd == "DISCHARGE") Serial.println("CMD:DISCHARGE");
    if (battery_cmd == "HOLD")      Serial.println("CMD:HOLD");
  }
  http.end();
}

void connectWiFi() {
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    attempts++;
  }
  // No blocking — if WiFi fails, Arduino runs offline mode
}
