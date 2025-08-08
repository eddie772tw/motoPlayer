#include <Arduino.h>
#include <SPI.h>
#include <MFRC522.h>
#include <Wire.h>
#include <DHT.h>
#include <SoftwareSerial.h> 
#include <DFRobotDFPlayerMini.h> 

// =================================================================
// --- 常數與腳位定義 ---
// =================================================================

// -- RC522 --
#define RC522_SS_PIN   10
#define RC522_RST_PIN  9
// -- 環境感測器 --
#define DHT_PIN    7
#define LDR_PIN    A0
#define DHT_TYPE   DHT11
// -- DFPlayer --
#define DFP_RX_PIN 2 // 連接到 DFPlayer 的 TX
#define DFP_TX_PIN 3 // 連接到 DFPlayer 的 RX

// -- I2C --
#define I2C_SLAVE_ADDRESS 8
#define I2C_PACKET_SIZE   10
#define FLAG_IDLE         0x00
#define FLAG_RFID_NEW     0x01
#define FLAG_ENV_NEW      0x02

// =================================================================
// --- 全域變數 ---
// =================================================================

MFRC522 mfrc522(RC522_SS_PIN, RC522_RST_PIN);
DHT dht(DHT_PIN, DHT_TYPE);

SoftwareSerial dfpSerial(DFP_RX_PIN, DFP_TX_PIN); // RX, TX
DFRobotDFPlayerMini myDFPlayer;

volatile bool newCardDataAvailable = false;
volatile bool newENVDataAvailable = false;
volatile bool IsCMD = false;
volatile char command_to_run = 0;
volatile byte command_param = 0;
byte payload[I2C_PACKET_SIZE]; 

// --- 計時器變數 ---
unsigned long lastRfidCheckMillis = 0;
unsigned long lastENVCheckMillis = 0;
const uint16_t RFID_CHECK_INTERVAL_MS = 200;
const uint16_t ENV_CHECK_INTERVAL_MS = 2500;

// =================================================================
// --- 函式宣告 ---
// =================================================================
void requestEvent();
void receiveEvent(int howMany);
void handleRFID();
void handleENVSensor();
void handleCommands();

// =================================================================
// --- 主要執行函式 ---
// =================================================================

void setup() {
  Serial.begin(9600);
  dfpSerial.begin(9600);
  SPI.begin();
  Wire.begin(I2C_SLAVE_ADDRESS);
  Wire.onRequest(requestEvent);
  Wire.onReceive(receiveEvent);
  
  mfrc522.PCD_Init();
  dht.begin();
  
  Serial.println(F("UNO I2C Slave is online. All peripherals activated."));

  Serial.print(F("Initializing DFPlayer... "));
  if (!myDFPlayer.begin(dfpSerial)) {
    Serial.println(F("Unable to begin DFPlayer. Check connections."));
  } else {
    Serial.println(F("DFPlayer Mini online."));
    myDFPlayer.volume(30);
    //myDFPlayer.play(1);
  }
}

void loop() {
  handleRFID();
  handleENVSensor();
  handleCommands();
}

// =================================================================
// --- 輔助函式實作 ---
// =================================================================

void handleRFID() {
  if (millis() - lastRfidCheckMillis < RFID_CHECK_INTERVAL_MS) return;
  lastRfidCheckMillis = millis();
  if (newCardDataAvailable) return;
  if (mfrc522.PICC_IsNewCardPresent() && mfrc522.PICC_ReadCardSerial()) {
    if (mfrc522.uid.size > 0) {
      payload[0] = FLAG_RFID_NEW; 
      String uidString = "";
      for (byte i = 0; i < I2C_PACKET_SIZE - 1; i++) {
        if (i < mfrc522.uid.size) {
          payload[i + 1] = mfrc522.uid.uidByte[i];
          uidString += (mfrc522.uid.uidByte[i] < 0x10 ? "0" : "");
          uidString += String(mfrc522.uid.uidByte[i], HEX);
        } else {
          payload[i + 1] = 0; 
        }
      }
      uidString.toUpperCase();
      Serial.print(F("Card Detected! UID: "));
      Serial.println(uidString);
      newCardDataAvailable = true;
    }
    mfrc522.PICC_HaltA();
  }
}

void handleENVSensor() {
  if (millis() - lastENVCheckMillis < ENV_CHECK_INTERVAL_MS) return;
  lastENVCheckMillis = millis();
  if (newENVDataAvailable) return;
  float temp_f = dht.readTemperature();
  float humid_f = dht.readHumidity();
  int light_i = analogRead(LDR_PIN);
  if (isnan(temp_f) || isnan(humid_f)) {
    Serial.println("No data from DHT, skiped.");
    return;
  }
  payload[0] = FLAG_ENV_NEW; 
  int16_t temp_i16 = (int16_t)(temp_f * 10);
  payload[1] = (byte)(temp_i16 >> 8);
  payload[2] = (byte)(temp_i16 & 0xFF);
  payload[3] = (byte)humid_f;
  int16_t light_i16 = (int16_t)light_i;
  payload[4] = (byte)(light_i16 >> 8);
  payload[5] = (byte)(light_i16 & 0xFF);
  for (int i = 6; i < I2C_PACKET_SIZE; i++) {
    payload[i] = 0;
  }
  newENVDataAvailable = true;
  Serial.print("ENV data Pkged ");
  Serial.print("T:"); Serial.print(temp_f);
  Serial.print(", H:"); Serial.print(humid_f);
  Serial.print(", L:"); Serial.print(light_i);
  Serial.println(".");
}

void requestEvent() {
  if (newCardDataAvailable) {
    Wire.write(payload, I2C_PACKET_SIZE);
    newCardDataAvailable = false;
  } else if (newENVDataAvailable)  {
    Wire.write(payload, I2C_PACKET_SIZE);
    newENVDataAvailable = false;
  } else {
    byte idle_payload[I2C_PACKET_SIZE] = {FLAG_IDLE};
    Wire.write(idle_payload, I2C_PACKET_SIZE);
  }
}

void handleCommands() {
  if (!IsCMD) return; // 如果沒有命令，直接返回

  // 根據旗標執行對應的動作
  switch (command_to_run) {
    case 'P': // 播放
      myDFPlayer.play(command_param);
      break;
    case '+': // 音量增大
      myDFPlayer.volumeUp();
      break;
    case '-': // 音量減小
      myDFPlayer.volumeDown();
      break;
    // 未來可以在此處增加更多指令
    // case 'L': ...
  }
  // 執行完畢後，清除旗標
  IsCMD = false;
}

// 接收並處理來自 NodeMCU 的指令
void receiveEvent(int howMany) {
  // 至少需要一個位元組 (指令本身)
  if (Wire.available() < 1) {
    return;
  }

  // 讀取第一個位元組作為指令
  char command = Wire.read();
  Serial.print("Received command: '");
  Serial.print(command);
  Serial.print("'");

  // 根據指令類型，決定是否讀取額外的參數
  switch (command) {
    case 'P': // 播放指定曲目指令
      if (Wire.available() > 0) {
        command_param = Wire.read(); // 讀取下一個位元組作為音軌編號
        Serial.print(" With parameter: ");
        Serial.println(command_param);
      }
      break;
    
    // 對於單一位元組指令，則不需要讀取參數
    case '+':
      Serial.println(" Vol UP.");
      command_param = 0; // 不需要參數，設為0
      break;
    case '-':
      Serial.println(" Vol Down.");
      command_param = 0; // 不需要參數，設為0
      break;
  }
  
  // 將收到的主指令儲存起來，並升起旗標
  command_to_run = command;
  IsCMD = true;
}