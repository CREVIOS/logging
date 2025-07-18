from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
import json
import asyncio
from urllib.parse import quote
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Centralized Log API",
    version="2.0.0",
    description="Centralized logging API for Template and Tabular services",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
LOKI_URL = os.getenv("LOKI_URL", "http://loki:3100")
GRAFANA_URL = os.getenv("GRAFANA_URL", "http://grafana:3000")
DEFAULT_TIMEOUT = 30

# Fixed service definitions
SERVICES = {
    "template": {
        "api": "template-backend-api",
        "celery-worker": "template-backend-celery-worker",
        "celery-beat": "template-backend-celery-beat",
        "nginx": "template-backend-nginx-ssl",
        "redis": "template-backend-redis"
    },
    "tabular": {
        "api": "tabular-backend-backend",  # Fixed naming
        "celery-worker": "tabular-backend-celery-worker",
        "celery-beat": "tabular-backend-celery-beat",
        "nginx": "tabular-review-nginx-ssl",
        "redis": "tabular-review-redis"
    }
}

async def query_loki(
    query: str, 
    start_time: Optional[str] = None, 
    end_time: Optional[str] = None,
    limit: int = 100,
    direction: str = "backward"
) -> Dict[str, Any]:
    """Query Loki for log data with proper error handling"""
    
    params = {
        "query": query,
        "limit": str(limit),
        "direction": direction
    }
    
    if start_time:
        params["start"] = start_time
    if end_time:
        params["end"] = end_time
    
    logger.info(f"Querying Loki: {query}")
    
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        try:
            response = await client.get(
                f"{LOKI_URL}/loki/api/v1/query_range", 
                params=params
            )
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=504, 
                detail="Loki query timeout"
            )
        except httpx.HTTPStatusError as e:
            logger.error(f"Loki HTTP error: {e.response.status_code} - {e.response.text}")
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Loki query failed: {e.response.text}"
            )
        except Exception as e:
            logger.error(f"Loki query error: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error querying Loki: {str(e)}"
            )

def format_timestamp(timestamp_ns: str) -> str:
    """Convert nanosecond timestamp to ISO format"""
    try:
        timestamp_s = int(timestamp_ns) / 1_000_000_000
        dt = datetime.fromtimestamp(timestamp_s, timezone.utc)
        return dt.isoformat()
    except:
        return timestamp_ns

@app.get("/", tags=["Root"])
async def root():
    return {
        "message": "Centralized Log API v2.0.0",
        "services": SERVICES,
        "endpoints": {
            "logs": "/logs/{stack}/{service}",
            "errors": "/errors/{stack}/{service}",
            "health": "/health",
            "search": "/search",
            "summary": "/summary",
            "metrics": "/metrics"
        }
    }

@app.get("/health", tags=["Health"])
async def health_check():
    """Comprehensive health check"""
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": {}
    }
    
    # Check Loki
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{LOKI_URL}/ready")
            health_status["services"]["loki"] = {
                "status": "healthy" if response.status_code == 200 else "unhealthy",
                "response_time": response.elapsed.total_seconds()
            }
    except Exception as e:
        health_status["services"]["loki"] = {
            "status": "unhealthy",
            "error": str(e)
        }
    
    # Check Grafana
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{GRAFANA_URL}/api/health")
            health_status["services"]["grafana"] = {
                "status": "healthy" if response.status_code == 200 else "unhealthy",
                "response_time": response.elapsed.total_seconds()
            }
    except Exception as e:
        health_status["services"]["grafana"] = {
            "status": "unhealthy",
            "error": str(e)
        }
    
    # Overall status
    overall_healthy = all(
        service.get("status") == "healthy" 
        for service in health_status["services"].values()
    )
    health_status["status"] = "healthy" if overall_healthy else "degraded"
    
    return JSONResponse(
        content=health_status,
        status_code=200 if overall_healthy else 503
    )

