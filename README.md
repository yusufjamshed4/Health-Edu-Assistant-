cp .env.example backend/.env      # set GOOGLE_API_KEY and JWT_SECRET (32+ chars)
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python ingest.py --reset          # indexes ./data
uvicorn app.main:app --reload     # http://localhost:8000/docs

cd backend
pytest                              # offline: safety, lab ranges, rate limiter (no API key)
python -m eval.run_eval             # live: emergency/scope/grounding/out-of-scope cases
python -m eval.run_eval --judge     # adds LLM-as-judge faithfulness check
