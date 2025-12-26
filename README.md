# AI-Proof CAPTCHA

Human verification system using temporal perception and behavioural analysis.

## Challenges

- **Temporal**: Hold and release timing with difficulty levels
- **Behavioural**: Mouse trajectory analysis with time limits

## Setup

```bash
pip install flask flask-cors
python backend/app.py
```

Open http://localhost:5000

## API

| Endpoint | Method | Params |
|----------|--------|--------|
| `/api/challenges/temporal` | GET | `?difficulty=easy\|medium\|hard` |
| `/api/challenges/temporal` | POST | `{challenge_id, press_time, release_time}` |
| `/api/challenges/behavioural` | GET | `?difficulty=easy\|medium\|hard` |
| `/api/challenges/behavioural` | POST | `{challenge_id, trajectory}` |
