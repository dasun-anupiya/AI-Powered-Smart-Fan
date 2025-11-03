#include <WiFi.h>
#include <WebServer.h>
#include <ArduinoJson.h>
#include <Ticker.h>

// WiFi credentials
const char* ssid = "vivo Y100A";
const char* password = "qwe8888@#";

// L298N DC Motor Pins
const int ENA = 27;
const int IN1 = 26;
const int IN2 = 25;

// A4988 Stepper Motor Pins
const int STEP_PIN = 14;
const int DIR_PIN = 12;

WebServer server(80);

// Stepper control variables
Ticker stepperTicker;
volatile bool stepping = false;
const unsigned long stepInterval = 1000; // microseconds (adjust for speed)

void stepperPulse() {
  if (stepping) {
    digitalWrite(STEP_PIN, HIGH);
    delayMicroseconds(2);
    digitalWrite(STEP_PIN, LOW);
  }
}

void startStepping() {
  stepping = true;
  stepperTicker.attach_us(stepInterval, stepperPulse);
}

void stopStepping() {
  stepping = false;
  stepperTicker.detach();
}

void handleMotor() {
  // CORS headers for all responses
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.sendHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  server.sendHeader("Access-Control-Allow-Headers", "Content-Type");

  if (server.method() == HTTP_OPTIONS) {
    server.send(204);
    return;
  }

  if (server.method() != HTTP_POST) {
    server.send(405, "application/json", "{\"error\":\"Method Not Allowed\"}");
    return;
  }

  StaticJsonDocument<200> doc;
  DeserializationError error = deserializeJson(doc, server.arg("plain"));
  if (error) {
    server.send(400, "application/json", "{\"error\":\"Invalid JSON\"}");
    return;
  }
  String cmd = doc["command"] | "";
  if (cmd == "dc_on") {
    digitalWrite(ENA, HIGH);
    digitalWrite(IN1, HIGH);
    digitalWrite(IN2, LOW);
  } else if (cmd == "dc_off") {
    digitalWrite(ENA, LOW);
    digitalWrite(IN1, LOW);
    digitalWrite(IN2, LOW);
  } else if (cmd == "stepper_left") {
    digitalWrite(DIR_PIN, LOW);
    startStepping();
  } else if (cmd == "stepper_right") {
    digitalWrite(DIR_PIN, HIGH);
    startStepping();
  } else if (cmd == "stop") {
    stopStepping();
    digitalWrite(ENA, LOW);
  }
  server.send(200, "application/json", "{\"status\":\"ok\"}");
}

void setup() {
  Serial.begin(115200);

  // Motor pin setup
  pinMode(ENA, OUTPUT);
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(STEP_PIN, OUTPUT);
  pinMode(DIR_PIN, OUTPUT);

  // Stop motors initially
  digitalWrite(ENA, LOW);
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, LOW);
  digitalWrite(STEP_PIN, LOW);
  digitalWrite(DIR_PIN, LOW);

  // Connect to WiFi
  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500); Serial.print(".");
  }
  Serial.println("\nWiFi connected. IP: " + WiFi.localIP().toString());

  // HTTP POST and OPTIONS endpoint for motor control
  server.on("/motor", HTTP_POST, handleMotor);
  server.on("/motor", HTTP_OPTIONS, handleMotor);

  server.begin();
}

void loop() {
  server.handleClient();
} 