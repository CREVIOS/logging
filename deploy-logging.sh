#!/bin/bash

# Centralized Logging Deployment Script
# This script deploys the complete logging infrastructure for template and tabular services

set -e

# Colors for output
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

# Check if running as root (needed for docker socket access)
check_permissions() {
    print_step "Checking permissions..."
    
    if [ "$EUID" -eq 0 ]; then
        print_error "Please don't run this script as root"
        exit 1
    fi
    
    # Check if user is in docker group
    if ! groups $USER | grep -q docker; then
        print_error "User $USER is not in docker group. Please add user to docker group:"
        echo "sudo usermod -aG docker $USER"
        echo "Then log out and log back in"
        exit 1
    fi
    
    print_success "Permissions check passed"
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

# Create necessary directories
create_directories() {
    print_step "Creating necessary directories..."
    
    mkdir -p alertmanager
    mkdir -p grafana/dashboards
    
    print_success "Directories created"
}

# Build and deploy the logging stack
deploy_stack() {
    print_step "Deploying centralized logging stack..."
    
    # Build the log-api service
    print_step "Building log-api service..."
    docker-compose -f docker-compose.logging.yml build log-api
    
    # Start the logging stack
    print_step "Starting logging services..."
    docker-compose -f docker-compose.logging.yml up -d
    
    print_success "Logging stack deployed"
}

# Wait for services to be ready
wait_for_services() {
    print_step "Waiting for services to be ready..."
    
    # Wait for Loki
    print_step "Waiting for Loki..."
    timeout=60
    while [ $timeout -gt 0 ]; do
        if curl -s http://localhost:3100/ready > /dev/null 2>&1; then
            print_success "Loki is ready"
            break
        fi
        sleep 2
        timeout=$((timeout - 2))
    done
    
    if [ $timeout -le 0 ]; then
        print_error "Loki failed to start within 60 seconds"
        exit 1
    fi
    
    # Wait for Grafana
    print_step "Waiting for Grafana..."
    timeout=60
    while [ $timeout -gt 0 ]; do
        if curl -s http://localhost:3000/api/health > /dev/null 2>&1; then
            print_success "Grafana is ready"
            break
        fi
        sleep 2
        timeout=$((timeout - 2))
    done
    
    if [ $timeout -le 0 ]; then
        print_error "Grafana failed to start within 60 seconds"
        exit 1
    fi
    
    # Wait for Log API
    print_step "Waiting for Log API..."
    timeout=60
    while [ $timeout -gt 0 ]; do
        if curl -s http://localhost:8888/health > /dev/null 2>&1; then
            print_success "Log API is ready"
            break
        fi
        sleep 2
        timeout=$((timeout - 2))
    done
    
    if [ $timeout -le 0 ]; then
        print_error "Log API failed to start within 60 seconds"
        exit 1
    fi
}

# Show service status
show_status() {
    print_header "🚀 CENTRALIZED LOGGING STATUS"
    
    echo -e "${BLUE}Service Status:${NC}"
    docker-compose -f docker-compose.logging.yml ps
    
    echo -e "\n${BLUE}Access URLs:${NC}"
    echo "Grafana: http://localhost:3000 (admin/admin123)"
    echo "Loki: http://localhost:3100"
    echo "Log API: http://localhost:8888"
    echo "Alertmanager: http://localhost:9093"
    
    echo -e "\n${BLUE}Quick Commands:${NC}"
    echo "View logs: ./logs.sh"
    echo "Check health: curl http://localhost:8888/health"
    echo "Get template API logs: curl http://localhost:8888/logs/template/api"
    echo "Get tabular API logs: curl http://localhost:8888/logs/tabular/api"
}

# Main execution
main() {
    print_header "🚀 CENTRALIZED LOGGING DEPLOYMENT"
    
    check_permissions
    check_dependencies
    create_directories
    deploy_stack
    wait_for_services
    show_status
    
    print_header "🎉 DEPLOYMENT COMPLETE!"
    echo "Your centralized logging infrastructure is now running."
    echo "Use './logs.sh' to view and manage logs from your template and tabular services."
}

# Run main function
main "$@" 