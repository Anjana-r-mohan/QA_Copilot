#!/usr/bin/env python3
"""
QA Copilot FastAPI Server
REST API for use in IntelliJ or any IDE
"""

from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional
import os
import sys
import shutil
import json
import asyncio
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add agents to path
sys.path.insert(0, os.path.dirname(__file__))

from agents.test_plan_agent import TestPlanAgent
from agents.codebase_explorer_agent import CodebaseExplorerAgent
from agents.ui_explorer_agent import UIExplorerAgent
from agents.test_generator_agent import TestGeneratorAgent
from agents.test_executor_agent import TestExecutorAgent
from agents.ai_test_navigator_agent import AITestNavigatorAgent

app = FastAPI(
    title="QA Copilot API",
    description="AI-Powered QA Automation for Mobile Apps",
    version="1.0.0"
)

# Enable CORS for IntelliJ HTTP Client
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize agents
test_plan_agent = TestPlanAgent()
codebase_explorer = CodebaseExplorerAgent()
ui_explorer = UIExplorerAgent()
test_generator = TestGeneratorAgent()
test_executor = TestExecutorAgent(ui_explorer)
ai_navigator = AITestNavigatorAgent(ui_explorer)


class AnalyzeRequest(BaseModel):
    repo_path: str


class CloneRequest(BaseModel):
    repo_url: str
    target_path: Optional[str] = "./repo"


class LocatorRequest(BaseModel):
    platform: Optional[str] = "both"


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "QA Copilot API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "parse_csv": "POST /api/parse-csv",
            "analyze": "POST /api/analyze",
            "clone": "POST /api/clone-and-analyze",
            "locators": "GET /api/locators",
            "test_plan": "GET /api/test-plan"
        }
    }


@app.get("/health")
async def health():
    """Health check"""
    return {"status": "healthy"}


