import os
import sys
import multiprocessing

# Tell the Hugging Face hub to operate completely offline BEFORE anything else loads
os.environ["HF_HUB_OFFLINE"] = "1"

# If running as a compiled PyInstaller executable, reroute the cache to the internal temp folder
if getattr(sys, 'frozen', False):
    os.environ["HF_HOME"] = os.path.join(sys._MEIPASS, "hf_cache")

import uvicorn

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src-python')))

from app.main import app

if __name__ == '__main__':
    # Required for PyInstaller to handle multithreading safely
    multiprocessing.freeze_support()
    # Run the server on port 8000
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False, workers=1)