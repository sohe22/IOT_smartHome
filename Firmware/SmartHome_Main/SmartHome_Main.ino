/*
 * 스마트홈 미니어처 통합 펌웨어 (Edge Logic 강화 버전)
 * 기능: AI 소리 감지 + 자체 판단 제어 + 결과 리포팅
 */

#include <IoT_project_inferencing.h> // 라이브러리 이름 확인!
#include <DHT.h>
#include <Servo.h>

// --- 핀 설정 ---
#define DHTPIN 2      
#define DHTTYPE DHT22
const int rainPin = A0;    
const int trigPin = 10;    
const int echoPin = 11;    
const int servoPin = 6;    
const int heatLed = 7;     
const int lightPin = 8;    

DHT dht(DHTPIN, DHTTYPE);
Servo windowServo;

const int OPEN_POS = 90;
const int CLOSE_POS = 0;
#define EI_CLASSIFIER_SLICES_PER_MODEL_WINDOW 3 

// --- 전역 변수 (상태 저장용) ---
float temperature = 0.0;
float humidity = 0.0;
int rainValue = 0;
long distance = 0;
const char* predicted_class = "Noise"; 
float confidence = 0.0;               

// [NEW] 아두이노의 판단 결과(상태)를 저장할 변수 추가
const char* windowState = "Open";   // 창문 상태
const char* lightState = "OFF";     // 조명 상태
const char* heatState = "OFF";      // 난방 상태

// ... (오디오 버퍼링 관련 코드는 동일하므로 생략) ...
static bool microphone_inference_record(void);
static int microphone_audio_signal_get_data(size_t offset, size_t length, float *out_ptr);

void setup() {
    Serial.begin(115200); 
    dht.begin();
    windowServo.attach(servoPin);
    pinMode(rainPin, INPUT);
    pinMode(heatLed, OUTPUT);
    pinMode(lightPin, OUTPUT);
    pinMode(trigPin, OUTPUT);
    pinMode(echoPin, INPUT);

    if (EI_CLASSIFIER_RAW_SAMPLE_COUNT > 0) {
        ei_printf("Edge Impulse Standalone Inferencing\n");
    }
}

void loop() {
    // 1. AI 소리 분류 (동일)
    bool m = microphone_inference_record(); 
    if (!m) return;

    signal_t signal;
    signal.total_length = EI_CLASSIFIER_RAW_SAMPLE_COUNT;
    signal.get_data = &microphone_audio_signal_get_data;
    ei_impulse_result_t result = { 0 };

    EI_IMPULSE_ERROR r = run_classifier(&signal, &result, false);
    if (r == EI_IMPULSE_OK) {
        float max_confidence = 0.0;
        int max_index = -1;
        for (size_t ix = 0; ix < EI_CLASSIFIER_LABEL_COUNT; ix++) {
            if (result.classification[ix].value > max_confidence) {
                max_confidence = result.classification[ix].value;
                max_index = ix;
            }
        }
        if (max_index != -1) {
            predicted_class = result.classification[max_index].label;
            confidence = result.classification[max_index].value;
        }
    }

    // 2. 센서 읽기 & 판단 제어
    readSensors();
    controlLogic(); // <--- 여기서 상태 변수가 업데이트됨

    // 3. JSON 전송 (판단 결과 포함)
    sendJsonData();
}

void readSensors() {
    temperature = dht.readTemperature();
    humidity = dht.readHumidity();
    if (isnan(temperature)) temperature = 0.0;
    if (isnan(humidity)) humidity = 0.0;

    rainValue = analogRead(rainPin);

    digitalWrite(trigPin, LOW);
    delayMicroseconds(2);
    digitalWrite(trigPin, HIGH);
    delayMicroseconds(10);
    digitalWrite(trigPin, LOW);
    long duration = pulseIn(echoPin, HIGH);
    distance = duration * 0.034 / 2;
}

// [중요] 엣지 제어 로직: 여기서 아두이노가 '결정'을 내리고 상태를 변수에 저장
void controlLogic() {
    // 1. 창문 & 난방 제어
    bool isRaining = (rainValue < 800); 
    
    if (isRaining || temperature < 18.0) {
        windowServo.write(CLOSE_POS);
        // 상태 업데이트
        if (isRaining) windowState = "Closed(Rain)";
        else windowState = "Closed(Cold)";
        
        if (temperature < 18.0) {
            digitalWrite(heatLed, HIGH);
            heatState = "ON";
        } else {
            digitalWrite(heatLed, LOW);
            heatState = "OFF";
        }
    } else {
        windowServo.write(OPEN_POS);
        windowState = "Open";
        digitalWrite(heatLed, LOW);
        heatState = "OFF";
    }

    // 2. 차고 제어
    if (distance < 40 && distance > 0) {
        digitalWrite(lightPin, HIGH);
        lightState = "ON"; // 상태 업데이트
    } else {
        digitalWrite(lightPin, LOW);
        lightState = "OFF";
    }
}

void sendJsonData() {
    // 버퍼 사이즈를 넉넉하게 늘림 (128 -> 200)
    char buffer[200]; 
    
    // [NEW] JSON에 win, heat, light 상태 추가
    // 예: {"temp":25.0, ..., "win":"Open", "heat":"OFF", "light":"ON"}
    snprintf(buffer, sizeof(buffer), 
        "{\"temp\":%.1f,\"humid\":%.1f,\"rain\":%d,\"dist\":%ld,\"sound\":\"%s\",\"conf\":%.2f,\"win\":\"%s\",\"heat\":\"%s\",\"light\":\"%s\"}",
        temperature, humidity, rainValue, distance, predicted_class, confidence,
        windowState, heatState, lightState  // <--- 여기가 핵심!
    );
    
    Serial.println(buffer);
}

// ... (오디오 샘플링 콜백 함수는 이전과 동일) ...
static bool microphone_inference_record(void) {
    inference.buf_count = 0;
    inference.buf_ready = 0;
    inference.buf_select = 0;
    if (microphone_inference_start(EI_CLASSIFIER_RAW_SAMPLE_COUNT) == false) return false;
    while (inference.buf_ready == 0) {};
    inference.buf_ready = 0;
    microphone_inference_end();
    return true;
}

static int microphone_audio_signal_get_data(size_t offset, size_t length, float *out_ptr) {
    numpy::int16_to_float(&inference.buffer[offset], out_ptr, length);
    return 0;
}