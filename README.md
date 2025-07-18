# Centralized Logging Infrastructure

This repository contains a complete centralized logging solution for monitoring template and tabular services using Grafana, Loki, Promtail, and Alertmanager.

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Template      │    │   Tabular       │    │   Other         │
│   Services      │    │   Services      │    │   Services      │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          └──────────────────────┼──────────────────────┘
                                 │
                    ┌─────────────▼─────────────┐
                    │        Promtail           │
                    │   (Log Collector)         │
                    └─────────────┬─────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │          Loki             │
                    │   (Log Aggregator)        │
                    └─────────────┬─────────────┘
                                  │
          ┌───────────────────────┼───────────────────────┐
          │                       │                       │
┌─────────▼─────────┐  ┌─────────▼─────────┐  ┌─────────▼─────────┐
│     Grafana       │  │   Log API         │  │   Alertmanager    │
│  (Visualization)  │  │  (REST API)       │  │   (Alerts)        │
└───────────────────┘  └───────────────────┘  └───────────────────┘
```

## 📋 Prerequisites

- Docker and Docker Compose installed
- User added to docker group
- Ports 3000, 3100, 8888, 9093 available

## 🚀 Quick Start

1. **Clone and navigate to the repository:**

   ```bash
   cd logging
   ```

2. **Deploy the logging infrastructure:**

   ```bash
   ./deploy-logging.sh
   ```

3. **Access the services:**
   - **Grafana**: http://localhost:3000 (admin/admin123)
   - **Loki**: http://localhost:3100
   - **Log API**: http://localhost:8888
   - **Alertmanager**: http://localhost:9093

## 📊 Monitored Services

### Template Services

- `template-backend-api` - Main API service
- `template-backend-celery-worker` - Celery worker
- `template-backend-celery-beat` - Celery beat scheduler
- `template-backend-nginx-ssl` - Nginx reverse proxy
- `template-backend-redis` - Redis cache

### Tabular Services

- `tabular-bakcend-backend` - Main API service
- `tabular-bakcend-celery-worker` - Celery worker
- `tabular-bakcend-celery-beat` - Celery beat scheduler
- `tabular-review-nginx-ssl` - Nginx reverse proxy
- `tabular-review-redis` - Redis cache

## 🛠️ Usage

### Using the Log Management Script

```bash
# View service health summary
./logs.sh

# Show recent activity (last 10 minutes)
./logs.sh 2

# Tail all logs in real-time
./logs.sh 3

# Show errors only
./logs.sh 4

# Show logs for specific service
./logs.sh 5 template-backend-api

# Export all logs to files
./logs.sh 6
```

### Using the Log API

```bash
# Check API health
curl http://localhost:8888/health

# Get template API logs (last hour)
curl http://localhost:8888/logs/template/api

# Get tabular API errors (last 24 hours)
curl http://localhost:8888/errors/tabular/api

# Search logs across all services
curl "http://localhost:8888/search?query=error&stack=template"

# Get log summary
curl http://localhost:8888/summary
```

### Using Grafana

1. Open http://localhost:3000
2. Login with admin/admin123
3. Navigate to Explore
4. Select Loki as data source
5. Use queries like:
   - `{stack="template"}` - All template service logs
   - `{stack="tabular"}` - All tabular service logs
   - `{container_name="template-backend-api"}` - Specific container logs
   - `{stack=~"template|tabular"} |~ "(?i)(error|exception)"` - Error logs

## 🔧 Configuration

### Loki Configuration

- **File**: `loki/config/local-config.yml`
- **Features**: File-based storage, 7-day retention, embedded cache

### Promtail Configuration

- **File**: `promtail/config/config.yml`
- **Features**: Docker service discovery, automatic labeling, log parsing

### Grafana Configuration

- **Datasource**: `grafana/provisioning/datasources/loki.yml`
- **Features**: Pre-configured Loki datasource, derived fields for trace IDs

### Alertmanager Configuration

- **File**: `alertmanager/config.yml`
- **Features**: Webhook notifications, alert grouping, inhibition rules

## 📈 Log Queries Examples

### Basic Queries

```logql
# All logs from template services
{stack="template"}

# All logs from tabular services
{stack="tabular"}

# Specific container logs
{container_name="template-backend-api"}

# Error logs only
{stack=~"template|tabular"} |~ "(?i)(error|exception|failed)"
```

### Advanced Queries

```logql
# Logs with specific labels
{stack="template", component="api"}

# Logs from last hour
{stack="template"} |~ "request_id"

# Rate of logs per minute
rate({stack="template"}[1m])

# Top containers by log volume
topk(5, sum by (container_name) (count_over_time({stack=~"template|tabular"}[5m])))
```

## 🚨 Troubleshooting

### Common Issues

1. **Promtail can't access Docker socket:**

   ```bash
   sudo usermod -aG docker $USER
   # Log out and log back in
   ```

2. **Services not showing up in Grafana:**

   - Check if containers are running: `docker ps`
   - Verify Promtail configuration matches container names
   - Check Promtail logs: `docker logs centralized-promtail`

3. **Log API not responding:**
   - Check if log-api container is running
   - Verify network connectivity between services
   - Check log-api logs: `docker logs centralized-log-api`

### Health Checks

```bash
# Check all service status
docker-compose -f docker-compose.logging.yml ps

# Check individual service health
curl http://localhost:8888/health
curl http://localhost:3100/ready
curl http://localhost:3000/api/health

# View service logs
docker logs centralized-loki
docker logs centralized-grafana
docker logs centralized-promtail
docker logs centralized-log-api
```

## 🔄 Maintenance

### Updating Services

```bash
# Pull latest images
docker-compose -f docker-compose.logging.yml pull

# Restart services
docker-compose -f docker-compose.logging.yml up -d
```

### Backup and Restore

```bash
# Backup volumes
docker run --rm -v centralized-logging_loki-data:/data -v $(pwd):/backup alpine tar czf /backup/loki-backup.tar.gz -C /data .
docker run --rm -v centralized-logging_grafana-data:/data -v $(pwd):/backup alpine tar czf /backup/grafana-backup.tar.gz -C /data .

# Restore volumes
docker run --rm -v centralized-logging_loki-data:/data -v $(pwd):/backup alpine tar xzf /backup/loki-backup.tar.gz -C /data
docker run --rm -v centralized-logging_grafana-data:/data -v $(pwd):/backup alpine tar xzf /backup/grafana-backup.tar.gz -C /data
```

### Cleanup

```bash
# Stop and remove services
docker-compose -f docker-compose.logging.yml down

# Remove volumes (WARNING: This will delete all data)
docker-compose -f docker-compose.logging.yml down -v
```

## 📝 API Endpoints

### Log API Endpoints

| Endpoint                    | Method | Description                            |
| --------------------------- | ------ | -------------------------------------- |
| `/`                         | GET    | API information and available services |
| `/health`                   | GET    | Health check for all services          |
| `/logs/{stack}/{service}`   | GET    | Get logs for specific service          |
| `/errors/{stack}/{service}` | GET    | Get error logs for specific service    |
| `/search`                   | GET    | Search logs across all services        |
| `/summary`                  | GET    | Get log activity summary               |

### Query Parameters

- `hours`: Number of hours to look back (default: 1)
- `limit`: Maximum number of log entries (default: 100)
- `query`: Search query for log content
- `stack`: Filter by stack (template/tabular)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License.