@app.get("/logs/{stack}/{service}", tags=["Logs"])
async def get_service_logs(
    stack: str,
    service: str,
    hours: int = Query(1, ge=1, le=168, description="Hours of logs to retrieve"),
    limit: int = Query(100, ge=1, le=5000, description="Maximum log entries"),
    level: Optional[str] = Query(None, description="Filter by log level"),
    search: Optional[str] = Query(None, description="Search term")
):
    """Get logs for a specific service"""
    
    if stack not in SERVICES:
        raise HTTPException(
            status_code=404, 
            detail=f"Stack '{stack}' not found. Available: {list(SERVICES.keys())}"
        )
    
    if service not in SERVICES[stack]:
        raise HTTPException(
            status_code=404,
            detail=f"Service '{service}' not found in stack '{stack}'. Available: {list(SERVICES[stack].keys())}"
        )
    
    container_name = SERVICES[stack][service]
    
    # Calculate time range
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=hours)
    
    # Build LogQL query
    query = f'{{container_name="{container_name}"}}'
    
    if level:
        query += f' | json | level="{level}"'
    
    if search:
        query += f' |~ "(?i){search}"'
    
    try:
        result = await query_loki(
            query=query,
            start_time=start_time.isoformat() + "Z",
            end_time=end_time.isoformat() + "Z",
            limit=limit
        )
        
        # Process results
        logs = []
        total_count = 0
        
        if "data" in result and "result" in result["data"]:
            for stream in result["data"]["result"]:
                for entry in stream["values"]:
                    timestamp_ns, log_line = entry
                    logs.append({
                        "timestamp": format_timestamp(timestamp_ns),
                        "message": log_line,
                        "labels": stream["stream"]
                    })
                    total_count += 1
        
        return {
            "stack": stack,
            "service": service,
            "container": container_name,
            "query": query,
            "time_range": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "hours": hours
            },
            "total_count": total_count,
            "returned_count": len(logs),
            "logs": logs
        }
        
    except Exception as e:
        logger.error(f"Error retrieving logs: {str(e)}")
        raise

@app.get("/errors/{stack}/{service}", tags=["Logs"])
async def get_service_errors(
    stack: str,
    service: str,
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(100, ge=1, le=1000)
):
    """Get error logs for a specific service"""
    
    if stack not in SERVICES:
        raise HTTPException(status_code=404, detail=f"Stack '{stack}' not found")
    
    if service not in SERVICES[stack]:
        raise HTTPException(status_code=404, detail=f"Service '{service}' not found")
    
    container_name = SERVICES[stack][service]
    
    # Time range
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=hours)
    
    # Enhanced error detection query
    query = f'{{container_name="{container_name}"}} |~ "(?i)(error|exception|failed|critical|fatal|traceback|stacktrace)"'
    
    try:
        result = await query_loki(
            query=query,
            start_time=start_time.isoformat() + "Z",
            end_time=end_time.isoformat() + "Z",
            limit=limit
        )
        
        errors = []
        if "data" in result and "result" in result["data"]:
            for stream in result["data"]["result"]:
                for entry in stream["values"]:
                    timestamp_ns, log_line = entry
                    errors.append({
                        "timestamp": format_timestamp(timestamp_ns),
                        "message": log_line,
                        "labels": stream["stream"]
                    })
        
        return {
            "stack": stack,
            "service": service,
            "container": container_name,
            "time_range": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "hours": hours
            },
            "error_count": len(errors),
            "errors": errors
        }
        
    except Exception as e:
        logger.error(f"Error retrieving error logs: {str(e)}")
        raise

