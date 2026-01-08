/*
 * Copyright (C) 2026 eddie772tw
 * This file is part of motoPlayer.
 * motoPlayer is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 */

#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <ESP8266mDNS.h>
#include <ESPAsyncTCP.h>
#include <ESPAsyncWebServer.h>
#include <ElegantOTA.h>
#include <Wire.h> 

// =================================================================
// --- 常數與腳位定義 (Constants and Pin Definitions) ---
// =================================================================

// -- 硬體腳位 --
#define UNO_SDA     D2
#define UNO_SCL     D1
#define LED_G_PIN   D4
#define LED_B_PIN   D0

// -- 常數定義 --
const uint8_t UNO_I2C_ADDRESS = 8; // Arduino 的 I2C 位址
const uint16_t I2C_CHECK_INTERVAL_MS = 500; // 每 0.5 秒檢查一次 UNO
const unsigned long TEMP_READ_INTERVAL_MS = 2500;
const char* STA_SSID = "motoplayer";
const char* STA_PASSWORD = "password12345";
const char* STA_SSID2 = "C80";
const char* STA_PASSWORD2 = "eddie772tw";
const unsigned long WIFI_TIMEOUT_MS = 15000;
const char* MDNS_HOSTNAME = "motoplayer";


// =================================================================
// --- 全域變數 (Global Variables) ---
// =================================================================

AsyncWebServer server(80);

// -- 斷線重連機制變數 --
unsigned long lastWifiCheckMillis = 0;
const uint16_t WIFI_RECONNECT_INTERVAL_MS = 10000; // 每 10 秒檢查一次

// -- I2C 變數 --
bool isUnoOnline = false; // UNO 是否在線的旗標
unsigned long lastI2CCheckMillis = 0; // 上次檢查 I2C 的時間
String lastRfidFromUno = "N/A"; 

// -- 非阻塞式閃爍功能所需變數 --
bool isBlinking = false;
char blinkPin = ' ';
uint16_t blinkInterval = 0;
unsigned long previousBlinkMillis = 0;
uint8_t blinkLedState = HIGH;

// -- 環境感測器變數 --
float currentTemperature = -999.0;
float currentHumidity = 0.0;
unsigned long lastSensorReadMillis = 0;
int lightLevel = 0;

// -- IP位置 --
IPAddress local_IP(192, 168, 9, 2);
IPAddress gateway(192, 168, 9, 1);
IPAddress subnet(255, 255, 255, 0);

// =================================================================
// --- 函式宣告 (Functions Declaration) ---
// =================================================================

void setLED(char pin, uint8_t status);
void setSolidLEDColor(bool g, bool b); 
void startBlinkingLED(char pin, uint16_t ms);
void handleBlink();
void setupWebServer();
void handleI2CCommunication(); 
void playTrack(byte trackNumber);
void chgVol(char vol);
void handleWiFiReconnect();

// =================================================================
// --- 主要執行函式 (Main Functions) ---
// =================================================================

void setup() {
  // 1. 初始化硬體
  pinMode(LED_G_PIN, OUTPUT);
  pinMode(LED_B_PIN, OUTPUT);
  Serial.begin(115200);
  Serial.println("\n\n--- MotoNodeMCU System Booting (I2C Master Mode) ---");
  setSolidLEDColor(false, false); // 初始化LED (全滅)

  // 2. 初始化I2C與DFPlayer
  Wire.begin(UNO_SDA, UNO_SCL); 
  while (!isUnoOnline) handleI2CCommunication();
  Serial.println("I2C Master Initialized.");
  playTrack(1);

  // 3. 初始化網路
  WiFi.begin(STA_SSID, STA_PASSWORD);
  WiFi.config(local_IP, gateway, subnet);
  //WiFi.setSleepMode(WIFI_MODEM_SLEEP);
  Serial.print("Connecting to STA...");
  startBlinkingLED('G', 300); 
  unsigned long wifi_start_time = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - wifi_start_time < WIFI_TIMEOUT_MS) {
    handleBlink();
    delay(100);
  }
  isBlinking = false;

  // 4. 初始化網路服務
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("Connected!");
    Serial.print("IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("Failed (Timeout).");
  }
  if (MDNS.begin(MDNS_HOSTNAME)) {
      Serial.print("mDNS responder started: http://");
      Serial.print(MDNS_HOSTNAME);
      Serial.println(".local");
  }

  // 5. 設定並啟動 Web Server
  setupWebServer();

  setSolidLEDColor(false, false);
  Serial.println("--- Setup Complete ---");
}

void loop() {
  // --- 持續處理非阻塞任務 ---
  ElegantOTA.loop();
  MDNS.update();
  handleBlink();
  handleI2CCommunication();
  handleWiFiReconnect(); 
}

