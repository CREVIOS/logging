#!/bin/bash

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Service definitions
TEMPLATE_SERVICES=(
    "template-backend-api"
    "template-backend-celery-worker" 
    "template-backend-celery-beat"
    "template-backend-nginx-ssl"
    "template-backend-redis"
)

TABULAR_SERVICES=(
    "tabular-bakcend-backend"
    "tabular-bakcend-celery-worker"
    "tabular-bakcend-celery-beat" 
    "tabular-review-nginx-ssl"
    "tabular-review-redis"
)

ALL_SERVICES=("${TEMPLATE_SERVICES[@]}" "${TABULAR_SERVICES[@]}")

# Function to print colored headers
print_header() {
    echo -e "\n${BLUE}=================================="
    echo -e "$1"
    echo -e "==================================${NC}\n"
}

print_service_header() {
    echo -e "${CYAN}📋 $1${NC}"
    echo "----------------------------------------"
}

# Function to check container status
check_status() {
    local container=$1
    if docker ps --format "table {{.Names}}\t{{.Status}}" | grep -q "$container"; then
        status=$(docker ps --format "table {{.Names}}\t{{.Status}}" | grep "$container" | awk '{print $2, $3}')
        if [[ $status == *"healthy"* ]]; then
            echo -e "${GREEN}✅ $container: $status${NC}"
        elif [[ $status == *"unhealthy"* ]]; then
            echo -e "${RED}❌ $container: $status${NC}"
        else
            echo -e "${YELLOW}⚠️  $container: $status${NC}"
        fi
    else
        echo -e "${RED}🔴 $container: NOT RUNNING${NC}"
    fi
}

# Function to get recent logs
get_recent_logs() {
    local container=$1
    local lines=${2:-50}
    
    if docker ps --format "{{.Names}}" | grep -q "^${container}$"; then
        echo -e "${PURPLE}📝 Recent logs for $container (last $lines lines):${NC}"
        docker logs --tail=$lines --timestamps "$container" 2>&1 | head -20
        echo ""
    else
        echo -e "${RED}❌ Container $container is not running${NC}"
    fi
}

# Function to get error logs only
get_error_logs() {
    local container=$1
    local lines=${2:-100}
    
    if docker ps --format "{{.Names}}" | grep -q "^${container}$"; then
        echo -e "${RED}🚨 Error logs for $container:${NC}"
        docker logs --tail=$lines "$container" 2>&1 | grep -i -E "(error|exception|failed|critical)" | head -10
        echo ""
    fi
}

# Function to show service health summary
show_health_summary() {
    print_header "🏥 SERVICE HEALTH SUMMARY"
    
    echo -e "${BLUE}Template Services:${NC}"
    for service in "${TEMPLATE_SERVICES[@]}"; do
        check_status "$service"
    done
    
    echo -e "\n${BLUE}Tabular Services:${NC}"
    for service in "${TABULAR_SERVICES[@]}"; do
        check_status "$service"
    done
    
    # Resource usage summary
    echo -e "\n${BLUE}📊 Resource Usage:${NC}"
    docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}" \
        $(printf "%s " "${ALL_SERVICES[@]}") 2>/dev/null | head -10
}

# Function to tail logs from all services
tail_all_logs() {
    print_header "📡 TAILING ALL SERVICE LOGS"
    echo "Press Ctrl+C to stop..."
    sleep 2
    
    # Create a temporary file for log aggregation
    temp_log="/tmp/aggregated_logs_$(date +%s).log"
    
    # Start background log tailing for each service
    for service in "${ALL_SERVICES[@]}"; do
        if docker ps --format "{{.Names}}" | grep -q "^${service}$"; then
            docker logs -f --timestamps "$service" 2>&1 | sed "s/^/[$service] /" >> "$temp_log" &
        fi
    done
    
    # Tail the aggregated log
    tail -f "$temp_log"
}

