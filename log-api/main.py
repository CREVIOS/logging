# log-api/main.py
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
import httpx
import os
from datetime import datetime, timedelta
from typing import Optional, List
import json

app = FastAPI(title="Centralized Log API", version="1.0.0")

LOKI_URL = os.getenv("LOKI_URL", "http://loki:3100")
GRAFANA_URL = os.getenv("GRAFANA_URL", "http://grafana:3000")

# Service definitions
SERVICES = {
    "template": {
        "api": "template-backend-api",
        "celery-worker": "template-backend-celery-worker",
        "celery-beat": "template-backend-celery-beat",
        "nginx": "template-backend-nginx-ssl",
        "redis": "template-backend-redis"
    },
    "tabular": {
        "api": "tabular-bakcend-backend",
        "celery-worker": "tabular-bakcend-celery-worker", 
        "celery-beat": "tabular-bakcend-celery-beat",
        "nginx": "tabular-review-nginx-ssl",
        "redis": "tabular-review-redis"
    }
}

async def query_loki(query: str, start_time: Optional[str] = None, end_time: Optional[str] = None):
    """Query Loki for log data"""
    params = {"query": query}
    
    if start_time:
        params["start"] = start_time
    if end_time:
        params["end"] = end_time
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{LOKI_URL}/loki/api/v1/query_range", params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=f"Loki query failed: {e}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error querying Loki: {str(e)}")