// =================================================================
// --- 輔助函式實作 (Helper Function Implementations) ---
// =================================================================

// 處理WIFI斷線重連機制
void handleWiFiReconnect() {
  if (millis() - lastWifiCheckMillis >= WIFI_RECONNECT_INTERVAL_MS) {
    lastWifiCheckMillis = millis();
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("Wi-Fi Disconnected. Reconnecting...");
      WiFi.reconnect();
    }
  }
}

// 處理與 Arduino UNO 的 I2C 通訊
void handleI2CCommunication() {
  if (millis() - lastI2CCheckMillis >= I2C_CHECK_INTERVAL_MS) {
    lastI2CCheckMillis = millis();
    byte error = Wire.requestFrom(UNO_I2C_ADDRESS, (uint8_t)10); // 請求固定的 10 個位元組
    if (error == 10) { // 必須收到完整的 10 個位元組
      if (!isUnoOnline) {
        Serial.println("I2C: Online.");
      }
      isUnoOnline = true;
      // 建立一個緩衝區來接收封包
      byte packetBuffer[10];
      Wire.readBytes(packetBuffer, 10);
      byte statusFlag = packetBuffer[0];
      String uidString = "";
      if (statusFlag == 0x00) return;
      switch (statusFlag) {
        case 0x01:
          for (int i = 1; i < 5; i++) {
            uidString += (packetBuffer[i] < 0x10 ? "0" : "");
            uidString += String(packetBuffer[i], HEX);
          }
          uidString.toUpperCase();
          lastRfidFromUno = uidString;
          Serial.print(">>> Received RFID: ");
          Serial.println(lastRfidFromUno);
          break;
        case 0x02:
          {// 讀取數據
          float temp_f = ((packetBuffer[1] << 8) | packetBuffer[2]) / 10.0; // 溫度
          int humid_f = (float)packetBuffer[3]; //濕度
          int light_i = (int)((packetBuffer[4] << 8) | packetBuffer[5]);  //光照

          // 更新對應的全域變數
          currentTemperature = temp_f;
          currentHumidity = humid_f;
          lightLevel = light_i;

          Serial.print(">>> Received ENV:");
          Serial.print("  Temp: "); Serial.print(temp_f);
          Serial.print("°C, Humid: "); Serial.print(humid_f);
          Serial.print("%, Light: "); Serial.println(light_i);}
          break;
        default:
          Serial.println(">>> Received Preserved CMD, please update NodeMCU Code.");
          break;
      }
      setLED('B', HIGH);
      delay(10);
      setLED('B', LOW);
    } else { // 如果通訊失敗或收到的位元組數不對
      if (isUnoOnline) {
        Serial.print("I2C: Connection lost, response bytes: ");
        Serial.println(error);
      }
      isUnoOnline = false;
      lastRfidFromUno = "N/A";
    }
  }
}

// 處理DFPlayer Mini的指令
void playTrack(byte trackNumber) {
  if (!isUnoOnline) return; // 如果 UNO 不在線，直接返回
  Wire.beginTransmission(UNO_I2C_ADDRESS);
  Serial.print("<<< Send CMD: Play track");
  Serial.println(trackNumber);
  Wire.write('P');           // 發送 'P' 指令
  Wire.write(trackNumber);   // 發送曲目編號
  Wire.endTransmission();
  setLED('G', HIGH);
  delay(10);
  setLED('G', LOW);
}

// 改變DFPlayerMini的音量
void chgVol(char vol){
  if (!isUnoOnline) return; // 如果 UNO 不在線，直接返回
  Wire.beginTransmission(UNO_I2C_ADDRESS);
  Serial.print("<<< Send CMD: Volume");
  Serial.println(vol);
  switch (vol)  {
  case '+':
    Wire.write('+');
    break;
  case '-':
    Wire.write('-');
    break;
  default:
    break;
  }
  Wire.endTransmission();
  setLED('G', HIGH);
  delay(10);
  setLED('G', LOW);
}

String getNavFooterHTML() {
  String footer = "<hr style='margin-top: 50px;'>";
  footer += "<p>";
  footer += "<a href='/'>[首頁]</a> | ";
  footer += "<a href='/debug'>[測試頁面]</a> | ";
  footer += "<a href='/sensor'>[即時數據]</a> | ";
  footer += "<a href='/update'>[ElegantOTA]</a>";
  footer += "</p>";
  return footer;
}

