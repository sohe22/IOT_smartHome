/*
 * SmartHome Edge Firmware (Final)
 * 기능: AI 소리 분류 + 엣지 판단(Reasoning) + 양방향 제어(Serial JSON)
 */

#include <Arduino.h>
#include <DHT.h>
#include <Servo.h>
#include <ArduinoJson.h> // [필수] 라이브러리 매니저에서 설치 필요

// ===== Edge Impulse =====
// [주의] 팀원이 준 라이브러리 이름으로 유지하세요.
#include <IOT_project_inferencing.h> 
#include <PDM.h>

// ================= PINS & CONFIG =================
#define DHTPIN     3  // D3
#define DHTTYPE    DHT22
#define RAIN_PIN   A0
#define SERVO_PIN  9  // D9

// 임계값
#define TEMP_HOT_C   25.0
#define TEMP_COLD_C  22.0
#define RAIN_WET_TH  300  // 300 이하면 비 옴 (Analog값 특성)

// 서보 각도
#define WINDOW_OPEN_ANG   0   // 각도는 기구물에 맞춰 조정
#define WINDOW_CLOSE_ANG  90

// ================= OBJECTS =================
DHT dht(DHTPIN, DHTTYPE);
Servo windowServo;

// ================= STATE VARIABLES =================
// 1. 센서 값
float temperature = 0.0;
float humidity    = 0.0;
int   rainValue   = 1024;

// 2. AI 결과
String soundClass = "Noise";
float  soundConf  = 0.0;
bool   trashAlert = false; // 불확실 감지 플래그

// 3. 시스템 제어 상태 (엣지 컴퓨팅의 핵심)
// 기본은 AUTO, 사용자가 명령하면 MANUAL로 변함
String systemMode = "AUTO"; 
String cmdWin     = "Open";
String cmdHeat    = "OFF";
String cmdCool    = "OFF";

// 4. 최종 결정 상태 (서버로 보낼 값)
String finalWin   = "Open";
String finalHeat  = "OFF";
String finalCool  = "OFF";
String reason     = "초기화 중...";

// ================= AUDIO BUFFER =================
static int16_t sampleBuffer[EI_CLASSIFIER_RAW_SAMPLE_COUNT];
static volatile bool bufferReady = false;

void onPDMdata() {
  int bytesAvailable = PDM.available();
  PDM.read(sampleBuffer, bytesAvailable);
  bufferReady = true;
}

// ================= SETUP =================
void setup() {
  Serial.begin(115200); // 속도 맞춤
  
  // 센서 초기화
  dht.begin();
  windowServo.attach(SERVO_PIN);
  windowServo.write(WINDOW_OPEN_ANG);

  // 마이크 초기화
  PDM.onReceive(onPDMdata);
  PDM.setGain(80);
  if (!PDM.begin(1, EI_CLASSIFIER_FREQUENCY)) {
    Serial.println("ERR: PDM Failed");
    while (1);
  }
}

// ================= LOOP (Non-blocking) =================
unsigned long lastMsgTime = 0;
const long interval = 1000; // 1초마다 전송

void loop() {
  // 1. 시리얼 명령 수신 (파이썬에서 보낸 제어 명령 읽기)
  readSerialCommand();

  // 2. 소리 감지 (Trash Alert 상태가 아닐 때만 수행)
  if (!trashAlert) {
    runAudioInference();
  }

  // 3. 주기적으로 센서 읽기 및 판단 (1초 간격)
  if (millis() - lastMsgTime >= interval) {
    lastMsgTime = millis();
    
    // (A) 센서 읽기
    readSensors();

    // (B) 엣지 판단 로직 (여기가 뇌입니다!)
    determineAction();

    // (C) 물리적 제어 수행 (서보모터 등)
    applyActuation();

    // (D) 결과 리포팅 (JSON 전송)
    sendJsonReport();
  }
}

// ---------------------------------------------------------
// [기능 1] 시리얼 명령 읽기 (JSON Parsing)
// ---------------------------------------------------------
void readSerialCommand() {
  if (Serial.available() > 0) {
    String input = Serial.readStringUntil('\n');
    
    // JSON 파싱
    StaticJsonDocument<200> doc;
    DeserializationError error = deserializeJson(doc, input);

    if (!error) {
      // 파이썬에서 {"mode":"MANUAL", "win":"Closed", ...} 형태로 보냄
      if (doc.containsKey("mode")) systemMode = doc["mode"].as<String>();
      if (doc.containsKey("win"))  cmdWin     = doc["win"].as<String>();
      if (doc.containsKey("heat")) cmdHeat    = doc["heat"].as<String>();
      if (doc.containsKey("cool")) cmdCool    = doc["cool"].as<String>();
      
      // 쓰레기 오류 해결 명령 {"resolve": "Can"}
      if (doc.containsKey("resolve")) {
        trashAlert = false; // 경고 해제
        soundClass = doc["resolve"].as<String>(); // 결과 보정
        soundConf = 1.0;
      }
    }
  }
}

