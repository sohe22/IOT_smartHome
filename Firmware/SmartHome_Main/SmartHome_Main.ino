#include <Arduino.h>
#include <DHT.h>
#include <Servo.h>

// ===== Edge Impulse =====
#include <IOT_project_inferencing.h>
#include "edge-impulse-sdk/dsp/numpy.hpp"

// ===== MIC (Nano 33 BLE Sense) =====
#include <PDM.h>

// ================= PINS =================
#define DHTPIN     3
#define DHTTYPE    DHT22
#define RAIN_PIN   A0
#define SERVO_PIN  9

// ================= THRESHOLDS =================
#define TEMP_HOT_C   25.0
#define TEMP_COLD_C  22.0
#define RAIN_WET_TH  300

#define WINDOW_OPEN_ANG   120
#define WINDOW_CLOSE_ANG  0

// ================= OBJECTS =================
DHT dht(DHTPIN, DHTTYPE);
Servo windowServo;

// ================= STATE =================
float temperature = NAN;
float humidity    = NAN;
int   rainValue   = 0;
bool  wet         = false;

bool tempHot = false;
const char* tempState = "TEMP_NAN";

// ===== SOUND RESULT =====
const char* soundLabel = "Unknown";
float soundConf = 0.0;

// ================= AUDIO BUFFER =================
static int16_t sampleBuffer[EI_CLASSIFIER_RAW_SAMPLE_COUNT];
static volatile bool bufferReady = false;

// ================= PDM CALLBACK =================
void onPDMdata() {
  int bytesAvailable = PDM.available();
  PDM.read(sampleBuffer, bytesAvailable);
  bufferReady = true;
}

// ================= SETUP =================
void setup() {
  Serial.begin(115200);
  delay(2000);

  // --- Sensors ---
  dht.begin();
  windowServo.attach(SERVO_PIN);
  windowServo.write(WINDOW_OPEN_ANG);

  // --- Microphone ---
  PDM.onReceive(onPDMdata);
  PDM.setGain(80);

  if (!PDM.begin(1, EI_CLASSIFIER_FREQUENCY)) {
    Serial.println("PDM start failed");
    while (1);
  }

  Serial.println("SYSTEM READY");
}

// ================= LOOP =================
void loop() {

  // ===== 1. RECORD SOUND =====
  bufferReady = false;
  while (!bufferReady) {
    delay(1);
  }

  signal_t signal;
  signal.total_length = EI_CLASSIFIER_RAW_SAMPLE_COUNT;
  signal.get_data = [](size_t offset, size_t length, float *out_ptr) {
    numpy::int16_to_float(&sampleBuffer[offset], out_ptr, length);
    return 0;
  };

  ei_impulse_result_t result = {0};
  run_classifier(&signal, &result, false);

  // --- Get best sound ---
  float maxVal = 0;
  int maxIdx = -1;
  for (size_t i = 0; i < EI_CLASSIFIER_LABEL_COUNT; i++) {
    if (result.classification[i].value > maxVal) {
      maxVal = result.classification[i].value;
      maxIdx = i;
    }
  }
  if (maxIdx != -1) {
    soundLabel = result.classification[maxIdx].label;
    soundConf = result.classification[maxIdx].value;
  }

  // ===== 2. READ SENSORS =====
  temperature = dht.readTemperature();
  humidity    = dht.readHumidity();
  rainValue   = analogRead(RAIN_PIN);
  wet         = (rainValue >= RAIN_WET_TH);

  // ===== 3. TEMP STATE (RED / BLUE) =====
  if (isnan(temperature)) {
    tempState = "TEMP_NAN";
  } else {
    if (!tempHot && temperature >= TEMP_HOT_C) tempHot = true;
    if ( tempHot && temperature <= TEMP_COLD_C) tempHot = false;
    tempState = tempHot ? "RED" : "BLUE";
  }

  // ===== 4. WINDOW CONTROL =====
  windowServo.write(wet ? WINDOW_CLOSE_ANG : WINDOW_OPEN_ANG);
  const char* windowState = wet ? "CLOSE" : "OPEN";

  // ===== 5. JSON OUTPUT =====
  char json[260];
  snprintf(json, sizeof(json),
    "{"
      "\"temp\":%.1f,"
      "\"humid\":%.1f,"
      "\"rain\":%d,"
      "\"wet\":%s,"
      "\"tempState\":\"%s\","
      "\"window\":\"%s\","
      "\"sound\":\"%s\","
      "\"conf\":%.2f"
    "}",
    isnan(temperature)?0.0:temperature,
    isnan(humidity)?0.0:humidity,
    rainValue,
    wet ? "true" : "false",
    tempState,
    windowState,
    soundLabel,
    soundConf
  );

  Serial.println(json);

  delay(2500); // не чаще
}
