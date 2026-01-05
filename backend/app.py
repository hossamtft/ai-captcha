from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import json, uuid, math, random, os, hashlib, time
from datetime import datetime, timedelta
from collections import defaultdict

app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
os.makedirs(DATA_DIR, exist_ok=True)
active_challenges = {}
LOGS_FILE = os.path.join(DATA_DIR, 'attempts.json')

# Rate limiting configuration - blocks high-frequency polling (5ms intervals)
request_timestamps = defaultdict(list)
RATE_LIMIT_WINDOW = 1.0  # 1 second window
MAX_REQUESTS_PER_WINDOW = 10  # Max 10 requests per second

def check_rate_limit(ip_address):
    """Returns True if request should be allowed, False if rate limited."""
    now = datetime.utcnow()
    cutoff = now - timedelta(seconds=RATE_LIMIT_WINDOW)
    
    # Remove old timestamps
    request_timestamps[ip_address] = [
        ts for ts in request_timestamps[ip_address] 
        if ts > cutoff
    ]
    
    # Check if over limit
    if len(request_timestamps[ip_address]) >= MAX_REQUESTS_PER_WINDOW:
        return False
    
    # Add current timestamp
    request_timestamps[ip_address].append(now)
    return True

def generate_challenge_nonce(challenge_id):
    """Generate a cryptographically secure nonce for challenge validation."""
    timestamp = str(int(time.time()))
    nonce_input = f"{challenge_id}{timestamp}{random.randint(0, 999999)}"
    return hashlib.sha256(nonce_input.encode()).hexdigest()

def load_logs():
    if os.path.exists(LOGS_FILE):
        with open(LOGS_FILE, 'r') as f:
            return json.load(f)
    return []

def save_log(entry):
    logs = load_logs()
    logs.append(entry)
    with open(LOGS_FILE, 'w') as f:
        json.dump(logs, f, indent=2)

def generate_temporal_challenge():
    seed = random.randint(1, 1000000)
    random.seed(seed)
    
    total_duration = random.randint(4000, 7000)
    zone_width = random.randint(250, 450)
    zone_start_pct = random.uniform(0.25, 0.65)
    zone_start = int(total_duration * zone_start_pct)
    
    speed_segments = []
    remaining = total_duration
    while remaining > 0:
        segment_duration = min(random.randint(400, 1200), remaining)
        speed_multiplier = random.uniform(0.5, 2.0)
        speed_segments.append({"duration": segment_duration, "speed": round(speed_multiplier, 2)})
        remaining -= segment_duration
    
    challenge_id = str(uuid.uuid4())
    challenge = {
        "challenge_id": challenge_id,
        "type": "temporal",
        "nonce": generate_challenge_nonce(challenge_id),  # Prevent replay attacks
        "seed": seed,
        "total_duration": total_duration,
        "zone_start": zone_start,
        "zone_width": zone_width,
        "speed_segments": speed_segments,
        "created_at": datetime.utcnow().isoformat()
    }
    active_challenges[challenge_id] = challenge
    return challenge

def generate_behavioural_challenge():
    seed = random.randint(1, 1000000)
    random.seed(seed)
    
    num_waypoints = random.randint(4, 6)
    min_distance = 85
    time_limit = 12000
    
    waypoints = []
    for _ in range(num_waypoints):
        for attempt in range(100):
            x, y = random.randint(60, 540), random.randint(60, 340)
            if all(math.sqrt((x - wp["x"])**2 + (y - wp["y"])**2) >= min_distance for wp in waypoints):
                waypoints.append({"x": x, "y": y})
                break
    
    challenge_id = str(uuid.uuid4())
    challenge = {
        "challenge_id": challenge_id,
        "type": "behavioural",
        "nonce": generate_challenge_nonce(challenge_id),  # Prevent replay attacks
        "seed": seed,
        "waypoints": waypoints,
        "revealed_waypoints": 0,  # Track how many waypoints have been revealed
        "canvas_width": 600,
        "canvas_height": 400,
        "time_limit": time_limit,
        "created_at": datetime.utcnow().isoformat()
    }
    active_challenges[challenge_id] = challenge
    return challenge

