"""Application entry point for the Bitbucket PR Test Generator service."""

import logging
import sys
from pathlib import Path

# Ensure the src directory is on the import path when running directly
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import uvicorn

from pr_test_generator.settings import load_settings
from pr_test_generator.bitbucket_client import BitbucketClient
from pr_test_generator.analyzer import PRAnalyzer
from pr_test_generator.jobs import JobManager
from pr_test_generator.api import create_app

# Configure logging with ISO 8601 timestamps
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S%z",
)

# Load settings (will terminate if credentials are missing)
settings = load_settings()

# Initialize components
client = BitbucketClient(settings)
analyzer = PRAnalyzer(client, settings)
job_manager = JobManager(analyzer_fn=analyzer.analyze)

# Create FastAPI app
app = create_app(job_manager)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
