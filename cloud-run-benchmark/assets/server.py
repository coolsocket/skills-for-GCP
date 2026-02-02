import os
import time
import json
import threading
import queue
import concurrent.futures
import logging
from flask import Flask, jsonify, request
import shutil

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("server.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- Configuration ---
# Allow overriding via Env Vars
MOUNT_PATH = os.environ.get("MOUNT_PATH", "/mnt/data")
MODEL_FILE = os.environ.get("MODEL_FILE", "model.bin")
# Internal flags
USE_SYNTHETIC = os.environ.get("USE_SYNTHETIC", "false").lower() == "true"
SYNTHETIC_SIZE_GB = float(os.environ.get("SYNTHETIC_SIZE_GB", "10.0"))
CHUNK_SIZE_MB = int(os.environ.get("CHUNK_SIZE_MB", "100)) # 100MB chunks
NUM_THREADS = int(os.environ.get("NUM_THREADS", "4"))

# Global State
STATE = {
    "status": "idle", # idle, running, completed, error
    "config": {
        "mount_path": MOUNT_PATH,
        "model_file": MODEL_FILE,
        "use_synthetic": USE_SYNTHETIC,
        "threads": NUM_THREADS,
        "gpu_available": False
    },
    "metrics": {
        "start_time": 0,
        "end_time": 0,
        "duration_sec": 0,
        "total_bytes": 0,
        "throughput_mb_s": 0,
        "vram_used_gb": 0,
        "files_processed": 0
    },
    "error": None
}

# GPU Check
try:
    import torch
    if torch.cuda.is_available():
        STATE["config"]["gpu_available"] = True
except ImportError:
    pass

# Metric Storage
KEPT_DATA = [] # To prevent GC if needed, or we just discard

def perform_benchmark():
    global STATE
    STATE["status"] = "running"
    STATE["metrics"]["start_time"] = time.time()
    STATE["metrics"]["total_bytes"] = 0
    
    logger.info(f"Starting benchmark. Config: {STATE['config']}")
    
    try:
        # 1. Identify Source
        target_files = []
        if USE_SYNTHETIC:
            logger.info(f"Using SYNTHETIC data ({SYNTHETIC_SIZE_GB} GB)")
            # Generator logic handled in consumer
        else:
            full_path = os.path.join(MOUNT_PATH, MODEL_FILE)
            if os.path.isdir(full_path):
                for root, _, files in os.walk(full_path):
                    for f in files:
                        target_files.append(os.path.join(root, f))
            elif os.path.isfile(full_path):
                target_files = [full_path]
            else:
                raise FileNotFoundError(f"Source not found: {full_path}")
            
            logger.info(f"Found {len(target_files)} files to read.")

        # 2. Pipeline Components
        q = queue.Queue(maxsize=NUM_THREADS * 2)
        stop_event = threading.Event()
        
        # Producer (IO)
        def producer():
            total_read = 0
            chunk_size = CHUNK_SIZE_MB * 1024 * 1024
            
            if USE_SYNTHETIC:
                # Synthetic Generator
                target_bytes = int(SYNTHETIC_SIZE_GB * 1024**3)
                while total_read < target_bytes and not stop_event.is_set():
                    # Generate dummy chunk
                    # faster to use pre-allocated buffer? 
                    chunk = b'0' * chunk_size 
                    q.put(chunk)
                    total_read += len(chunk)
            else:
                # File Reader
                def read_file(fp):
                    try:
                        with open(fp, "rb") as f:
                            while not stop_event.is_set():
                                chunk = f.read(chunk_size)
                                if not chunk: break
                                q.put(chunk)
                    except Exception as e:
                        logger.error(f"Error reading {fp}: {e}")
                        raise e

                with concurrent.futures.ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
                    futures = [executor.submit(read_file, fp) for fp in target_files]
                    concurrent.futures.wait(futures)
            
            q.put(None) # Sentinel

        # Consumer (GPU/Memory)
        def consumer():
            total_processed = 0
            while True:
                chunk = q.get()
                if chunk is None: break
                
                # Check GPU
                if STATE["config"]["gpu_available"]:
                    try:
                        t = torch.frombuffer(chunk, dtype=torch.uint8).to("cuda:0", non_blocking=True)
                        # Optionally keep or sync
                        # KEPT_DATA.append(t) # Warning: Fast OOM if we keep everything
                        # Instead, just sync periodically to force transfer
                        if total_processed % (1024**3) < len(chunk): # Sync every 1GB roughly
                             torch.cuda.synchronize()
                    except Exception as e:
                        logger.error(f"GPU Error: {e}")
                        # Don't fail benchmark, just log? Or fail?
                        # OOM is a common "benchmark result", so handle gracefully?
                        pass

                total_processed += len(chunk)
                STATE["metrics"]["total_bytes"] = total_processed
                
                # Update realtime throughput
                duration = time.time() - STATE["metrics"]["start_time"]
                if duration > 1:
                    STATE["metrics"]["throughput_mb_s"] = (total_processed / 1024**2) / duration
            
            return total_processed

        # Start Threads
        prod_thread = threading.Thread(target=producer)
        prod_thread.start()
        
        consumer() # Run consumer in main thread (of this function)
        
        prod_thread.join()
        
        # Finish
        duration = time.time() - STATE["metrics"]["start_time"]
        STATE["metrics"]["end_time"] = time.time()
        STATE["metrics"]["duration_sec"] = duration
        STATE["metrics"]["throughput_mb_s"] = (STATE["metrics"]["total_bytes"] / 1024**2) / duration
        STATE["status"] = "completed"
        logger.info(f"Benchmark finished. {STATE['metrics']['throughput_mb_s']:.2f} MB/s")

    except Exception as e:
        logger.error(f"Benchmark failed: {e}")
        STATE["status"] = "error"
        STATE["error"] = str(e)

# Auto-start if configured
if os.environ.get("AUTO_START", "false").lower() == "true":
    threading.Thread(target=perform_benchmark).start()

@app.route("/")
def health():
    return jsonify(STATE)

@app.route("/start", methods=["POST"])
def start_trigger():
    if STATE["status"] == "running":
         return jsonify({"error": "Already running"}), 400
    
    # Allow config overrides
    data = request.json or {}
    if "synthetic_size_gb" in data:
        global SYNTHETIC_SIZE_GB
        SYNTHETIC_SIZE_GB = float(data["synthetic_size_gb"])
        
    threading.Thread(target=perform_benchmark).start()
    return jsonify({"status": "started"})

@app.route("/report")
def get_report():
    return jsonify({
        "timestamp": time.time(),
        "state": STATE
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
