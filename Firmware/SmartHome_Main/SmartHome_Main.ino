/*
 * 스마트홈 미니어처 통합 펌웨어 (Nano 33 BLE Sense 전용)
 * 기능: 소리 감지(AI) + 온습도/빗물/초음파 센서 제어 + JSON Serial 통신
 */

// ================================================================
// 1. 라이브러리 및 설정
// ================================================================
// [중요] 아래 헤더 파일 이름을 다운로드 받은 라이브러리 이름으로 바꾸세요!
// 예: <My_Project_inferencing.h>
#include <SmartHome_Sound_Classifier_inferencing.h> 

#include <DHT.h>
#include <Servo.h>

// --- 핀 설정 (Nano 33 BLE Sense 기준) ---
#define DHTPIN 2       // D2
#define DHTTYPE DHT22

const int rainPin = A0;     // 빗물 센서
const int trigPin = 10;     // 초음파 Trig (주의: 3.3V 레벨 시프트 권장)
const int echoPin = 11;     // 초음파 Echo (주의: 전압 분배 회로 필수!)
const int servoPin = 6;     // 서보모터
const int heatLed = 7;      // 난방 LED
const int lightPin = 8;     // 차고 조명 LED

// --- 객체 생성 ---
DHT dht(DHTPIN, DHTTYPE);
Servo windowServo;

// --- 설정값 ---
const int OPEN_POS = 90;
const int CLOSE_POS = 0;
#define EI_CLASSIFIER_SLICES_PER_MODEL_WINDOW 3 // 추론 속도 조절

// --- 전역 변수 (상태 저장용) ---
float temperature = 0.0;
float humidity = 0.0;
int rainValue = 0;
long distance = 0;
const char* predicted_class = "Noise"; // AI 분류 결과
float confidence = 0.0;                // 신뢰도

// ================================================================
// 2. 오디오 버퍼링 설정 (Edge Impulse 관련)
// ================================================================
static bool microphone_inference_record(void);
static int microphone_audio_signal_get_data(size_t offset, size_t length, float *out_ptr);

void setup() {
    Serial.begin(115200); // 속도 115200 추천
    // while (!Serial);   // 디버깅 시에는 주석 해제 (연결될 때까지 대기)

    // 센서 초기화
    dht.begin();
    windowServo.attach(servoPin);
    pinMode(rainPin, INPUT);
    pinMode(heatLed, OUTPUT);
    pinMode(lightPin, OUTPUT);
    pinMode(trigPin, OUTPUT);
    pinMode(echoPin, INPUT);

    // AI 모델 초기화 확인
    if (EI_CLASSIFIER_RAW_SAMPLE_COUNT > 0) {
        ei_printf("Edge Impulse Standalone Inferencing\n");
    }
    
    // PDM 마이크 초기화 로직은 라이브러리 내부에서 처리됨
    // (run_classifier 호출 시 자동 처리)
}

void loop() {
    // ------------------------------------------------
    // [Part 1] AI 소리 분류 (Microphone Inference)
    // ------------------------------------------------
    bool m = microphone_inference_record(); 
    if (!m) {
        Serial.println("ERR: Failed to record audio...");
        return;
    }

    signal_t signal;
    signal.total_length = EI_CLASSIFIER_RAW_SAMPLE_COUNT;
    signal.get_data = &microphone_audio_signal_get_data;
    ei_impulse_result_t result = { 0 };

    // 분류 실행
    EI_IMPULSE_ERROR r = run_classifier(&signal, &result, false);
    if (r != EI_IMPULSE_OK) {
        Serial.print("ERR: Failed to run classifier (");
        Serial.print(r);
        Serial.println(")");
        return;
    }

    // 가장 확률 높은 결과 찾기
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

    // ------------------------------------------------
    // [Part 2] 센서 데이터 읽기 & 제어 로직
    // ------------------------------------------------
    readSensors();
    controlLogic();

    // ------------------------------------------------
    // [Part 3] JSON 데이터 전송 (메모리 최적화: snprintf 사용)
    // ------------------------------------------------
    sendJsonData();

    // 딜레이 없음 (오디오 샘플링 시간이 이미 딜레이 역할을 함)
}

// ================================================================
// 보조 함수들
// ================================================================

void readSensors() {
    // 1. 온습도
    temperature = dht.readTemperature();
    humidity = dht.readHumidity();
    if (isnan(temperature)) temperature = 0.0;
    if (isnan(humidity)) humidity = 0.0;

    // 2. 빗물
    rainValue = analogRead(rainPin);

    // 3. 초음파 (거리)
    digitalWrite(trigPin, LOW);
    delayMicroseconds(2);
    digitalWrite(trigPin, HIGH);
    delayMicroseconds(10);
    digitalWrite(trigPin, LOW);
    long duration = pulseIn(echoPin, HIGH);
    distance = duration * 0.034 / 2;
}

void controlLogic() {
    // [창문 & 난방]
    bool isRaining = (rainValue < 800); // 빗물 기준값
    if (isRaining || temperature < 18.0) {
        windowServo.write(CLOSE_POS);
        if (temperature < 18.0) digitalWrite(heatLed, HIGH); // 난방 ON
        else digitalWrite(heatLed, LOW);
    } else {
        windowServo.write(OPEN_POS);
        digitalWrite(heatLed, LOW);
    }

    // [차고 조명]
    if (distance < 40 && distance > 0) {
        digitalWrite(lightPin, HIGH);
    } else {
        digitalWrite(lightPin, LOW);
    }
}

void sendJsonData() {
    // 메모리 절약을 위해 ArduinoJson 대신 snprintf 사용 (버퍼 방식)
    char buffer[128]; 
    
    // JSON 포맷: {"temp":24.5,"humid":60.0,"rain":1024,"dist":35,"sound":"Can","conf":0.95}
    snprintf(buffer, sizeof(buffer), 
        "{\"temp\":%.1f,\"humid\":%.1f,\"rain\":%d,\"dist\":%ld,\"sound\":\"%s\",\"conf\":%.2f}",
        temperature, humidity, rainValue, distance, predicted_class, confidence
    );
    
    Serial.println(buffer);
}

// ================================================================
// Edge Impulse 오디오 샘플링 콜백 함수 (수정 불필요)
// ================================================================
static bool microphone_inference_record(void) {
    inference.buf_count = 0;
    inference.buf_ready = 0;
    inference.buf_select = 0;

    if (microphone_inference_start(EI_CLASSIFIER_RAW_SAMPLE_COUNT) == false) {
        return false;
    }

    while (inference.buf_ready == 0) {
        // 데이터가 모일 때까지 대기
    }

    inference.buf_ready = 0;
    microphone_inference_end();
    return true;
}

static int microphone_audio_signal_get_data(size_t offset, size_t length, float *out_ptr) {
    numpy::int16_to_float(&inference.buffer[offset], out_ptr, length);
    return 0;
}