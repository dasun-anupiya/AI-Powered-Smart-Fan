import cv2
import numpy as np
from flask import Flask, Response
from ultralytics import YOLO
import sys
import time
import requests
import json
import threading
import math

# Load YOLOv8 .pt model
model = YOLO("best.pt")  # Replace with your model file

# Define which class IDs represent a person
PERSON_CLASS_IDS = {1, 2, 3}

# Global variables to store person coordinates
person_coordinates = None
person_detected = False
last_detection_time = 0
group_mode_start_time = 0
group_mode_active = False

# ESP32 configuration
ESP32_IP = "192.168.1.100"  # Replace with your ESP32 IP address
ESP32_PORT = 80
ESP32_ENDPOINT = f"http://{ESP32_IP}:{ESP32_PORT}/data"

# Detection smoothing variables
coordinate_history = []
HISTORY_SIZE = 5
SMOOTHING_FACTOR = 0.3

# Function to send data to ESP32
def send_to_esp32(data):
    """Send detection data to ESP32 in a separate thread"""
    try:
        response = requests.post(ESP32_ENDPOINT, json=data, timeout=2)
        if response.status_code == 200:
            print(f"[ESP32] Data sent successfully: {data}")
        else:
            print(f"[ESP32] Failed to send data. Status code: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"[ESP32] Connection error: {e}")

def send_to_esp32_async(data):
    """Send data to ESP32 asynchronously"""
    thread = threading.Thread(target=send_to_esp32, args=(data,))
    thread.daemon = True
    thread.start()

# Run inference and extract detections
def infer(frame):
    results = model(frame, verbose=False)[0]
    h, w, _ = frame.shape
    detections = []

    for box in results.boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        score = float(box.conf[0])
        class_id = int(box.cls[0])
        if score > 0.3:
            detections.append((x1, y1, x2, y2, score, class_id))
    return detections

def smooth_coordinates(new_coords):
    """Apply smoothing to coordinates to reduce jitter"""
    global coordinate_history
    
    if not coordinate_history:
        coordinate_history.append(new_coords)
        return new_coords
    
    # Add new coordinates to history
    coordinate_history.append(new_coords)
    
    # Keep only recent history
    if len(coordinate_history) > HISTORY_SIZE:
        coordinate_history.pop(0)
    
    # Calculate weighted average with more weight to recent values
    weights = [i + 1 for i in range(len(coordinate_history))]
    total_weight = sum(weights)
    
    smoothed_x = sum(coord['center_x'] * weight for coord, weight in zip(coordinate_history, weights)) / total_weight
    smoothed_y = sum(coord['center_y'] * weight for coord, weight in zip(coordinate_history, weights)) / total_weight
    
    # Apply additional smoothing factor
    if len(coordinate_history) > 1:
        prev_coords = coordinate_history[-2]
        smoothed_x = prev_coords['center_x'] * (1 - SMOOTHING_FACTOR) + smoothed_x * SMOOTHING_FACTOR
        smoothed_y = prev_coords['center_y'] * (1 - SMOOTHING_FACTOR) + smoothed_y * SMOOTHING_FACTOR
    
    # Update the latest coordinates with smoothed values
    smoothed_coords = new_coords.copy()
    smoothed_coords['center_x'] = int(smoothed_x)
    smoothed_coords['center_y'] = int(smoothed_y)
    
    return smoothed_coords

def get_person_coordinates(person_box):
    """Extract and return person coordinates from bounding box"""
    x1, y1, x2, y2, score, class_id = person_box
    
    # Calculate center coordinates
    center_x = (x1 + x2) // 2
    center_y = (y1 + y2) // 2
    
    # Calculate bounding box dimensions
    width = x2 - x1
    height = y2 - y1
    
    # Calculate distance estimation based on bounding box size
    distance_factor = (width * height) / (FRAME_WIDTH * FRAME_HEIGHT)
    
    # Normalize coordinates for better tracking
    normalized_x = (center_x - FRAME_WIDTH/2) / (FRAME_WIDTH/2)
    normalized_y = (center_y - FRAME_HEIGHT/2) / (FRAME_HEIGHT/2)
    
    # Calculate angle from center for stepper motor control
    angle_from_center = math.atan2(center_x - FRAME_WIDTH/2, FRAME_HEIGHT/2) * 180 / math.pi
    
    coordinates = {
        'center_x': center_x,
        'center_y': center_y,
        'bbox_x1': x1,
        'bbox_y1': y1,
        'bbox_x2': x2,
        'bbox_y2': y2,
        'width': width,
        'height': height,
        'confidence': score,
        'class_id': class_id,
        'normalized_x': normalized_x,
        'normalized_y': normalized_y,
        'distance_factor': distance_factor,
        'angle_from_center': angle_from_center
    }
    
    return coordinates

# Frame dimensions (will be set dynamically)
FRAME_WIDTH = 640
FRAME_HEIGHT = 480

# Generate frames from IP camera or webcam
def gen_frames(source):
    global person_coordinates, person_detected, FRAME_WIDTH, FRAME_HEIGHT
    global last_detection_time, group_mode_start_time, group_mode_active, coordinate_history
    
    cap = cv2.VideoCapture(0 if source == "0" else f"http://{source}/stream")

    if not cap.isOpened():
        print(f"[ERROR] Cannot connect to video source: {source}")
        return

    # Get actual frame dimensions
    FRAME_WIDTH = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    FRAME_HEIGHT = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[INFO] Frame dimensions: {FRAME_WIDTH}x{FRAME_HEIGHT}")

    prev_time = time.time()
    frame_center_x = FRAME_WIDTH // 2
    frame_center_y = FRAME_HEIGHT // 2

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[WARN] Frame not received. Reconnecting...")
            time.sleep(1)
            cap.release()
            cap = cv2.VideoCapture(0 if source == "0" else f"http://{source}/stream")
            continue

        # Flip the frame horizontally to fix mirroring (especially for webcam)
        frame = cv2.flip(frame, 1)

        current_time = time.time()
        detections = infer(frame)
        person_boxes = [d for d in detections if d[5] in PERSON_CLASS_IDS]
        count = len(person_boxes)

        # Draw frame center reference
        cv2.circle(frame, (frame_center_x, frame_center_y), 3, (255, 0, 255), -1)
        cv2.putText(frame, "CENTER", (frame_center_x - 30, frame_center_y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 255), 1)

        # Draw all detections
        for (x1, y1, x2, y2, score, class_id) in detections:
            label = model.names.get(class_id, f"Class {class_id}")
            color = (0, 255, 0) if class_id in PERSON_CLASS_IDS else (0, 0, 255)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, f"{label} {score:.2f}", (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        # Handle group mode timing
        if group_mode_active and (current_time - group_mode_start_time) >= 30:
            group_mode_active = False
            print("[INFO] Group mode ended, resuming normal detection")

        # Handle person detection and coordinate extraction
        if count == 1 and not group_mode_active:
            person_detected = True
            raw_coordinates = get_person_coordinates(person_boxes[0])
            person_coordinates = smooth_coordinates(raw_coordinates)
            last_detection_time = current_time
            
            # Prepare data for ESP32
            esp32_data = {
                "status": "single_person",
                "x": person_coordinates['center_x'],
                "y": person_coordinates['center_y'],
                "confidence": person_coordinates['confidence'],
                "width": person_coordinates['width'],
                "height": person_coordinates['height'],
                "angle": person_coordinates['angle_from_center'],
                "distance_factor": person_coordinates['distance_factor']
            }
            
            # Send to ESP32
            send_to_esp32_async(esp32_data)
            
            # Print coordinates to console
            print(f"[INFO] Person detected at coordinates:")
            print(f"  Center: ({person_coordinates['center_x']}, {person_coordinates['center_y']})")
            print(f"  Angle from center: {person_coordinates['angle_from_center']:.2f}°")
            print(f"  Distance factor: {person_coordinates['distance_factor']:.3f}")
            print(f"  Confidence: {person_coordinates['confidence']:.2f}")
            print("-" * 50)
            
            # Visual indicators
            center_x = person_coordinates['center_x']
            center_y = person_coordinates['center_y']
            label = model.names.get(person_coordinates['class_id'], f"Class {person_coordinates['class_id']}")
            
            # Draw center point and tracking line
            cv2.circle(frame, (center_x, center_y), 8, (255, 255, 0), -1)
            cv2.line(frame, (frame_center_x, frame_center_y), (center_x, center_y), (255, 255, 0), 2)
            
            # Display coordinates and angle on frame
            cv2.putText(frame, f"{label} at ({center_x}, {center_y})", (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
            cv2.putText(frame, f"Angle: {person_coordinates['angle_from_center']:.1f}°", (10, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
            cv2.putText(frame, f"Distance: {person_coordinates['distance_factor']:.3f}", (10, 110),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
            
        elif count >= 2:
            if not group_mode_active:
                group_mode_active = True
                group_mode_start_time = current_time
                print("[INFO] Group detected, starting 30-second swing mode")
            
            person_detected = False
            person_coordinates = None
            coordinate_history = []  # Clear history when switching modes
            
            # Send "multiple people" status to ESP32
            esp32_data = {
                "status": "multiple_people",
                "count": count,
                "x": 0,
                "y": 0,
                "swing_duration": 30
            }
            send_to_esp32_async(esp32_data)
            
            # Display group mode info
            remaining_time = 30 - (current_time - group_mode_start_time)
            cv2.putText(frame, f"GROUP MODE - {count} people", (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)
            cv2.putText(frame, f"Swing time: {remaining_time:.1f}s", (10, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)
            
        else:
            # No person detected
            if person_detected or (current_time - last_detection_time) > 2:  # 2 second delay
                person_detected = False
                person_coordinates = None
                coordinate_history = []  # Clear history
                
                # Send "no person" status to ESP32
                esp32_data = {
                    "status": "no_person",
                    "x": 0,
                    "y": 0,
                    "return_center": True
                }
                send_to_esp32_async(esp32_data)
                
                cv2.putText(frame, "No person detected", (10, 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                cv2.putText(frame, "Returning to center", (10, 90),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        # Display FPS and mode
        curr_time = time.time()
        fps = 1 / (curr_time - prev_time)
        prev_time = curr_time
        cv2.putText(frame, f"FPS: {fps:.2f}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        
        if group_mode_active:
            cv2.putText(frame, "MODE: GROUP SWING", (FRAME_WIDTH - 200, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)
        else:
            cv2.putText(frame, "MODE: TRACKING", (FRAME_WIDTH - 200, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        _, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

        time.sleep(0.03)  # Slightly faster frame rate

# Flask setup
app = Flask(__name__)
video_source = None

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(video_source), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/coordinates')
def get_coordinates():
    """API endpoint to get current person coordinates"""
    global person_coordinates, person_detected, group_mode_active
    
    return {
        'person_detected': person_detected,
        'group_mode_active': group_mode_active,
        'coordinates': person_coordinates if person_detected else None
    }

@app.route('/reset')
def reset_tracking():
    """Reset tracking system"""
    global person_coordinates, person_detected, coordinate_history, group_mode_active
    person_coordinates = None
    person_detected = False
    coordinate_history = []
    group_mode_active = False
    
    # Send reset command to ESP32
    esp32_data = {
        "status": "reset",
        "return_center": True
    }
    send_to_esp32_async(esp32_data)
    
    return "Tracking system reset"

@app.route('/')
def index():
    return '''
    <html>
      <head><title>Advanced People Detection & Tracking</title></head>
      <body>
        <h1>Advanced People Detection & Tracking System</h1>
        <img src="/video_feed" width="640" />
        <br><br>
        <button onclick="getCoordinates()">Get Current Status</button>
        <button onclick="resetTracking()">Reset System</button>
        <div id="coordinates"></div>
        
        <script>
        function getCoordinates() {
            fetch('/coordinates')
                .then(response => response.json())
                .then(data => {
                    const div = document.getElementById('coordinates');
                    if (data.person_detected) {
                        const coords = data.coordinates;
                        div.innerHTML = `
                            <h3>Person Detected - Tracking Active:</h3>
                            <p>Center: (${coords.center_x}, ${coords.center_y})</p>
                            <p>Angle from center: ${coords.angle_from_center.toFixed(1)}°</p>
                            <p>Distance factor: ${coords.distance_factor.toFixed(3)}</p>
                            <p>Size: ${coords.width}x${coords.height}</p>
                            <p>Confidence: ${coords.confidence.toFixed(2)}</p>
                        `;
                    } else if (data.group_mode_active) {
                        div.innerHTML = '<h3>Group Mode Active - Swing Pattern</h3>';
                    } else {
                        div.innerHTML = '<h3>No Person Detected - Standby</h3>';
                    }
                });
        }
        
        function resetTracking() {
            fetch('/reset')
                .then(response => response.text())
                .then(data => {
                    alert(data);
                });
        }
        
        // Auto-refresh status every 1 second
        setInterval(getCoordinates, 1000);
        </script>
      </body>
    </html>
    '''

if __name__ == "__main__":
    if len(sys.argv) > 1:
        video_source = sys.argv[1]
    else:
        video_source = input("Enter ESP32-CAM IP or type 0 to use laptop webcam: ").strip()
    
    # Get ESP32 target IP if not using default
    esp32_input = input(f"Enter target ESP32 IP (default: {ESP32_IP}): ").strip()
    if esp32_input:
        ESP32_IP = esp32_input
        ESP32_ENDPOINT = f"http://{ESP32_IP}:{ESP32_PORT}/data"
    
    print("Starting Advanced People Detection & Tracking Server...")
    print(f"Camera source: {video_source}")
    print(f"Sending data to ESP32: {ESP32_ENDPOINT}")
    print("Access the stream at: http://localhost:8080")
    print("Features:")
    print("- Smooth coordinate tracking with history")
    print("- 30-second group swing mode")
    print("- Auto-return to center when no person")
    print("- Improved angle calculation for stepper motor")
    app.run(host='0.0.0.0', port=8080, debug=False)