@app.get("/")
async def root():
    return {
        "message": "Centralized Log API",
        "services": SERVICES,
        "endpoints": {
            "logs": "/logs/{stack}/{service}",
            "errors": "/errors/{stack}/{service}",
            "health": "/health",
            "search": "/search"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        async with httpx.AsyncClient() as client:
            loki_response = await client.get(f"{LOKI_URL}/ready", timeout=5)
            loki_healthy = loki_response.status_code == 200
            
            grafana_response = await client.get(f"{GRAFANA_URL}/api/health", timeout=5)
            grafana_healthy = grafana_response.status_code == 200
            
        return {
            "status": "healthy" if loki_healthy and grafana_healthy else "unhealthy",
            "loki": "healthy" if loki_healthy else "unhealthy",
            "grafana": "healthy" if grafana_healthy else "unhealthy"
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "unhealthy", "error": str(e)}
        )

@app.get("/logs/{stack}/{service}")
async def get_service_logs(
    stack: str,
    service: str,
    hours: int = Query(1, description="Hours of logs to retrieve"),
    limit: int = Query(100, description="Maximum number of log entries")
):
    """Get logs for a specific service in a stack"""
    
    if stack not in SERVICES:
        raise HTTPException(status_code=404, detail=f"Stack '{stack}' not found")
    
    if service not in SERVICES[stack]:
        raise HTTPException(status_code=404, detail=f"Service '{service}' not found in stack '{stack}'")
    
    container_name = SERVICES[stack][service]
    
    # Calculate time range
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=hours)
    
    # Build Loki query
    query = f'{{container_name="{container_name}"}}'
    
    try:
        result = await query_loki(
            query=query,
            start_time=start_time.isoformat() + "Z",
            end_time=end_time.isoformat() + "Z"
        )
        
        # Process and format results
        logs = []
        if "data" in result and "result" in result["data"]:
            for stream in result["data"]["result"]:
                for entry in stream["values"][:limit]:
                    timestamp, log_line = entry
                    logs.append({
                        "timestamp": timestamp,
                        "message": log_line,
                        "labels": stream["stream"]
                    })
        
        return {
            "stack": stack,
            "service": service,
            "container": container_name,
            "count": len(logs),
            "logs": logs
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving logs: {str(e)}")

@app.get("/errors/{stack}/{service}")
async def get_service_errors(
    stack: str,
    service: str,
    hours: int = Query(24, description="Hours of logs to search for errors"),
    limit: int = Query(50, description="Maximum number of error entries")
):
    """Get error logs for a specific service"""
    
    if stack not in SERVICES:
        raise HTTPException(status_code=404, detail=f"Stack '{stack}' not found")
    
    if service not in SERVICES[stack]:
        raise HTTPException(status_code=404, detail=f"Service '{service}' not found in stack '{stack}'")
    
    container_name = SERVICES[stack][service]
    
    # Calculate time range
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=hours)
    
    # Build Loki query for errors
    query = f'{{container_name="{container_name}"}} |~ "(?i)(error|exception|failed|critical|fatal)"'
    
    try:
        result = await query_loki(
            query=query,
            start_time=start_time.isoformat() + "Z",
            end_time=end_time.isoformat() + "Z"
        )
        
        # Process and format results
        errors = []
        if "data" in result and "result" in result["data"]:
            for stream in result["data"]["result"]:
                for entry in stream["values"][:limit]:
                    timestamp, log_line = entry
                    errors.append({
                        "timestamp": timestamp,
                        "message": log_line,
                        "labels": stream["stream"]
                    })
        
        return {
            "stack": stack,
            "service": service,
            "container": container_name,
            "error_count": len(errors),
            "errors": errors
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving error logs: {str(e)}")

@app.get("/search")
async def search_logs(
    query: str = Query(..., description="Search query"),
    stack: Optional[str] = Query(None, description="Filter by stack (template/tabular)"),
    hours: int = Query(1, description="Hours of logs to search"),
    limit: int = Query(100, description="Maximum number of results")
):
    """Search logs across all services"""
    
    # Calculate time range
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=hours)
    
    # Build Loki query
    if stack:
        if stack not in SERVICES:
            raise HTTPException(status_code=404, detail=f"Stack '{stack}' not found")
        loki_query = f'{{stack="{stack}"}} |~ "(?i){query}"'
    else:
        loki_query = f'{{stack=~"template|tabular"}} |~ "(?i){query}"'
    
    try:
        result = await query_loki(
            query=loki_query,
            start_time=start_time.isoformat() + "Z",
            end_time=end_time.isoformat() + "Z"
        )
        
        # Process and format results
        matches = []
        if "data" in result and "result" in result["data"]:
            for stream in result["data"]["result"]:
                for entry in stream["values"][:limit]:
                    timestamp, log_line = entry
                    matches.append({
                        "timestamp": timestamp,
                        "message": log_line,
                        "labels": stream["stream"]
                    })
        
        return {
            "query": query,
            "stack_filter": stack,
            "match_count": len(matches),
            "matches": matches
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error searching logs: {str(e)}")

@app.get("/summary")
async def get_log_summary(hours: int = Query(1, description="Hours to summarize")):
    """Get a summary of log activity across all services"""
    
    # Calculate time range
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=hours)
    
    summary = {
        "period": f"Last {hours} hours",
        "stacks": {}
    }
    
    # Get summary for each stack
    for stack_name, services in SERVICES.items():
        summary["stacks"][stack_name] = {}
        
        for service_name, container_name in services.items():
            try:
                # Query log count
                query = f'{{container_name="{container_name}"}}'
                result = await query_loki(
                    query=query,
                    start_time=start_time.isoformat() + "Z",
                    end_time=end_time.isoformat() + "Z"
                )
                
                log_count = 0
                if "data" in result and "result" in result["data"]:
                    for stream in result["data"]["result"]:
                        log_count += len(stream["values"])
                
                # Query error count
                error_query = f'{{container_name="{container_name}"}} |~ "(?i)(error|exception|failed|critical)"'
                error_result = await query_loki(
                    query=error_query,
                    start_time=start_time.isoformat() + "Z",
                    end_time=end_time.isoformat() + "Z"
                )
                
                error_count = 0
                if "data" in error_result and "result" in error_result["data"]:
                    for stream in error_result["data"]["result"]:
                        error_count += len(stream["values"])
                
                summary["stacks"][stack_name][service_name] = {
                    "container": container_name,
                    "log_count": log_count,
                    "error_count": error_count
                }
                
            except Exception as e:
                summary["stacks"][stack_name][service_name] = {
                    "container": container_name,
                    "error": str(e)
                }
    
    return summary

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)