@app.post("/api/parse-csv")
async def parse_csv(file: UploadFile = File(...), workspace_path: str = Form(None)):
    """
    Parse CSV file with test cases
    
    Upload a CSV file with columns:
    Test ID, Feature, Test Case Name, Steps, Expected Result, Priority, Platform
    
    Optional form field:
    - workspace_path: Path where to create test_plans directory (defaults to current directory)
    """
    try:
        # Determine where to save files
        if workspace_path and os.path.exists(workspace_path):
            base_path = workspace_path
        else:
            base_path = os.getcwd()
        
        # Save uploaded file
        uploads_dir = os.path.join(base_path, "uploads")
        os.makedirs(uploads_dir, exist_ok=True)
        file_path = os.path.join(uploads_dir, file.filename)
        
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        
        # Parse CSV
        test_cases = test_plan_agent.parse_csv(file_path)
        
        # Group by feature
        features = test_plan_agent.group_by_feature()
        
        # Generate test plan in the workspace with unique name
        test_plans_dir = os.path.join(base_path, "test_plans")
        os.makedirs(test_plans_dir, exist_ok=True)
        
        # Use CSV filename for unique test plan name
        test_plan_path = test_plan_agent.generate_test_plan(
            output_path=None,  # Let agent generate unique name
            csv_filename=file.filename,
            workspace_path=base_path  # Pass workspace path
        )
        
        return {
            "success": True,
            "message": "Test cases parsed successfully",
            "summary": {
                "total_test_cases": len(test_cases),
                "features": len(features),
                "test_plan_path": test_plan_path,
                "absolute_path": os.path.abspath(test_plan_path)
            },
            "features": {
                feature: len(tcs) for feature, tcs in features.items()
            },
            "test_cases": test_cases[:5]  # Return first 5 as sample
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/analyze")
async def analyze_codebase(request: AnalyzeRequest):
    """
    Analyze codebase to extract screens and locators
    
    Body:
    {
        "repo_path": "./path/to/repo"
    }
    """
    try:
        if not os.path.exists(request.repo_path):
            raise HTTPException(status_code=404, detail=f"Path not found: {request.repo_path}")
        
        # Analyze repository
        results = codebase_explorer.explore_repository(request.repo_path)
        
        return {
            "success": True,
            "message": "Codebase analyzed successfully",
            "summary": {
                "total_screens": len(results['screens']),
                "total_locators": len(results['locators']),
                "android_screens": len([s for s in results['screens'].values() if s['platform'] == 'android']),
                "ios_screens": len([s for s in results['screens'].values() if s['platform'] == 'ios'])
            },
            "screens": list(results['screens'].keys()),
            "sample_locators": results['locators'][:10],
            "data_files": {
                "feature_map": "data/feature_map.json",
                "locators": "data/locators.json"
            }
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/clone-and-analyze")
async def clone_and_analyze(request: CloneRequest):
    """
    Clone repository and analyze it
    
    Body:
    {
        "repo_url": "https://bitbucket.org/bizom/bizom-kmm.git",
        "target_path": "./bizom_kmm"
    }
    """
    try:
        # Clone repository
        cloned_path = codebase_explorer.clone_repo(request.repo_url, request.target_path)
        
        if not cloned_path:
            raise HTTPException(status_code=500, detail="Failed to clone repository")
        
        # Analyze
        results = codebase_explorer.explore_repository(cloned_path)
        
        return {
            "success": True,
            "message": "Repository cloned and analyzed",
            "cloned_to": cloned_path,
            "summary": {
                "total_screens": len(results['screens']),
                "total_locators": len(results['locators'])
            },
            "screens": list(results['screens'].keys()),
            "sample_locators": results['locators'][:10]
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/locators")
async def get_locators(platform: str = "both"):
    """
    Get extracted locators
    
    Query params:
    - platform: android, ios, or both (default: both)
    """
    try:
        locators_file = "data/locators.json"
        
        if not os.path.exists(locators_file):
            raise HTTPException(status_code=404, detail="No locators found. Run analyze first.")
        
        import json
        with open(locators_file, 'r') as f:
            locators = json.load(f)
        
        # Filter by platform
        if platform != "both":
            locators = [loc for loc in locators if loc['platform'] == platform]
        
        return {
            "success": True,
            "platform": platform,
            "total": len(locators),
            "locators": locators
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/test-plan")
async def get_test_plan():
    """Get generated test plan"""
    try:
        test_plan_file = "test_plans/test_plan.md"
        
        if not os.path.exists(test_plan_file):
            raise HTTPException(status_code=404, detail="No test plan found. Parse CSV first.")
        
        return FileResponse(
            test_plan_file,
            media_type="text/markdown",
            filename="test_plan.md"
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/test-plan/json")
async def get_test_plan_json():
    """Get test plan as JSON"""
    try:
        test_plan_file = "test_plans/test_plan.md"
        
        if not os.path.exists(test_plan_file):
            raise HTTPException(status_code=404, detail="No test plan found. Parse CSV first.")
        
        with open(test_plan_file, 'r') as f:
            content = f.read()
        
        return {
            "success": True,
            "test_plan": content,
            "file_path": test_plan_file
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/feature-map")
async def get_feature_map():
    """Get feature map"""
    try:
        feature_map_file = "data/feature_map.json"
        
        if not os.path.exists(feature_map_file):
            raise HTTPException(status_code=404, detail="No feature map found. Run analyze first.")
        
        import json
        with open(feature_map_file, 'r') as f:
            feature_map = json.load(f)
        
        return {
            "success": True,
            "feature_map": feature_map
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/explore-ui")
async def explore_ui(request: dict):
    """
    Explore UI screens and extract elements from real emulator
    
    Body:
    {
        "screens": ["LoginScreen", "DashboardScreen"],  // Optional
        "platform": "android",
        "device_name": "emulator-5554",  // Optional
        "app_package": "com.bizom",      // Optional
        "app_activity": ".MainActivity"   // Optional
    }
    """
    try:
        screens = request.get('screens', None)
        platform = request.get('platform', 'android')
        device_name = request.get('device_name', 'emulator-5554')
        app_package = request.get('app_package', None)
        app_activity = request.get('app_activity', None)
        
        result = ui_explorer.explore_app(
            screens=screens,
            platform=platform,
            device_name=device_name,
            app_package=app_package,
            app_activity=app_activity
        )
        
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/disconnect-emulator")
async def disconnect_emulator():
    """Disconnect from emulator"""
    try:
        result = ui_explorer.disconnect()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/screenshot")
async def take_screenshot(request: dict):
    """
    Take screenshot of current screen
    
    Body:
    {
        "filename": "screenshot.png"  // Optional
    }
    """
    try:
        filename = request.get('filename', None)
        result = ui_explorer.take_screenshot(filename)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/generate-tests")
async def generate_tests(request: dict):
    """
    Generate test code from test plan and locators
    
    Body:
    {
        "test_cases": [...],
        "platform": "android"
    }
    """
    try:
        test_cases = request.get('test_cases', [])
        platform = request.get('platform', 'android')
        
        # Load UI elements
        test_generator.load_ui_elements()
        
        # Generate tests
        result = test_generator.generate_tests_from_plan(test_cases)
        
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/execute-test-plan")
async def execute_test_plan(request: dict):
    """
    Execute test plan and collect locators
    
    Body:
    {
        "test_plan_path": "test_plans/test_plan_sample.md",
        "device_name": "127.0.0.1:6555",
        "app_package": "co.bizom.apps",
        "app_activity": ".android.MainActivity"
    }
    """
    try:
        test_plan_path = request.get('test_plan_path')
        device_name = request.get('device_name', '127.0.0.1:6555')
        app_package = request.get('app_package', None)
        app_activity = request.get('app_activity', None)
        
        if not test_plan_path or not os.path.exists(test_plan_path):
            raise HTTPException(status_code=404, detail=f"Test plan not found: {test_plan_path}")
        
        # Execute test plan
        result = test_executor.execute_test_plan(
            test_plan_path=test_plan_path,
            device_name=device_name,
            app_package=app_package,
            app_activity=app_activity
        )
        
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/navigate-ui-stream")
async def navigate_ui_stream_endpoint(request: dict):
    """
    Stream navigation progress with real-time updates
    Returns Server-Sent Events (SSE) stream
    """
    command = request.get('command')
    device_name = request.get('device_name', '127.0.0.1:6555')
    app_package = request.get('app_package', None)
    app_activity = request.get('app_activity', None)
    workspace_path = request.get('workspace_path', os.getcwd())
    
    if not command:
        raise HTTPException(status_code=400, detail="command is required")
    
    async def generate_progress():
        """Generate SSE stream with progress updates"""
        try:
            # Send initial understanding
            yield f"data: {json.dumps({'type': 'understanding', 'message': f'🎯 I understand: {command}'})}\n\n"
            
            # Detect intent
            user_command_lower = command.lower()
            has_test_plan = any(kw in user_command_lower for kw in ['test plan', 'test case'])
            
            if has_test_plan:
                yield f"data: {json.dumps({'type': 'intent', 'message': '📋 Detected: Test Plan Execution Mode'})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'intent', 'message': '🧭 Detected: Free-form Navigation Mode'})}\n\n"
            
            # Create progress callback
            def send_progress(msg_type: str, message: str, data: dict = None):
                event = {'type': msg_type, 'message': message}
                if data:
                    event.update(data)
                # Store in queue for async iteration
                progress_queue.put(json.dumps(event))
            
            # Execute with progress callback
            import queue
            progress_queue = queue.Queue()
            
            # Run navigation in thread to allow async streaming
            import threading
            result_container = {}
            
            def run_navigation():
                try:
                    result = ui_explorer.navigate_based_on_intent_with_progress(
                        user_command=command,
                        device_name=device_name,
                        app_package=app_package,
                        app_activity=app_activity,
                        workspace_path=workspace_path,
                        progress_callback=send_progress
                    )
                    result_container['result'] = result
                    progress_queue.put(None)  # Signal completion
                except Exception as e:
                    result_container['error'] = str(e)
                    progress_queue.put(None)
            
            nav_thread = threading.Thread(target=run_navigation)
            nav_thread.start()
            
            # Stream progress updates
            while True:
                try:
                    msg = progress_queue.get(timeout=1.0)
                    if msg is None:  # Completion signal
                        break
                    yield f"data: {msg}\n\n"
                except queue.Empty:
                    # Send keepalive
                    yield f"data: {json.dumps({'type': 'keepalive', 'message': '⏳ Processing...'})}\n\n"
            
            # Wait for thread to complete
            nav_thread.join(timeout=10)
            
            # Send final result
            if 'result' in result_container:
                yield f"data: {json.dumps({'type': 'complete', 'result': result_container['result']})}\n\n"
            elif 'error' in result_container:
                yield f"data: {json.dumps({'type': 'error', 'message': result_container['error']})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': f'❌ {str(e)}'})}\n\n"
    
    return StreamingResponse(generate_progress(), media_type="text/event-stream")


@app.post("/api/navigate-ui")
async def navigate_ui(request: dict):
    """
    Intelligently navigate through UI based on user command
    Uses Claude AI to understand intent and guide navigation
    
    Body:
    {
        "command": "explore pjp screen and do start call and place order",
        "device_name": "127.0.0.1:6555",
        "app_package": "co.bizom.apps",
        "app_activity": ".android.MainActivity",
        "workspace_path": "/path/to/workspace",
        "stream": false  // Set to true for SSE streaming
    }
    """
    try:
        command = request.get('command')
        device_name = request.get('device_name', '127.0.0.1:6555')
        app_package = request.get('app_package', None)
        app_activity = request.get('app_activity', None)
        workspace_path = request.get('workspace_path', os.getcwd())
        stream = request.get('stream', False)
        
        if not command:
            raise HTTPException(status_code=400, detail="command is required")
        
        # If streaming requested, use SSE endpoint
        if stream:
            return StreamingResponse(
                navigate_ui_stream(command, device_name, app_package, app_activity, workspace_path),
                media_type="text/event-stream"
            )
        
        # Original non-streaming behavior
        try:
            result = ui_explorer.navigate_based_on_intent(
                user_command=command,
                device_name=device_name,
                app_package=app_package,
                app_activity=app_activity,
                workspace_path=workspace_path
            )
            return result
        except Exception as navigation_error:
            # If device connection fails, return helpful response
            error_msg = str(navigation_error)
            if "address already in use" in error_msg or "connection refused" in error_msg or "No such device" in error_msg:
                return {
                    "success": False,
                    "error": "Device not connected",
                    "message": f"Could not connect to device at {device_name}",
                    "solutions": [
                        f"1. Ensure device/emulator is running at {device_name}",
                        "2. Check device connection: adb devices",
                        "3. Verify Appium server is running on port 4723",
                        "4. Try updating the device address in settings"
                    ],
                    "command_understood": command,
                    "fallback": "AI understood your command but device not accessible"
                }
            else:
                # Re-raise other errors
                raise
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_detail = f"{str(e)}\n{traceback.format_exc()}"
        raise HTTPException(status_code=500, detail=error_detail)


async def navigate_ui_stream(command: str, device_name: str, app_package: str, 
                             app_activity: str, workspace_path: str):
    """
    Stream navigation progress using Server-Sent Events (SSE)
    Sends real-time updates as execution progresses
    """
    try:
        # Send initial acknowledgment
        yield f"data: {json.dumps({'type': 'start', 'message': f'🎯 Understanding your command: {command}'})}\n\n"
        await asyncio.sleep(0.1)
        
        # Create progress callback
        async def progress_callback(update_type: str, message: str, data: dict = None):
            event_data = {
                'type': update_type,
                'message': message
            }
            if data:
                event_data.update(data)
            yield f"data: {json.dumps(event_data)}\n\n"
            await asyncio.sleep(0.1)
        
        # Execute with progress updates
        result = ui_explorer.navigate_based_on_intent(
            user_command=command,
            device_name=device_name,
            app_package=app_package,
            app_activity=app_activity,
            workspace_path=workspace_path,
            progress_callback=progress_callback
        )
        
        # Send final result
        yield f"data: {json.dumps({'type': 'complete', 'result': result})}\n\n"
        
    except Exception as e:
        error_msg = str(e)
        yield f"data: {json.dumps({'type': 'error', 'message': f'❌ Error: {error_msg}'})}\n\n"


@app.post("/api/execute-test-plan-with-ai")
async def execute_test_plan_with_ai(request: dict):
    """
    Execute test plan with AI-guided navigation
    Uses Claude to understand test flow and intelligently navigate through app
    
    Body:
    {
        "test_plan_path": "test_plans/test_plan_sample.md",
        "device_name": "127.0.0.1:6555",
        "app_package": "co.bizom.apps",
        "app_activity": ".android.MainActivity",
        "anthropic_api_key": "sk-..." (optional, uses env var if not provided)
    }
    """
    try:
        # Handle both dict and request body
        if isinstance(request, dict):
            test_plan_path = request.get('test_plan_path')
            device_name = request.get('device_name', '127.0.0.1:6555')
            app_package = request.get('app_package', None)
            app_activity = request.get('app_activity', None)
            anthropic_api_key = request.get('anthropic_api_key', None)
        else:
            # Fallback for other request types
            test_plan_path = None
            device_name = '127.0.0.1:6555'
            app_package = None
            app_activity = None
            anthropic_api_key = None
        
        if not test_plan_path:
            raise HTTPException(status_code=400, detail="test_plan_path is required")
        
        if not os.path.exists(test_plan_path):
            raise HTTPException(status_code=404, detail=f"Test plan not found: {test_plan_path}")
        
        # Execute test plan with AI navigation
        result = ai_navigator.execute_test_plan_with_ai(
            test_plan_path=test_plan_path,
            device_name=device_name,
            app_package=app_package,
            app_activity=app_activity
        )
        
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_detail = f"{str(e)}\n{traceback.format_exc()}"
        raise HTTPException(status_code=500, detail=error_detail)


if __name__ == "__main__":
    import uvicorn
    
    print("=" * 60)
    print("🚀 QA Copilot API Server")
    print("=" * 60)
    print()
    print("Server starting at: http://localhost:8000")
    print("API Docs: http://localhost:8000/docs")
    print("Interactive API: http://localhost:8000/redoc")
    print()
    print("Available endpoints:")
    print("  POST /api/parse-csv - Upload CSV test cases")
    print("  POST /api/analyze - Analyze codebase")
    print("  POST /api/clone-and-analyze - Clone and analyze repo")
    print("  GET  /api/locators - Get extracted locators")
    print("  GET  /api/test-plan - Get test plan")
    print()
    print("=" * 60)
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