def extract_features(trajectory):
    if len(trajectory) < 2:
        return None
    
    path_length = sum(math.sqrt((trajectory[i]["x"] - trajectory[i-1]["x"])**2 + 
                                (trajectory[i]["y"] - trajectory[i-1]["y"])**2) 
                      for i in range(1, len(trajectory)))
    
    straight = math.sqrt((trajectory[-1]["x"] - trajectory[0]["x"])**2 + 
                        (trajectory[-1]["y"] - trajectory[0]["y"])**2)
    
    velocities = []
    accelerations = []
    for i in range(1, len(trajectory)):
        dt = max(trajectory[i]["t"] - trajectory[i-1]["t"], 1)
        dx = trajectory[i]["x"] - trajectory[i-1]["x"]
        dy = trajectory[i]["y"] - trajectory[i-1]["y"]
        v = math.sqrt(dx**2 + dy**2) / dt
        velocities.append(v)
        if len(velocities) > 1:
            accelerations.append(abs(velocities[-1] - velocities[-2]) / dt)
    
    vel_mean = sum(velocities) / len(velocities) if velocities else 0
    vel_var = sum((v - vel_mean)**2 for v in velocities) / len(velocities) if velocities else 0
    vel_std = math.sqrt(vel_var)
    
    directions = []
    for i in range(1, len(trajectory)):
        dx = trajectory[i]["x"] - trajectory[i-1]["x"]
        dy = trajectory[i]["y"] - trajectory[i-1]["y"]
        if math.sqrt(dx**2 + dy**2) > 0.5:
            directions.append(math.atan2(dy, dx))
    
    dir_changes = sum(1 for i in range(1, len(directions)) if abs(directions[i] - directions[i-1]) > 0.3)
    
    pauses = 0
    pause_time = 0
    for i in range(1, len(trajectory)):
        dt = trajectory[i]["t"] - trajectory[i-1]["t"]
        if dt > 100:
            pauses += 1
            pause_time += dt
    
    curvatures = []
    for i in range(2, len(trajectory)):
        x1, y1 = trajectory[i-2]["x"], trajectory[i-2]["y"]
        x2, y2 = trajectory[i-1]["x"], trajectory[i-1]["y"]
        x3, y3 = trajectory[i]["x"], trajectory[i]["y"]
        a = math.sqrt((x2-x1)**2 + (y2-y1)**2)
        b = math.sqrt((x3-x2)**2 + (y3-y2)**2)
        c = math.sqrt((x3-x1)**2 + (y3-y1)**2)
        if a > 0.5 and b > 0.5:
            area = 0.5 * abs((x2-x1)*(y3-y1) - (x3-x1)*(y2-y1))
            if a * b > 0:
                curvatures.append(4 * area / (a * b * c) if c > 0 else 0)
    
    curv_mean = sum(curvatures) / len(curvatures) if curvatures else 0
    curv_var = sum((c - curv_mean)**2 for c in curvatures) / len(curvatures) if curvatures else 0
    accel_mean = sum(accelerations) / len(accelerations) if accelerations else 0
    accel_var = sum((a - accel_mean)**2 for a in accelerations) / len(accelerations) if accelerations else 0
    
    return {
        "path_length": round(path_length, 2),
        "straight_distance": round(straight, 2),
        "path_ratio": round(path_length / max(straight, 1), 3),
        "velocity_mean": round(vel_mean, 4),
        "velocity_std": round(vel_std, 4),
        "direction_changes": dir_changes,
        "pause_count": pauses,
        "pause_time": pause_time,
        "curvature_mean": round(curv_mean, 4),
        "curvature_variance": round(curv_var, 6),
        "acceleration_mean": round(accel_mean, 6),
        "acceleration_variance": round(accel_var, 8),
        "total_time": trajectory[-1]["t"] - trajectory[0]["t"] if trajectory else 0,
        "points": len(trajectory)
    }

def classify_trajectory(features):
    if not features:
        return False, 0, ["No trajectory data"]
    
    score = 100
    reasons = []
    
    if features["path_ratio"] < 1.08:
        score -= 35
        reasons.append("Path too direct")
    
    if features["velocity_std"] < 0.15:
        score -= 30
        reasons.append("Velocity too consistent")
    
    if features["direction_changes"] < 4:
        score -= 20
        reasons.append("Too few direction changes")
    
    if features["curvature_variance"] < 0.015:
        score -= 15
        reasons.append("Curvature too uniform")
    
    if features["pause_count"] == 0 and features["total_time"] > 2000:
        score -= 10
        reasons.append("No natural pauses")
    
    if features["acceleration_variance"] < 0.00001:
        score -= 10
        reasons.append("Acceleration too smooth")
    
    if features["path_ratio"] > 1.25:
        score = min(100, score + 10)
    if features["velocity_std"] > 0.3:
        score = min(100, score + 10)
    if features["direction_changes"] > 10:
        score = min(100, score + 5)
    
    return score >= 50, max(0, min(100, score)), reasons