void setupWebServer() {
  server.on("/", HTTP_GET, [](AsyncWebServerRequest *request){
    String html = "<h1>MotoNodeMCU Control Panel</h1>";
    html += "<p>Access me at <a href='http://" + String(MDNS_HOSTNAME) + ".local'>http://" + String(MDNS_HOSTNAME) + ".local</a></p>";
    html += "<h3>STA IP: " + WiFi.localIP().toString() + "</h3>";
    html += "<h3>STA MAC: " + WiFi.macAddress() + "</h3>";
    String unoStatus = isUnoOnline ? "<span style='color: green;'>Online</span>" : "<span style='color: red;'>Offline</span>";
    html += "<h3>UNO Module: " + unoStatus + "</h3>";
    html += "<h3>Last RFID Scanned: " + lastRfidFromUno + "</h3>";
    html += "<h3>Device Temp: " + String(currentTemperature, 1) + " &deg;C</h3>";
    html += "<h3>Device Humidity: " + String(currentHumidity, 1) + " &#x25;</h3>";
    html += "<h3>Device Light: " + String(lightLevel) + "</h3>";
    html += getNavFooterHTML();
    request->send(200, "text/html; charset=UTF-8", html);
  });

  server.on("/debug", HTTP_GET, [](AsyncWebServerRequest *request){
    String html = "<h1>Debug & Test Page</h1>";
    html += "<h3>DFPlayer Control</h3>";
    html += "播放第 <input type='number' id='trackNum' value='1' min='1' style='width: 50px;'> 首: ";
    html += "<button onclick=\"playSpecificTrack()\">Play</button><br>";
    html += "<button onclick=\"sendCmd('vol_up')\">Volume +</button> ";
    html += "<button onclick=\"sendCmd('vol_down')\">Volume -</button>";
    html += "<h3>LED Control (Green / Blue)</h3>";
    html += "<button onclick=\"sendCmd('blink_g')\">Blink Green</button> ";
    html += "<button onclick=\"sendCmd('blink_b')\">Blink Blue</button> ";
    html += "<button onclick=\"sendCmd('stop_blink')\">Stop Blink</button><br>";
    html += "<button onclick=\"sendCmd('on_g')\">Green On</button> ";
    html += "<button onclick=\"sendCmd('on_b')\">Blue On</button><br>";
    html += "<button onclick=\"sendCmd('off_g')\">Green Off</button> ";
    html += "<button onclick=\"sendCmd('off_b')\">Blue Off</button>";
    html += "<h3>System</h3>";
    html += "<button onclick=\"if(confirm('你確定嗎？')) sendCmd('restart')\">Restart Device</button>";
    
    html += "<script>";
    html += "function sendCmd(cmd) { fetch('/api/' + cmd).then(response => console.log(cmd + ' sent.')); }";
    html += "function playSpecificTrack() {";
    html += "  var trackId = document.getElementById('trackNum').value;";
    html += "  if (trackId) { fetch('/api/play?track=' + trackId).then(response => console.log('Play track ' + trackId + ' command sent.')); }";
    html += "}";
    html += "</script>";

    html += getNavFooterHTML();
    request->send(200, "text/html; charset=UTF-8", html);
  });
  
  server.on("/sensor", HTTP_GET, [](AsyncWebServerRequest *request){
    String html = "<h1>傳感器即時數據</h1>";
    html += "<p>更新週期: 2.5秒</p>";
    html += "<h2 style='font-size: 2em;'>UNO: <span id='UNO' style='color: #4b4b4b;'>--</span></h2>";
    html += "<h2 style='font-size: 2em;'>溫度: <span id='temp' style='color: #E67E22;'>--</span> &deg;C</h2>";
    html += "<h2 style='font-size: 2em;'>濕度: <span id='humid' style='color: #3498DB;'>--</span> &#x25;</h2>";
    html += "<h2 style='font-size: 2em;'>日照: <span id='light' style='color: #F1C40F;'>--</span></h2>";
    html += "<h2 style='font-size: 2em;'>卡號: <span id='card' style='color: #7F4448;'>--</span></h2>";
    html += "<script>";
    html += "function updateSensorData() {";
    html += "  fetch('/api/sensors').then(response => response.json())";
    html += "    .then(data => {";
    html += "      document.getElementById('UNO').innerText = data.UNO;";
    html += "      document.getElementById('UNO').style.color = (data.UNO == 'Online') ? '#2ECC71' : '#E74C3C';";
    html += "      document.getElementById('temp').innerText = data.temperature.toFixed(1);";
    html += "      document.getElementById('humid').innerText = data.humidity.toFixed(1);";
    html += "      document.getElementById('light').innerText = data.light;";
    html += "      document.getElementById('card').innerText = data.card;";
    html += "    }).catch(error => console.error('Error fetching sensor data:', error));";
    html += "}";
    html += "window.onload = function() { updateSensorData(); setInterval(updateSensorData, 2500); };";
    html += "</script>";

    html += getNavFooterHTML();
    request->send(200, "text/html; charset=UTF-8", html);
  });

  server.on("/api/sensors", HTTP_GET, [](AsyncWebServerRequest *request){
    String unoStatus = isUnoOnline ? "Online":"Offline";
    String json = "{";
    json += "\"temperature\":" + String(currentTemperature, 1) + ",";
    json += "\"humidity\":" + String(currentHumidity, 1) + ",";
    json += "\"light\":" + String(lightLevel) + ",";
    json += "\"card\":\"" + String(lastRfidFromUno) + "\",";
    json += "\"UNO\":\"" + String(unoStatus) + "\"";
    json += "}";
    request->send(200, "application/json", json);
  });
  server.on("/api/play", HTTP_GET, [](AsyncWebServerRequest *request){
    // 檢查 URL 中是否存在名為 'track' 的參數
    if (request->hasParam("track")) {
      // 獲取 'track' 參數的值
      String trackValue = request->getParam("track")->value();
      // 將字串轉換為整數
      int trackId = trackValue.toInt();
      
      if (trackId > 0) {
        // 呼叫我們之前建立的 I2C 指令函式
        playTrack(trackId);
        String responseMessage = "Play command for track " + String(trackId) + " sent to UNO.";
        request->send(200, "text/plain", responseMessage);
      } else {
        request->send(400, "text/plain", "Invalid track number.");
      }
    } else {
      request->send(400, "text/plain", "Missing 'track' parameter.");
    }
  });
  server.on("/api/vol_up", HTTP_GET, [](AsyncWebServerRequest *request){ chgVol('+'); request->send(200); });
  server.on("/api/vol_down", HTTP_GET, [](AsyncWebServerRequest *request){ chgVol('-'); request->send(200); });
  server.on("/api/blink_g", HTTP_GET, [](AsyncWebServerRequest *request){ startBlinkingLED('G', 250); request->send(200); });
  server.on("/api/blink_b", HTTP_GET, [](AsyncWebServerRequest *request){ startBlinkingLED('B', 250); request->send(200); });
  server.on("/api/on_g", HTTP_GET, [](AsyncWebServerRequest *request){ setLED('G', HIGH); request->send(200); });
  server.on("/api/on_b", HTTP_GET, [](AsyncWebServerRequest *request){ setLED('B', HIGH); request->send(200); });
  server.on("/api/off_g", HTTP_GET, [](AsyncWebServerRequest *request){ setLED('G', LOW); request->send(200); });
  server.on("/api/off_b", HTTP_GET, [](AsyncWebServerRequest *request){ setLED('B', LOW); request->send(200); });
  server.on("/api/stop_blink", HTTP_GET, [](AsyncWebServerRequest *request){ isBlinking = false; setSolidLEDColor(false, false); request->send(200); });
  server.on("/api/restart", HTTP_GET, [](AsyncWebServerRequest *request){ 
    request->send(200, "text/plain; charset=UTF-8", "Restarting..."); 
    delay(200); 
    ESP.restart(); 
  });

  ElegantOTA.begin(&server);
  server.begin();
  Serial.println("Web Server and OTA are running.");
}

