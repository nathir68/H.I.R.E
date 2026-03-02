import json

LOG_FILE = "system_logs.json"

# Empty the logs by writing an empty list
with open(LOG_FILE, 'w') as f:
    json.dump([], f)

print("✅ System logs completely wiped clean! The Admin God View is now a clean slate. 🚀")