// ---------------------------------------------------------
// [기능 2] AI 추론
// ---------------------------------------------------------
void runAudioInference() {
  if (bufferReady) {
    signal_t signal;
    signal.total_length = EI_CLASSIFIER_RAW_SAMPLE_COUNT;
    signal.get_data = [](size_t offset, size_t length, float *out_ptr) {
      numpy::int16_to_float(&sampleBuffer[offset], out_ptr, length);
      return 0;
    };

    ei_impulse_result_t result = {0};
    run_classifier(&signal, &result, false);

    float maxVal = 0;
    int maxIdx = -1;
    for (size_t i = 0; i < EI_CLASSIFIER_LABEL_COUNT; i++) {
      if (result.classification[i].value > maxVal) {
        maxVal = result.classification[i].value;
        maxIdx = i;
      }
    }

    if (maxIdx != -1) {
      String label = result.classification[maxIdx].label;
      float conf = result.classification[maxIdx].value;

      // 불확실 감지 로직 (Threshold 0.6 ~ 0.8 사이일 때 등)
      // 여기선 예시로 Noise가 아닌데 확신도가 낮으면 Alert
      if (label != "Noise" && conf < 0.70) {
        trashAlert = true;
        soundClass = "Uncertain";
        soundConf = conf;
      } else {
        soundClass = label;
        soundConf = conf;
      }
    }
    bufferReady = false;
  }
}

// ---------------------------------------------------------
// [기능 3] 센서 읽기
// ---------------------------------------------------------
void readSensors() {
  float t = dht.readTemperature();
  float h = dht.readHumidity();
  
  if (!isnan(t)) temperature = t;
  if (!isnan(h)) humidity = h;
  
  rainValue = analogRead(RAIN_PIN);
}

// ---------------------------------------------------------
// [기능 4] 엣지 판단 로직 (Reasoning)
// ---------------------------------------------------------
void determineAction() {
  String reasonList = "";
  
  // [AUTO 모드] 센서 기반 판단
  if (systemMode == "AUTO") {
    // 1. 창문 로직
    if (rainValue < RAIN_WET_TH) {
      finalWin = "Closed";
      reasonList += "비 감지됨 -> 창문 닫기";
    } else {
      finalWin = "Open";
      reasonList += "날씨 쾌적 -> 창문 열기";
    }

    // 2. 냉난방 로직
    if (temperature >= TEMP_HOT_C) {
      finalCool = "ON";
      finalHeat = "OFF";
      reasonList += " / 고온 -> 냉방 ON";
    } else if (temperature <= TEMP_COLD_C) {
      finalHeat = "ON";
      finalCool = "OFF";
      reasonList += " / 저온 -> 난방 ON";
    } else {
      finalHeat = "OFF";
      finalCool = "OFF";
      reasonList += " / 온도 적정";
    }
    
  } 
  // [MANUAL 모드] 사용자 명령 우선
  else {
    finalWin  = cmdWin;
    finalHeat = cmdHeat;
    finalCool = cmdCool;
    reasonList = "사용자 수동 제어 중";
  }

  reason = reasonList;
}

// ---------------------------------------------------------
// [기능 5] 물리적 구동
// ---------------------------------------------------------
void applyActuation() {
  // 창문 서보
  if (finalWin == "Open") windowServo.write(WINDOW_OPEN_ANG);
  else windowServo.write(WINDOW_CLOSE_ANG);

  // LED 제어 (있다면 추가)
  // if (finalHeat == "ON") digitalWrite(LED_RED, HIGH); ...
}

// ---------------------------------------------------------
// [기능 6] JSON 리포팅
// ---------------------------------------------------------
void sendJsonReport() {
  // Python 백엔드가 기대하는 키 이름과 정확히 일치시킴
  StaticJsonDocument<300> doc;
  
  doc["temp"] = temperature;
  doc["humid"] = humidity;
  doc["rain"] = rainValue;
  
  doc["sound"] = soundClass;
  doc["conf"]  = soundConf;
  doc["trash_alert"] = trashAlert ? 1 : 0; // Python이 인식하는 flag

  doc["win_stat"]  = finalWin;
  doc["heat_stat"] = finalHeat;
  doc["cool_stat"] = finalCool;
  
  doc["reason"] = reason;
  doc["mode"]   = systemMode;

  serializeJson(doc, Serial);
  Serial.println(); // 줄바꿈 필수
}