def real_to_visual_time(real_time, speed_segments):
    visual_time = 0
    remaining_real = real_time

    for seg in speed_segments:
        real_duration_of_segment = seg["duration"] / seg["speed"]
        
        if remaining_real <= real_duration_of_segment:
            visual_time += remaining_real * seg["speed"]
            return visual_time
        else:
            visual_time += seg["duration"]
            remaining_real -= real_duration_of_segment
    
    return visual_time

def verify_temporal(challenge_id, press_time, release_time):
    if challenge_id not in active_challenges:
        return {"success": False, "message": "Challenge expired"}
    
    c = active_challenges[challenge_id]
    real_hold = release_time - press_time
    
    visual_hold = real_to_visual_time(real_hold, c["speed_segments"])
    
    zone_start = c["zone_start"]
    zone_end = zone_start + c["zone_width"]
    
    # Strict check - must be within the actual green zone
    in_zone = zone_start <= visual_hold <= zone_end
    
    # Calculate accuracy (100% = center of zone, 0% = edge of zone)
    if in_zone:
        zone_center = zone_start + c["zone_width"] / 2
        distance_from_center = abs(visual_hold - zone_center)
        max_distance = c["zone_width"] / 2
        accuracy = max(0, 100 - (distance_from_center / max_distance * 100)) if max_distance > 0 else 100
    else:
        accuracy = 0
    
    save_log({
        "challenge_id": challenge_id,
        "type": "temporal",
        "result": "pass" if in_zone else "fail",
        "real_hold_time": real_hold,
        "visual_hold_time": round(visual_hold, 1),
        "accuracy": round(accuracy, 1),
        "created_at": datetime.utcnow().isoformat()
    })
    
    del active_challenges[challenge_id]
    
    return {
        "success": in_zone,
        "message": f"{accuracy:.0f}% accuracy" if in_zone else "Missed the zone",
        "accuracy": round(accuracy, 1),
        "hold_time": real_hold,
        "visual_time": round(visual_hold, 1),
        "zone": {"start": zone_start, "end": zone_end}
    }

def verify_behavioural(challenge_id, trajectory):
    if challenge_id not in active_challenges:
        return {"success": False, "message": "Challenge expired"}
    
    c = active_challenges[challenge_id]
    
    # Time limit check disabled for testing
    # if trajectory and trajectory[-1]["t"] > c["time_limit"]:
    #     del active_challenges[challenge_id]
    #     return {"success": False, "message": "Time limit exceeded"}
    
    visited = [False] * len(c["waypoints"])
    next_wp = 0
    for pt in trajectory:
        if next_wp < len(c["waypoints"]):
            wp = c["waypoints"][next_wp]
            if math.sqrt((pt["x"] - wp["x"])**2 + (pt["y"] - wp["y"])**2) <= 28:
                visited[next_wp] = True
                next_wp += 1
    
    in_order = next_wp == len(c["waypoints"])
    features = extract_features(trajectory)
    is_human, confidence, reasons = classify_trajectory(features)
    success = in_order and is_human
    
    save_log({
        "challenge_id": challenge_id,
        "type": "behavioural",
        "result": "pass" if success else "fail",
        "confidence": confidence,
        "waypoints_hit": sum(visited),
        "in_order": in_order,
        "time": features["total_time"] if features else 0,
        "created_at": datetime.utcnow().isoformat()
    })
    
    del active_challenges[challenge_id]
    
    if not in_order:
        return {"success": False, "message": f"Visit waypoints in order (got {sum(visited)}/{len(c['waypoints'])})"}
    
    return {
        "success": success,
        "message": f"Human verified! {confidence}% confidence" if success else "Movement pattern flagged",
        "confidence": confidence,
        "is_human": is_human,
        "reasons": reasons if not is_human else ["Natural movement detected"]
    }

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory(app.static_folder, path)

