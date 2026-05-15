FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sync_vault.py .

# Default: run loop mode. Container reads DB from /app/data/diary.db (mounted)
# and writes state to /app/state/vault_sync_state.json (mounted).
CMD ["python", "sync_vault.py", "loop"]