@app.get("/search", tags=["Search"])
async def search_logs(
    query: str = Query(..., description="Search query"),
    stack: Optional[str] = Query(None, description="Filter by stack"),
    hours: int = Query(1, ge=1, le=168),
    limit: int = Query(100, ge=1, le=1000)
):
    """Search logs across services"""
    
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=hours)
    
    # Build LogQL query
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
            end_time=end_time.isoformat() + "Z",
            limit=limit
        )
        
        matches = []
        if "data" in result and "result" in result["data"]:
            for stream in result["data"]["result"]:
                for entry in stream["values"]:
                    timestamp_ns, log_line = entry
                    matches.append({
                        "timestamp": format_timestamp(timestamp_ns),
                        "message": log_line,
                        "labels": stream["stream"]
                    })
        
        return {
            "query": query,
            "stack_filter": stack,
            "time_range": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "hours": hours
            },
            "match_count": len(matches),
            "matches": matches
        }
        
    except Exception as e:
        logger.error(f"Error searching logs: {str(e)}")
        raise

@app.get("/summary", tags=["Analytics"])
async def get_log_summary(hours: int = Query(1, ge=1, le=168)):
    """Get log activity summary"""
    
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=hours)
    
    summary = {
        "period": f"Last {hours} hours",
        "time_range": {
            "start": start_time.isoformat(),
            "end": end_time.isoformat()
        },
        "stacks": {}
    }
    
    # Process each stack
    for stack_name, services in SERVICES.items():
        summary["stacks"][stack_name] = {
            "services": {},
            "total_logs": 0,
            "total_errors": 0
        }
        
        for service_name, container_name in services.items():
            try:
                # Get log count
                log_query = f'{{container_name="{container_name}"}}'
                log_result = await query_loki(
                    query=log_query,
                    start_time=start_time.isoformat() + "Z",
                    end_time=end_time.isoformat() + "Z",
                    limit=10000
                )
                
                log_count = 0
                if "data" in log_result and "result" in log_result["data"]:
                    for stream in log_result["data"]["result"]:
                        log_count += len(stream["values"])
                
                # Get error count
                error_query = f'{{container_name="{container_name}"}} |~ "(?i)(error|exception|failed|critical)"'
                error_result = await query_loki(
                    query=error_query,
                    start_time=start_time.isoformat() + "Z",
                    end_time=end_time.isoformat() + "Z",
                    limit=1000
                )
                
                error_count = 0
                if "data" in error_result and "result" in error_result["data"]:
                    for stream in error_result["data"]["result"]:
                        error_count += len(stream["values"])
                
                summary["stacks"][stack_name]["services"][service_name] = {
                    "container": container_name,
                    "log_count": log_count,
                    "error_count": error_count,
                    "error_rate": round(error_count / log_count * 100, 2) if log_count > 0 else 0
                }
                
                summary["stacks"][stack_name]["total_logs"] += log_count
                summary["stacks"][stack_name]["total_errors"] += error_count
                
            except Exception as e:
                summary["stacks"][stack_name]["services"][service_name] = {
                    "container": container_name,
                    "error": str(e)
                }
    
    return summary

@app.get("/metrics", tags=["Analytics"])
async def get_metrics():
    """Get basic metrics for monitoring"""
    
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=1)
    
    metrics = {
        "timestamp": end_time.isoformat(),
        "services_monitored": sum(len(services) for services in SERVICES.values()),
        "stacks": len(SERVICES),
        "last_hour": {}
    }
    
    try:
        # Get total logs in last hour
        total_query = '{stack=~"template|tabular"}'
        result = await query_loki(
            query=total_query,
            start_time=start_time.isoformat() + "Z",
            end_time=end_time.isoformat() + "Z",
            limit=50000
        )
        
        total_logs = 0
        if "data" in result and "result" in result["data"]:
            for stream in result["data"]["result"]:
                total_logs += len(stream["values"])
        
        metrics["last_hour"]["total_logs"] = total_logs
        metrics["last_hour"]["logs_per_minute"] = round(total_logs / 60, 2)
        
    except Exception as e:
        metrics["last_hour"]["error"] = str(e)
    
    return metrics

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