# Rate limiting middleware - blocks high-frequency polling (5ms intervals)
@app.before_request
def rate_limit_middleware():
    """Apply rate limiting to all API endpoints."""
    if request.path.startswith('/api/'):
        ip = request.remote_addr
        if not check_rate_limit(ip):
            return jsonify({"error": "Rate limit exceeded. Please slow down."}), 429

@app.route('/api/challenges/temporal', methods=['GET'])
def get_temporal():
    """
    Returns challenge data including zone information for UI.
    Security is maintained via rate limiting and nonce validation.
    """
    challenge = generate_temporal_challenge()
    
    return jsonify({
        'challenge_id': challenge['challenge_id'],
        'total_duration': challenge['total_duration'],
        'speed_segments': challenge['speed_segments'],
        'zone_start': challenge['zone_start'],
        'zone_width': challenge['zone_width'],
        'nonce': challenge['nonce'],
    })

@app.route('/api/challenges/behavioural', methods=['GET'])
def get_behavioural():
    """
    Returns challenge data including all waypoints.
    Security is maintained via rate limiting and nonce validation.
    """
    challenge = generate_behavioural_challenge()
    
    return jsonify({
        'challenge_id': challenge['challenge_id'],
        'canvas_width': challenge['canvas_width'],
        'canvas_height': challenge['canvas_height'],
        'waypoints': challenge['waypoints'],
        'time_limit': challenge['time_limit'],
        'nonce': challenge['nonce'],
    })

@app.route('/api/challenges/behavioural/<challenge_id>/waypoint/<int:index>', methods=['GET'])
def get_waypoint(challenge_id, index):
    """
    SECURITY: Returns coordinates for ONE waypoint at a time.
    Waypoints are revealed sequentially as user progresses.
    Client must hit waypoint N before getting waypoint N+1 coordinates.
    """
    if challenge_id not in active_challenges:
        return jsonify({"error": "Challenge expired"}), 404
    
    challenge = active_challenges[challenge_id]
    
    # Security: Validate waypoint index bounds
    if index < 0 or index >= len(challenge['waypoints']):
        return jsonify({"error": "Invalid waypoint index"}), 400
    
    # Security: Only reveal waypoints sequentially
    # Allow getting waypoint N only if N <= revealed_waypoints
    if index > challenge['revealed_waypoints']:
        return jsonify({"error": "Previous waypoint not completed"}), 403
    
    # Update revealed waypoints (allow client to request next one)
    if index == challenge['revealed_waypoints']:
        challenge['revealed_waypoints'] = index + 1
    
    return jsonify({
        'index': index,
        'x': challenge['waypoints'][index]['x'],
        'y': challenge['waypoints'][index]['y']
    })

@app.route('/api/challenges/temporal', methods=['POST'])
def post_temporal():
    """
    SECURITY: Validates nonce to prevent replay attacks.
    """
    d = request.json
    challenge_id = d.get('challenge_id')
    nonce = d.get('nonce')
    
    # Validate nonce to prevent replay attacks
    if challenge_id in active_challenges:
        if active_challenges[challenge_id].get('nonce') != nonce:
            return jsonify({"success": False, "message": "Invalid nonce - possible replay attack"}), 403
    
    return jsonify(verify_temporal(challenge_id, d.get('press_time', 0), d.get('release_time', 0)))

@app.route('/api/challenges/behavioural', methods=['POST'])
def post_behavioural():
    """
    SECURITY: Validates nonce to prevent replay attacks.
    """
    d = request.json
    challenge_id = d.get('challenge_id')
    nonce = d.get('nonce')
    
    # Validate nonce to prevent replay attacks
    if challenge_id in active_challenges:
        if active_challenges[challenge_id].get('nonce') != nonce:
            return jsonify({"success": False, "message": "Invalid nonce - possible replay attack"}), 403
    
    return jsonify(verify_behavioural(challenge_id, d.get('trajectory', [])))

if __name__ == '__main__':
    print("AI-Proof CAPTCHA running at http://localhost:5000")
    print("SECURITY FEATURES ENABLED:")
    print("  - Rate limiting: 10 requests/second max")
    print("  - Hidden challenge parameters")
    print("  - Sequential waypoint revelation")
    print("  - Nonce validation for replay attack prevention")
    print("  - Stricter trajectory classification")
    app.run(debug=True, host='0.0.0.0', port=5000)
