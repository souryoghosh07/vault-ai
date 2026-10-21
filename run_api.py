import os
import sys
import multiprocessing
import uvicorn

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src-python')))

from app.main import app

if __name__ == '__main__':
    # Required for PyInstaller to handle multithreading safely
    multiprocessing.freeze_support()
    # Run the server on port 8000
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False, workers=1)