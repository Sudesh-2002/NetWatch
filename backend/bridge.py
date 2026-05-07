import json
import time
from monitor import NetworkMonitor

monitor = NetworkMonitor()
monitor.start()

while True:
    data = monitor.get_snapshot()
    print(json.dumps(data), flush=True)
    time.sleep(1)