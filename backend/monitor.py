import psutil
import time
import threading
import json
from collections import deque
from datetime import datetime


class NetworkMonitor:
    def __init__(self):
        self.lock = threading.Lock()
        self.running = False

        # Speed tracking
        self.download_speed = 0.0   # bytes/sec
        self.upload_speed = 0.0     # bytes/sec

        # Historical data for sparklines (last 60 samples)
        self.dl_history = deque([0] * 60, maxlen=60)
        self.ul_history = deque([0] * 60, maxlen=60)

        # Session totals (accurate — from net_io_counters diff)
        self.session_start = time.time()
        self.session_downloaded = 0
        self.session_uploaded = 0

        # Per-app tracking
        # pid -> {name, total_recv, total_sent, dl_speed, ul_speed}
        self.app_data = {}

        # Peak speeds
        self.peak_download = 0.0
        self.peak_upload = 0.0

        # Session baseline (so totals start from 0 at launch)
        init_net = psutil.net_io_counters()
        self._session_base_recv = init_net.bytes_recv
        self._session_base_sent = init_net.bytes_sent

        # Detect whether psutil supports per-process net IO on this OS
        # Linux supports it; Windows/macOS do NOT
        self._has_proc_net_io = self._check_proc_net_io()

    # INIT HELPERS

    def _check_proc_net_io(self):
        """
        Check once at startup whether proc.net_io_counters() works.
        On Windows/macOS this raises AttributeError — we detect that here
        so we don't waste time trying every loop iteration.
        """
        for p in psutil.process_iter():
            try:
                p.net_io_counters()
                return True
            except AttributeError:
                # psutil doesn't support this on this OS at all
                return False
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                # Process-level denial — feature exists but denied for this proc
                # Keep trying other processes
                continue
        return False

    # MAIN LOOP

    def _update_loop(self):
        """
        Main data collection loop.
        Uses real elapsed time (not hardcoded 1.0) to avoid drift errors
        in speed and total byte calculations.
        """
        prev_net = psutil.net_io_counters()
        prev_proc_io = {}   # pid -> {name, sent, recv}
        prev_time = time.time()

        while self.running:
            time.sleep(1.0)
            now = time.time()
            # Real interval — accounts for sleep drift
            interval = now - prev_time
            prev_time = now

            if interval <= 0:
                continue

            #  Global network stats 
            curr_net = psutil.net_io_counters()

            dl = max(0, (curr_net.bytes_recv - prev_net.bytes_recv) / interval)
            ul = max(0, (curr_net.bytes_sent - prev_net.bytes_sent) / interval)

            #  Per-process stats 
            curr_proc_io = {}
            app_speeds = {}

            if self._has_proc_net_io:
                # Linux only — real per-process byte counters
                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        pid = proc.pid
                        name = (proc.info.get('name') or 'Unknown')[:28]

                        try:
                            io = proc.net_io_counters()
                            curr_sent = io.bytes_sent
                            curr_recv = io.bytes_recv
                        except (AttributeError, psutil.AccessDenied, psutil.NoSuchProcess):
                            continue

                        curr_proc_io[pid] = {
                            'name': name,
                            'sent': curr_sent,
                            'recv': curr_recv
                        }

                        if pid in prev_proc_io:
                            prev = prev_proc_io[pid]

                            # Raw byte difference — NOT speed added to total
                            raw_recv_diff = max(0, curr_recv - prev['recv'])
                            raw_sent_diff = max(0, curr_sent - prev['sent'])

                            proc_dl = raw_recv_diff / interval
                            proc_ul = raw_sent_diff / interval

                            if proc_dl > 0 or proc_ul > 0:
                                existing = self.app_data.get(pid, {
                                    'name': name,
                                    'total_recv': 0,
                                    'total_sent': 0,
                                    'dl_speed': 0,
                                    'ul_speed': 0
                                })
                                existing['name'] = name
                                existing['dl_speed'] = proc_dl
                                existing['ul_speed'] = proc_ul
                                # Accumulate actual bytes, not speed values
                                existing['total_recv'] = existing.get('total_recv', 0) + raw_recv_diff
                                existing['total_sent'] = existing.get('total_sent', 0) + raw_sent_diff
                                app_speeds[pid] = existing

                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        continue

            else:
                # Windows / macOS — psutil cannot track per-process net IO
                # We distribute global traffic proportionally by connection count
                # This is an ESTIMATE only — labelled clearly in the UI
                conn_map = {}  # pid -> connection count
                try:
                    for conn in psutil.net_connections(kind='inet'):
                        if conn.pid and conn.status == 'ESTABLISHED':
                            conn_map[conn.pid] = conn_map.get(conn.pid, 0) + 1
                except (psutil.AccessDenied, PermissionError):
                    pass

                total_conns = sum(conn_map.values()) or 1
                global_dl_bytes = max(0, curr_net.bytes_recv - prev_net.bytes_recv)
                global_ul_bytes = max(0, curr_net.bytes_sent - prev_net.bytes_sent)

                for pid, n_conns in conn_map.items():
                    try:
                        proc = psutil.Process(pid)
                        name = (proc.name() or 'Unknown')[:28]
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue

                    # Proportional share of global traffic
                    share = n_conns / total_conns
                    recv_share = global_dl_bytes * share
                    sent_share = global_ul_bytes * share

                    proc_dl = recv_share / interval
                    proc_ul = sent_share / interval

                    curr_proc_io[pid] = {'name': name, 'sent': 0, 'recv': 0}

                    if proc_dl > 0 or proc_ul > 0:
                        existing = self.app_data.get(pid, {
                            'name': name,
                            'total_recv': 0,
                            'total_sent': 0,
                            'dl_speed': 0,
                            'ul_speed': 0
                        })
                        existing['name'] = name
                        existing['dl_speed'] = proc_dl
                        existing['ul_speed'] = proc_ul
                        existing['total_recv'] = existing.get('total_recv', 0) + recv_share
                        existing['total_sent'] = existing.get('total_sent', 0) + sent_share
                        app_speeds[pid] = existing

            prev_proc_io = curr_proc_io

            #  Write to shared state 
            with self.lock:
                self.download_speed = dl
                self.upload_speed = ul
                self.dl_history.append(dl)
                self.ul_history.append(ul)

                # Session totals — always accurate (from baseline diff)
                self.session_downloaded = curr_net.bytes_recv - self._session_base_recv
                self.session_uploaded = curr_net.bytes_sent - self._session_base_sent

                # Peaks
                if dl > self.peak_download:
                    self.peak_download = dl
                if ul > self.peak_upload:
                    self.peak_upload = ul

                # Merge new app speeds
                for pid, data in app_speeds.items():
                    self.app_data[pid] = data

                # Zero out speed for dead processes (keep their total data)
                alive_pids = set(curr_proc_io.keys())
                for pid in list(self.app_data.keys()):
                    if pid not in alive_pids:
                        self.app_data[pid]['dl_speed'] = 0
                        self.app_data[pid]['ul_speed'] = 0

            prev_net = curr_net


    # PUBLIC API

    def start(self):
        self.running = True
        t = threading.Thread(target=self._update_loop, daemon=True)
        t.start()

    def stop(self):
        self.running = False

    def get_snapshot(self):
        """Return current state as a JSON-serialisable dict."""
        with self.lock:
            apps = []
            for pid, d in self.app_data.items():
                total_recv = d.get('total_recv', 0)
                total_sent = d.get('total_sent', 0)
                # Only include processes that have had some activity
                if d['dl_speed'] > 0 or d['ul_speed'] > 0 or total_recv > 0 or total_sent > 0:
                    apps.append({
                        'pid': pid,
                        'name': d['name'],
                        'dl_speed': d['dl_speed'],
                        'ul_speed': d['ul_speed'],
                        'total_recv': total_recv,
                        'total_sent': total_sent,
                        'total': total_recv + total_sent,
                    })

            # Top 3 by CURRENT speed (last 1s sample)
            by_speed = sorted(
                apps,
                key=lambda x: x['dl_speed'] + x['ul_speed'],
                reverse=True
            )

            # Top 3 by TOTAL bytes transferred this session
            by_usage = sorted(
                apps,
                key=lambda x: x['total'],
                reverse=True
            )

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
                'proc_net_io_supported': self._has_proc_net_io,
                'all_apps': apps[:20],
                'top_speed_apps': by_speed[:3],
                'top_usage_apps': by_usage[:3],
            }