#!/bin/bash
# Centralized Logging Setup Script
# This script sets up the complete logging infrastructure

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_header() {
    echo -e "\n${BLUE}=================================="
    echo -e "$1"
    echo -e "==================================${NC}\n"
}

print_step() {
    echo -e "${YELLOW}📋 $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Check dependencies
check_dependencies() {
    print_step "Checking dependencies..."
    
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose is not installed"
        exit 1
    fi
    
    print_success "Dependencies check passed"
}

# Create directory structure
create_directories() {
    print_step "Creating directory structure..."
    
    mkdir -p centralized-logging/{loki/config,promtail/config,grafana/{provisioning,dashboards},alertmanager,log-api}
    
    print_success "Directories created"
}

# Create configuration files
create_configs() {
    print_step "Creating configuration files..."
    
    # Create Loki config
    cat > centralized-logging/loki/config/local-config.yaml << 'EOF'
auth_enabled: false

server:
  http_listen_port: 3100
  grpc_listen_port: 9096

common:
  path_prefix: /tmp/loki
  storage:
    filesystem:
      chunks_directory: /tmp/loki/chunks
      rules_directory: /tmp/loki/rules
  replication_factor: 1
  ring:
    instance_addr: 127.0.0.1
    kvstore:
      store: inmemory

query_range:
  results_cache:
    cache:
      embedded_cache:
        enabled: true
        max_size_mb: 100

schema_config:
  configs:
    - from: 2020-10-24
      store: boltdb-shipper
      object_store: filesystem
      schema: v11
      index:
        prefix: index_
        period: 24h

limits_config:
  enforce_metric_name: false
  reject_old_samples: true
  reject_old_samples_max_age: 168h
  max_cache_freshness_per_query: 10m
  split_queries_by_interval: 15m

table_manager:
  retention_deletes_enabled: true
  retention_period: 168h
EOF

    # Create Grafana datasource provisioning
    mkdir -p centralized-logging/grafana/provisioning/datasources
    cat > centralized-logging/grafana/provisioning/datasources/loki.yml << 'EOF'
apiVersion: 1

datasources:
  - name: Loki
    type: loki
    access: proxy
    url: http://loki:3100
    isDefault: true
EOF

    # Create basic Grafana dashboard
    cat > centralized-logging/grafana/dashboards/services-overview.json << 'EOF'
{
  "dashboard": {
    "id": null,
    "title": "Template & Tabular Services Overview",
    "uid": "services-overview",
    "version": 1,
    "schemaVersion": 30,
    "panels": [
      {
        "id": 1,
        "title": "Log Volume by Service",
        "type": "stat",
        "targets": [
          {
            "expr": "sum by (container_name) (count_over_time({stack=~\"template|tabular\"}[1h]))",
            "legendFormat": "{{container_name}}"
          }
        ],
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0}
      },
      {
        "id": 2,
        "title": "Recent Logs",
        "type": "logs",
        "targets": [
          {
            "expr": "{stack=~\"template|tabular\"}"
          }
        ],
        "gridPos": {"h": 12, "w": 24, "x": 0, "y": 8}
      }
    ],
    "time": {"from": "now-1h", "to": "now"},
    "refresh": "30s"
  }
}
EOF

    # Create Log API Dockerfile
    cat > centralized-logging/log-api/Dockerfile << 'EOF'
FROM python:3.11-slim

WORKDIR /app

RUN pip install fastapi uvicorn httpx

COPY main.py .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
EOF

    print_success "Configuration files created"
}

# Create the main logging script
create_logging_script() {
    print_step "Creating centralized logging script..."
    
    # Copy the main logging script to the setup directory
    cp logs.sh centralized-logging/ 2>/dev/null || echo "Note: logs.sh not found, you'll need to copy it manually"
    
    print_success "Logging script ready"
}

