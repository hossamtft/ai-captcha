from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import json, uuid, math, random, os
from datetime import datetime

app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
os.makedirs(DATA_DIR, exist_ok=True)
active_challenges = {}
LOGS_FILE = os.path.join(DATA_DIR, 'attempts.json')

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

def generate_temporal_challenge(difficulty='medium'):
    seed = random.randint(1, 1000000)
    random.seed(seed)
    
    if difficulty == 'easy':
        total_duration = random.randint(5000, 7000)
        zone_width = random.randint(400, 600)
        flicker_speed = 800
    elif difficulty == 'hard':
        total_duration = random.randint(3000, 5000)
        zone_width = random.randint(150, 250)
        flicker_speed = 250
    else:
        total_duration = random.randint(4000, 6000)
        zone_width = random.randint(250, 400)
        flicker_speed = 400
    
    zone_start_pct = random.uniform(0.20, 0.70)
    zone_start = int(total_duration * zone_start_pct)
    
    challenge_id = str(uuid.uuid4())
    challenge = {
        "challenge_id": challenge_id,
        "type": "temporal",
        "difficulty": difficulty,
        "seed": seed,
        "total_duration": total_duration,
        "zone_start": zone_start,
        "zone_width": zone_width,
        "flicker_speed": flicker_speed,
        "tolerance": 80 if difficulty == 'hard' else 120,
        "created_at": datetime.utcnow().isoformat()
    }
    active_challenges[challenge_id] = challenge
    return challenge

def generate_behavioural_challenge(difficulty='medium'):
    seed = random.randint(1, 1000000)
    random.seed(seed)
    
    if difficulty == 'easy':
        num_waypoints = random.randint(3, 4)
        min_distance = 100
        time_limit = 15000
    elif difficulty == 'hard':
        num_waypoints = random.randint(6, 8)
        min_distance = 70
        time_limit = 8000
    else:
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
        "difficulty": difficulty,
        "seed": seed,
        "waypoints": waypoints,
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

def classify_trajectory(features, difficulty='medium'):
    if not features:
        return False, 0, ["No trajectory data"]
    
    score = 100
    reasons = []
    
    thresholds = {
        'easy': {'ratio': 1.03, 'vel_std': 0.08, 'dir': 2, 'curv': 0.008},
        'medium': {'ratio': 1.05, 'vel_std': 0.12, 'dir': 3, 'curv': 0.01},
        'hard': {'ratio': 1.08, 'vel_std': 0.15, 'dir': 4, 'curv': 0.015}
    }
    t = thresholds.get(difficulty, thresholds['medium'])
    
    if features["path_ratio"] < t['ratio']:
        score -= 35
        reasons.append("Path too direct")
    
    if features["velocity_std"] < t['vel_std']:
        score -= 30
        reasons.append("Velocity too consistent")
    
    if features["direction_changes"] < t['dir']:
        score -= 20
        reasons.append("Too few direction changes")
    
    if features["curvature_variance"] < t['curv']:
        score -= 15
        reasons.append("Curvature too uniform")
    
    if features["pause_count"] == 0 and features["total_time"] > 2000:
        score -= 10
        reasons.append("No natural pauses")
    
    if features["acceleration_variance"] < 0.00001:
        score -= 10
        reasons.append("Acceleration too smooth")
    
    if features["path_ratio"] > 1.2:
        score = min(100, score + 15)
    if features["velocity_std"] > 0.25:
        score = min(100, score + 10)
    if features["direction_changes"] > 8:
        score = min(100, score + 5)
    if features["pause_count"] >= 2:
        score = min(100, score + 5)
    
    return score >= 50, max(0, min(100, score)), reasons

def verify_temporal(challenge_id, press_time, release_time):
    if challenge_id not in active_challenges:
        return {"success": False, "message": "Challenge expired"}
    
    c = active_challenges[challenge_id]
    hold = release_time - press_time
    zone_end = c["zone_start"] + c["zone_width"]
    tolerance = c.get("tolerance", 100)
    
    in_zone = (c["zone_start"] - tolerance) <= hold <= (zone_end + tolerance)
    
    accuracy = 0
    if in_zone:
        zone_center = c["zone_start"] + c["zone_width"] / 2
        distance_from_center = abs(hold - zone_center)
        max_distance = c["zone_width"] / 2 + tolerance
        accuracy = max(0, 100 - (distance_from_center / max_distance * 100))
    
    save_log({
        "challenge_id": challenge_id,
        "type": "temporal",
        "difficulty": c["difficulty"],
        "result": "pass" if in_zone else "fail",
        "hold_time": hold,
        "accuracy": round(accuracy, 1),
        "created_at": datetime.utcnow().isoformat()
    })
    
    del active_challenges[challenge_id]
    
    return {
        "success": in_zone,
        "message": f"Perfect timing! {accuracy:.0f}% accuracy" if in_zone else "Missed the zone",
        "hold_time": hold,
        "accuracy": round(accuracy, 1),
        "zone": {"start": c["zone_start"], "end": zone_end}
    }

def verify_behavioural(challenge_id, trajectory):
    if challenge_id not in active_challenges:
        return {"success": False, "message": "Challenge expired"}
    
    c = active_challenges[challenge_id]
    
    if trajectory and trajectory[-1]["t"] > c["time_limit"]:
        del active_challenges[challenge_id]
        return {"success": False, "message": "Time limit exceeded"}
    
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
    is_human, confidence, reasons = classify_trajectory(features, c["difficulty"])
    success = in_order and is_human
    
    save_log({
        "challenge_id": challenge_id,
        "type": "behavioural",
        "difficulty": c["difficulty"],
        "result": "pass" if success else "fail",
        "confidence": confidence,
        "waypoints_hit": sum(visited),
        "in_order": in_order,
        "time": features["total_time"] if features else 0,
        "features": features,
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
        "reasons": reasons if not is_human else ["Natural movement detected"],
        "features": features
    }

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory(app.static_folder, path)

@app.route('/api/challenges/temporal', methods=['GET'])
def get_temporal():
    difficulty = request.args.get('difficulty', 'medium')
    return jsonify(generate_temporal_challenge(difficulty))

@app.route('/api/challenges/behavioural', methods=['GET'])
def get_behavioural():
    difficulty = request.args.get('difficulty', 'medium')
    return jsonify(generate_behavioural_challenge(difficulty))

@app.route('/api/challenges/temporal', methods=['POST'])
def post_temporal():
    d = request.json
    return jsonify(verify_temporal(d.get('challenge_id'), d.get('press_time', 0), d.get('release_time', 0)))

@app.route('/api/challenges/behavioural', methods=['POST'])
def post_behavioural():
    d = request.json
    return jsonify(verify_behavioural(d.get('challenge_id'), d.get('trajectory', [])))

if __name__ == '__main__':
    print("AI-Proof CAPTCHA running at http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