# Function to show recent activity across all services
show_recent_activity() {
    print_header "🕐 RECENT ACTIVITY (Last 10 minutes)"
    
    since_time=$(date -d '10 minutes ago' '+%Y-%m-%dT%H:%M:%S')
    
    for service in "${ALL_SERVICES[@]}"; do
        if docker ps --format "{{.Names}}" | grep -q "^${service}$"; then
            echo -e "${CYAN}📋 $service:${NC}"
            docker logs --since="$since_time" --timestamps "$service" 2>&1 | tail -5
            echo ""
        fi
    done
}

# Function to show logs for specific service
show_service_logs() {
    local service=$1
    local lines=${2:-100}
    
    if [[ " ${ALL_SERVICES[@]} " =~ " ${service} " ]]; then
        print_header "📋 LOGS FOR $service"
        get_recent_logs "$service" "$lines"
    else
        echo -e "${RED}❌ Service '$service' not found${NC}"
        echo "Available services:"
        printf '%s\n' "${ALL_SERVICES[@]}"
    fi
}

# Function to export logs to files
export_logs() {
    local export_dir="logs_export_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$export_dir"
    
    print_header "📦 EXPORTING LOGS TO $export_dir"
    
    for service in "${ALL_SERVICES[@]}"; do
        if docker ps --format "{{.Names}}" | grep -q "^${service}$"; then
            echo "Exporting $service logs..."
            docker logs --timestamps "$service" > "$export_dir/${service}.log" 2>&1
        fi
    done
    
    # Create summary file
    cat > "$export_dir/summary.txt" << EOF
Log Export Summary
Generated: $(date)

Services included:
$(printf '%s\n' "${ALL_SERVICES[@]}")

File sizes:
$(ls -lh "$export_dir"/*.log)
EOF
    
    echo -e "${GREEN}✅ Logs exported to $export_dir${NC}"
}

# Main menu
show_menu() {
    echo -e "${YELLOW}🚀 Centralized Log Management${NC}"
    echo "=================================="
    echo "1. Health Summary"
    echo "2. Recent Activity (10 min)"
    echo "3. Tail All Logs (live)"
    echo "4. Show Errors Only"
    echo "5. Show Specific Service"
    echo "6. Export All Logs"
    echo "7. Custom Command"
    echo "0. Exit"
    echo ""
}

# Parse command line arguments
case "${1:-menu}" in
    "health"|"status")
        show_health_summary
        ;;
    "tail"|"live")
        tail_all_logs
        ;;
    "errors"|"error")
        print_header "🚨 ERROR LOGS ACROSS ALL SERVICES"
        for service in "${ALL_SERVICES[@]}"; do
            get_error_logs "$service"
        done
        ;;
    "recent"|"activity")
        show_recent_activity
        ;;
    "export")
        export_logs
        ;;
    "service")
        if [ -n "$2" ]; then
            show_service_logs "$2" "${3:-100}"
        else
            echo "Usage: $0 service <service_name> [lines]"
            echo "Available services:"
            printf '%s\n' "${ALL_SERVICES[@]}"
        fi
        ;;
    "summary")
        show_health_summary
        echo ""
        show_recent_activity
        ;;
    "menu"|*)
        while true; do
            show_menu
            read -p "Choose an option: " choice
            case $choice in
                1) show_health_summary ;;
                2) show_recent_activity ;;
                3) tail_all_logs ;;
                4) 
                    print_header "🚨 ERROR LOGS"
                    for service in "${ALL_SERVICES[@]}"; do
                        get_error_logs "$service"
                    done
                    ;;
                5)
                    echo "Available services:"
                    printf '%s\n' "${ALL_SERVICES[@]}"
                    read -p "Enter service name: " service_name
                    read -p "Number of lines (default 100): " lines
                    show_service_logs "$service_name" "${lines:-100}"
                    ;;
                6) export_logs ;;
                7)
                    read -p "Enter custom docker command (e.g., 'logs --tail=50 template-backend-api'): " custom_cmd
                    docker $custom_cmd
                    ;;
                0) echo "Goodbye!"; exit 0 ;;
                *) echo "Invalid option" ;;
            esac
            echo ""
            read -p "Press Enter to continue..."
        done
        ;;
esac