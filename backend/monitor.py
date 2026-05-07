"""
NetWatch - Network Monitor Backend
Real-time network data collection engine using psutil
"""

import psutil
import time
import threading
import json
from collections import defaultdict, deque
from datetime import datetime

class NetworkMonitor:
    def __init__(self):
        self.lock = threading.Lock()
        self.running = False
        
        # Speed tracking
        self.download_speed = 0.0   # bytes/sec
        self.upload_speed = 0.0     # bytes/sec
        
        # Historical data for sparklines (last 60 samples)
        self.dl_history = deque([0]*60, maxlen=60)
        self.ul_history = deque([0]*60, maxlen=60)
        
        # Session totals
        self.session_start = time.time()
        self.session_downloaded = 0
        self.session_uploaded = 0
        
        # Per-app tracking
        self.app_data = {}          # pid -> {name, sent, recv, dl_speed, ul_speed}
        self.app_history = {}       # pid -> {dl_history, ul_history}
        
        # Previous snapshots
        self._prev_net = None
        self._prev_proc = {}        # pid -> (sent, recv, time)
        self._prev_time = None
        
        # Peak speeds
        self.peak_download = 0.0
        self.peak_upload = 0.0
        
        # Total bytes (system lifetime)
        self._init_net = psutil.net_io_counters()
        self._session_base_recv = self._init_net.bytes_recv
        self._session_base_sent = self._init_net.bytes_sent

    def _get_process_name(self, proc):
        """Get clean process name"""
        try:
            name = proc.name()
            # Clean up common suffixes
            for suffix in ['.exe', 'd', 'Helper', '-bin']:
                if name.endswith(suffix) and len(name) > len(suffix) + 2:
                    pass  # Keep original name
            return name[:32] if name else "Unknown"
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None

    def _collect_process_io(self):
        """Sample per-process network I/O (Linux uses /proc, may need net_connections)"""
        proc_data = {}
        now = time.time()
        
        for proc in psutil.process_iter(['pid', 'name', 'status']):
            try:
                pid = proc.pid
                name = proc.info.get('name', 'Unknown')
                if not name:
                    continue
                    
                # Try to get net io counters per process
                try:
                    io = proc.net_io_counters()
                    sent = io.bytes_sent
                    recv = io.bytes_recv
                except (AttributeError, psutil.AccessDenied, psutil.NoSuchProcess):
                    # Fallback: use connections count as proxy
                    try:
                        conns = proc.connections()
                        if not conns:
                            continue
                        # Estimate based on connection count (rough proxy)
                        sent = len(conns) * 1024  # placeholder
                        recv = len(conns) * 2048  # placeholder
                    except (psutil.AccessDenied, psutil.NoSuchProcess):
                        continue
                
                proc_data[pid] = {
                    'name': name[:28],
                    'sent': sent,
                    'recv': recv,
                    'time': now
                }
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        
        return proc_data

    def _update_loop(self):
        """Main data collection loop - runs every 1 second"""
        prev_net = psutil.net_io_counters()
        prev_proc_io = {}
        
        # Try to get per-process net IO support
        test_proc = None
        has_proc_net_io = False
        for p in psutil.process_iter():
            try:
                p.net_io_counters()
                has_proc_net_io = True
                break
            except (AttributeError, psutil.AccessDenied, psutil.NoSuchProcess):
                break
        
        while self.running:
            time.sleep(1.0)
            now = time.time()
            
            # --- Global network stats ---
            curr_net = psutil.net_io_counters()
            interval = 1.0
            
            dl = max(0, (curr_net.bytes_recv - prev_net.bytes_recv) / interval)
            ul = max(0, (curr_net.bytes_sent - prev_net.bytes_sent) / interval)
            
            # --- Per-process stats ---
            curr_proc_io = {}
            app_speeds = {}
            
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    pid = proc.pid
                    name = (proc.info.get('name') or 'Unknown')[:28]
                    
                    if has_proc_net_io:
                        try:
                            io = proc.net_io_counters()
                            curr_sent = io.bytes_sent
                            curr_recv = io.bytes_recv
                        except (AttributeError, psutil.AccessDenied, psutil.NoSuchProcess):
                            continue
                    else:
                        # Fallback: distribute global traffic by connection count
                        try:
                            conns = proc.connections()
                            n_conns = len(conns)
                            if n_conns == 0:
                                continue
                            curr_sent = n_conns * 10000  # scaled placeholder
                            curr_recv = n_conns * 20000
                        except (psutil.AccessDenied, psutil.NoSuchProcess):
                            continue
                    
                    curr_proc_io[pid] = {'name': name, 'sent': curr_sent, 'recv': curr_recv}
                    
                    if pid in prev_proc_io:
                        prev = prev_proc_io[pid]
                        proc_dl = max(0, (curr_recv - prev['recv']) / interval)
                        proc_ul = max(0, (curr_sent - prev['sent']) / interval)
                        
                        if proc_dl > 0 or proc_ul > 0:
                            # Accumulate totals
                            existing = self.app_data.get(pid, {
                                'name': name, 'total_recv': 0, 'total_sent': 0,
                                'dl_speed': 0, 'ul_speed': 0
                            })
                            existing['name'] = name
                            existing['dl_speed'] = proc_dl
                            existing['ul_speed'] = proc_ul
                            existing['total_recv'] = existing.get('total_recv', 0) + proc_dl
                            existing['total_sent'] = existing.get('total_sent', 0) + proc_ul
                            app_speeds[pid] = existing
                            
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
            
            prev_proc_io = curr_proc_io
            
            with self.lock:
                self.download_speed = dl
                self.upload_speed = ul
                self.dl_history.append(dl)
                self.ul_history.append(ul)
                
                # Session totals
                self.session_downloaded = curr_net.bytes_recv - self._session_base_recv
                self.session_uploaded = curr_net.bytes_sent - self._session_base_sent
                
                # Peaks
                if dl > self.peak_download:
                    self.peak_download = dl
                if ul > self.peak_upload:
                    self.peak_upload = ul
                
                # Merge app speeds into persistent dict
                for pid, data in app_speeds.items():
                    self.app_data[pid] = data
                
                # Cleanup dead processes
                alive_pids = set(curr_proc_io.keys())
                dead = [p for p in self.app_data if p not in alive_pids]
                for p in dead:
                    # Keep data but zero speed
                    self.app_data[p]['dl_speed'] = 0
                    self.app_data[p]['ul_speed'] = 0
                
            prev_net = curr_net

    def start(self):
        self.running = True
        t = threading.Thread(target=self._update_loop, daemon=True)
        t.start()

    def stop(self):
        self.running = False

    def get_snapshot(self):
        """Return current state as dict"""
        with self.lock:
            # Build app list - active only (speed > 0 or recently active)
            apps = []
            for pid, d in self.app_data.items():
                if d['dl_speed'] > 0 or d['ul_speed'] > 0 or d.get('total_recv', 0) > 0:
                    apps.append({
                        'pid': pid,
                        'name': d['name'],
                        'dl_speed': d['dl_speed'],
                        'ul_speed': d['ul_speed'],
                        'total_recv': d.get('total_recv', 0),
                        'total_sent': d.get('total_sent', 0),
                        'total': d.get('total_recv', 0) + d.get('total_sent', 0),
                    })
            
            # Sort for top lists
            by_speed = sorted(apps, key=lambda x: x['dl_speed'] + x['ul_speed'], reverse=True)
            by_usage = sorted(apps, key=lambda x: x['total'], reverse=True)
            
            elapsed = time.time() - self.session_start
            
            return {
                'timestamp': datetime.now().isoformat(),
                'elapsed_seconds': int(elapsed),
                'download_speed': self.download_speed,
                'upload_speed': self.upload_speed,
                'peak_download': self.peak_download,
                'peak_upload': self.peak_upload,
                'session_downloaded': self.session_downloaded,
                'session_uploaded': self.session_uploaded,
                'dl_history': list(self.dl_history),
                'ul_history': list(self.ul_history),
                'all_apps': apps[:20],          # top 20 for main view
                'top_speed_apps': by_speed[:3],  # top 3 by speed
                'top_usage_apps': by_usage[:3],  # top 3 by data used
            }