# Deploy logging stack
deploy_stack() {
    print_step "Deploying centralized logging stack..."
    
    cd centralized-logging
    
    # Start the logging stack
    docker-compose -f ../docker-compose.logging.yml up -d
    
    # Wait for services to be ready
    print_step "Waiting for services to start..."
    sleep 30
    
    # Check if services are running
    if docker-compose -f ../docker-compose.logging.yml ps | grep -q "Up"; then
        print_success "Logging stack deployed successfully"
    else
        print_error "Some services failed to start"
        docker-compose -f ../docker-compose.logging.yml logs
    fi
    
    cd ..
}

# Test the setup
test_setup() {
    print_step "Testing the logging setup..."
    
    # Test Loki
    if curl -s http://localhost:3100/ready > /dev/null; then
        print_success "Loki is running"
    else
        print_error "Loki is not responding"
    fi
    
    # Test Grafana
    if curl -s http://localhost:3000/api/health > /dev/null; then
        print_success "Grafana is running"
    else
        print_error "Grafana is not responding"
    fi
    
    # Test Log API
    if curl -s http://localhost:8888/health > /dev/null; then
        print_success "Log API is running"
    else
        print_error "Log API is not responding"
    fi
}

# Show access information
show_access_info() {
    print_header "🎉 SETUP COMPLETE!"
    
    echo -e "${GREEN}Access your centralized logging services:${NC}"
    echo ""
    echo -e "${YELLOW}📊 Grafana Dashboard:${NC}"
    echo "   URL: http://localhost:3000"
    echo "   Username: admin"
    echo "   Password: admin123"
    echo ""
    echo -e "${YELLOW}🔍 Log API:${NC}"
    echo "   URL: http://localhost:8888"
    echo "   Docs: http://localhost:8888/docs"
    echo ""
    echo -e "${YELLOW}📋 Loki (Direct):${NC}"
    echo "   URL: http://localhost:3100"
    echo ""
    echo -e "${YELLOW}🛠️  Management Commands:${NC}"
    echo "   View all logs: ./logs.sh summary"
    echo "   Tail live logs: ./logs.sh tail"
    echo "   Check health: ./logs.sh health"
    echo "   Export logs: ./logs.sh export"
    echo ""
    echo -e "${YELLOW}📱 API Examples:${NC}"
    echo "   Get template API logs: curl 'http://localhost:8888/logs/template/api?hours=1'"
    echo "   Search for errors: curl 'http://localhost:8888/search?query=error&hours=24'"
    echo "   Get log summary: curl 'http://localhost:8888/summary?hours=1'"
}

# Main execution
main() {
    print_header "🚀 CENTRALIZED LOGGING SETUP"
    
    case "${1:-install}" in
        "install"|"setup")
            check_dependencies
            create_directories
            create_configs
            create_logging_script
            deploy_stack
            test_setup
            show_access_info
            ;;
        "start")
            print_step "Starting logging services..."
            cd centralized-logging
            docker-compose -f ../docker-compose.logging.yml up -d
            print_success "Services started"
            ;;
        "stop")
            print_step "Stopping logging services..."
            cd centralized-logging
            docker-compose -f ../docker-compose.logging.yml down
            print_success "Services stopped"
            ;;
        "restart")
            print_step "Restarting logging services..."
            cd centralized-logging
            docker-compose -f ../docker-compose.logging.yml restart
            print_success "Services restarted"
            ;;
        "status")
            cd centralized-logging
            docker-compose -f ../docker-compose.logging.yml ps
            ;;
        "logs")
            cd centralized-logging
            docker-compose -f ../docker-compose.logging.yml logs -f "${2:-}"
            ;;
        "clean")
            print_step "Cleaning up logging services..."
            cd centralized-logging
            docker-compose -f ../docker-compose.logging.yml down -v
            docker system prune -f
            print_success "Cleanup complete"
            ;;
        *)
            echo "Usage: $0 {install|start|stop|restart|status|logs|clean}"
            echo ""
            echo "Commands:"
            echo "  install  - Full setup and deployment"
            echo "  start    - Start logging services"
            echo "  stop     - Stop logging services"
            echo "  restart  - Restart logging services"  
            echo "  status   - Show service status"
            echo "  logs     - Follow service logs"
            echo "  clean    - Remove everything"
            ;;
    esac
}

main "$@"