void setLED(char pin, uint8_t status) {
  isBlinking = false;
  uint8_t output = (status == HIGH) ? LOW : HIGH;
  switch (pin) {
    case 'G': case 'g': digitalWrite(LED_G_PIN, output); break;
    case 'B': case 'b': digitalWrite(LED_B_PIN, output); break;
    case 'A': case 'a':
      digitalWrite(LED_G_PIN, output);
      digitalWrite(LED_B_PIN, output);
      break;
  }
}

void setSolidLEDColor(bool g, bool b) {
  isBlinking = false;
  digitalWrite(LED_G_PIN, g ? LOW : HIGH);
  digitalWrite(LED_B_PIN, b ? LOW : HIGH);
}

void startBlinkingLED(char pin, uint16_t ms) {
  isBlinking = true;
  blinkPin = pin;
  blinkInterval = ms;
  previousBlinkMillis = 0;
  blinkLedState = HIGH;
}

void handleBlink() {
  if (!isBlinking) return;
  unsigned long currentMillis = millis();
  if (currentMillis - previousBlinkMillis >= blinkInterval) {
    previousBlinkMillis = currentMillis;
    blinkLedState = !blinkLedState;
    switch (blinkPin) {
        case 'G': case 'g': digitalWrite(LED_G_PIN, blinkLedState); break;
        case 'B': case 'b': digitalWrite(LED_B_PIN, blinkLedState); break;
        case 'A': case 'a':
            digitalWrite(LED_G_PIN, blinkLedState);
            digitalWrite(LED_B_PIN, blinkLedState);
            break;
    }
  }
}