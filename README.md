<p align="center">
  <img src="dashboard/logo.svg" alt="VisionSafe 360" width="80" />
</p>

<h1 align="center">VisionSafe 360</h1>

<p align="center">
  <strong>AI-Powered Industrial Safety Monitoring Platform</strong><br />
  Real-time PPE detection · Fall detection · Incident management · Live video streaming
</p>

<p align="center">
  <img src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=white" alt="React" />
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql&logoColor=white" alt="PostgreSQL" />
  <img src="https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white" alt="Redis" />
  <img src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white" alt="Docker" />
  <img src="https://img.shields.io/badge/Nginx-1.27-009639?logo=nginx&logoColor=white" alt="Nginx" />
</p>

---

## Table of Contents

- [Project Overview](#project-overview)
- [Key Features](#key-features)
- [Tech Stack](#tech-stack)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Project Structure](#project-structure)
- [Environment Configuration](#environment-configuration)
- [How to Run the Project](#how-to-run-the-project)
- [Accessing the Application](#accessing-the-application)
- [Default Login Credentials](#default-login-credentials)
- [How the System Works](#how-the-system-works)
- [Authentication Flow](#authentication-flow)
- [Video Streaming](#video-streaming)
- [WebSocket Real-Time Communication](#websocket-real-time-communication)
- [Makefile Commands Reference](#makefile-commands-reference)
- [Troubleshooting](#troubleshooting)
- [Development Notes](#development-notes)
- [Production Deployment](#production-deployment)
- [License](#license)

---

## Project Overview

**VisionSafe 360** is an industrial safety monitoring platform that uses Edge AI to detect workplace hazards in real time. It provides a unified dashboard for safety engineers, administrators, and data analysts to monitor live camera feeds, review AI-generated safety alerts, manage incidents, and analyze safety trends across industrial facilities.

The system runs entirely in Docker containers: a React dashboard served by Nginx acts as both the frontend and the reverse proxy to a FastAPI backend, which connects to PostgreSQL for persistence and Redis for caching and job queuing.

---

## Key Features

| Feature | Description |
| :--- | :--- |
| **Live Video Monitoring** | Stream test videos with real-time AI overlay (motion detection, fall detection, PPE checks) |
| **Safety Alerts** | Automatic alert generation with severity levels (High / Medium / Low) |
| **Incident Management** | Full CRUD for incident records with zone, classification, root cause, and corrective actions |
| **Real-Time WebSockets** | Live incident feed pushed to the dashboard without page refresh |
| **Role-Based Access Control** | Three roles: Admin, Safety Engineer, Data Analyst — each with different dashboard access |
| **Ergonomic Monitoring** | Track and analyze ergonomic risk assessments |
| **Camera Management** | Register, configure, and monitor camera health |
| **Analytics & Reports** | Time-series charts, severity breakdowns, zone heatmaps |
| **System Health** | Live metrics for backend, database, Redis, and WebSocket connections |
| **Bilingual UI** | Full English and Arabic interface with RTL support |
| **pgAdmin** | Built-in database administration panel |

---

## Tech Stack

### Frontend
| Technology | Version | Purpose |
| :--- | :--- | :--- |
| React | 19.x | UI framework |
| TypeScript | 5.8 | Type safety |
| Vite | 6.x | Build tool and dev server |
| Recharts | 3.x | Data visualization and charts |
| Lucide React | 0.556 | Icon library |

### Backend
| Technology | Version | Purpose |
| :--- | :--- | :--- |
| FastAPI | 0.115 | REST API framework |
| Uvicorn | 0.30 | ASGI server |
| SQLAlchemy | 2.0 | ORM and database toolkit |
| Pydantic | 2.9 | Data validation and schemas |
| pg8000 | 1.31 | Pure-Python PostgreSQL driver |
| Redis (py) | 5.0 | Caching and rate limiting |
| RQ | 1.16 | Background job queue (Edge AI jobs) |
| OpenCV | 4.10 | Video processing and AI overlay |
| python-jose | 3.3 | JWT token creation and validation |
| Passlib + bcrypt | — | Password hashing |
| Sentry SDK | 2.58 | Error monitoring (optional) |

### Infrastructure
| Technology | Version | Purpose |
| :--- | :--- | :--- |
| Docker & Docker Compose | Latest | Containerization and orchestration |
| Nginx | 1.27 | Reverse proxy, static file serving, WebSocket proxying |
| PostgreSQL | 16 Alpine | Primary database |
| Redis | 7 Alpine | Cache, rate limiting, job queue broker |
| pgAdmin 4 | Latest | Database administration UI |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        Browser (Client)                          │
│                                                                  │
│  http://localhost      → Dashboard (React SPA)                   │
│  http://localhost/api/ → REST API calls                          │
│  ws://localhost/ws/    → WebSocket (live incidents)               │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                    Nginx  (Port 80)                               │
│                                                                  │
│  /           → Serve React static files (index.html, JS, CSS)    │
│  /api/*      → proxy_pass http://backend:8000                    │
│  /ws/*       → proxy_pass http://backend:8000 (WebSocket upgrade)│
└────────────┬──────────────────────────────┬──────────────────────┘
             │                              │
             ▼                              ▼
┌────────────────────────┐    ┌────────────────────────────────────┐
│  FastAPI Backend        │    │  RQ Worker                         │
│  (Port 8000)            │    │  (Edge AI job execution)           │
│                         │    │                                    │
│  • REST API endpoints   │    │  • Runs AI inference on video      │
│  • JWT authentication   │    │  • Creates incidents from results  │
│  • WebSocket server     │    │  • Broadcasts via WebSocket        │
│  • Video streaming      │    │                                    │
└─────────┬───────┬───────┘    └──────────┬────────────────────────┘
          │       │                       │
          ▼       ▼                       ▼
   ┌────────┐  ┌───────┐          ┌────────────────┐
   │Postgres│  │ Redis │          │ edge_ai/       │
   │  (DB)  │  │(Cache)│          │ vids_test/*.mp4│
   └────────┘  └───────┘          └────────────────┘
```

---

## Prerequisites

Before you begin, make sure you have the following installed:

| Requirement | Minimum Version | Check Command |
| :--- | :--- | :--- |
| **Docker** | 24.x+ | `docker --version` |
| **Docker Compose** | v2.x+ (included with Docker Desktop) | `docker compose version` |
| **Git** | 2.x+ | `git --version` |
| **Make** (optional but recommended) | Any | `make --version` |

### Ports Required

| Port | Service | Notes |
| :--- | :--- | :--- |
| `80` | Dashboard + Nginx | Main entry point for the application |
| `5050` | pgAdmin | Database administration panel |

> **Note:** Ports `8000` (backend), `5432` (PostgreSQL), and `6379` (Redis) are internal to the Docker network and are **not** exposed to your host machine. All external access goes through Nginx on port 80.

---

## Project Structure

```
VisionSafe360/
├── backend/                    # FastAPI backend application
│   ├── app/
│   │   ├── api/
│   │   │   ├── routes/         # REST API route handlers
│   │   │   │   ├── alerts.py
│   │   │   │   ├── analytics.py
│   │   │   │   ├── auth.py         # Login & JWT
│   │   │   │   ├── cameras.py
│   │   │   │   ├── config_route.py
│   │   │   │   ├── edge_config.py
│   │   │   │   ├── ergonomics.py
│   │   │   │   ├── health.py       # /healthz and /readyz
│   │   │   │   ├── incidents.py
│   │   │   │   ├── jobs.py         # Edge AI job control
│   │   │   │   ├── media.py        # Video streaming
│   │   │   │   ├── monitoring.py
│   │   │   │   ├── notifications_route.py
│   │   │   │   ├── stats.py
│   │   │   │   └── users.py
│   │   │   └── websocket/
│   │   │       ├── ws_handler.py       # /ws/incidents
│   │   │       └── ws_notifications.py # /ws/notifications
│   │   ├── config/
│   │   │   ├── database.py     # SQLAlchemy engine & session
│   │   │   └── settings.py     # Pydantic BaseSettings
│   │   ├── models/             # SQLAlchemy ORM models
│   │   ├── schemas/            # Pydantic request/response schemas
│   │   ├── services/           # Business logic layer
│   │   ├── utils/              # Security, logging, Sentry
│   │   ├── main.py             # FastAPI app entry point
│   │   └── seed.py             # Demo data seeder
│   ├── Dockerfile
│   ├── requirements.txt
│   └── worker.py               # RQ worker entry point
│
├── dashboard/                  # React frontend application
│   ├── components/             # React page components
│   │   ├── Dashboard.tsx
│   │   ├── LiveMonitoring.tsx
│   │   ├── Alerts.tsx
│   │   ├── Incidents.tsx
│   │   ├── Reports.tsx
│   │   ├── CameraManagement.tsx
│   │   ├── UserManagement.tsx
│   │   ├── Ergonomics.tsx
│   │   ├── SystemHealth.tsx
│   │   ├── Configuration.tsx
│   │   ├── Login.tsx
│   │   └── VisionSafeLogo.tsx
│   ├── contexts/               # React context providers
│   ├── nginx/
│   │   └── default.conf        # Nginx reverse proxy configuration
│   ├── api.ts                  # API client (fetch wrapper)
│   ├── types.ts                # TypeScript type definitions
│   ├── App.tsx                 # Root application component
│   ├── index.tsx               # React entry point
│   ├── index.html
│   ├── Dockerfile              # Multi-stage build (Node → Nginx)
│   ├── vite.config.ts
│   └── package.json
│
├── edge_ai/                    # Edge AI module
│   ├── vids_test/              # Test video files (.mp4)
│   ├── weights/                # YOLO model weights
│   ├── configs/                # AI pipeline configuration
│   └── demo_pipeline.py        # Standalone AI demo script
│
├── docker-compose.yml          # Multi-service orchestration
├── Makefile                    # Convenience commands
├── .env                        # Environment variables (git-ignored)
├── .env.example                # Template for .env
└── README.md                   # ← You are here
```

---

## Environment Configuration

### Quick Setup

```bash
# Copy the example file
cp .env.example .env
```

### Required Variables

Edit `.env` and set at minimum these two values:

```dotenv
# A strong password for PostgreSQL
POSTGRES_PASSWORD=your_secure_password

# A random 32+ character key for JWT signing
# Generate one with: python3 -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=your_64_char_hex_string_here
```

### Full Variable Reference

| Variable | Default | Description |
| :--- | :--- | :--- |
| `POSTGRES_DB` | `visionsafe360` | Database name |
| `POSTGRES_USER` | `postgres` | Database username |
| `POSTGRES_PASSWORD` | **required** | Database password |
| `SECRET_KEY` | **required** | JWT signing secret (min 32 chars) |
| `JWT_ALGORITHM` | `HS256` | JWT algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `480` | Token expiry (8 hours) |
| `REDIS_HOST` | `redis` | Redis hostname (Docker service name) |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_PASSWORD` | *(empty)* | Redis password |
| `ALLOWED_ORIGINS` | `http://localhost` | CORS allowed origins (comma-separated) |
| `APP_ENV` | `production` | Environment (`development` or `production`) |
| `DASHBOARD_PORT` | `80` | Host port for the dashboard |
| `VITE_API_BASE_URL` | *(empty)* | Leave empty for Docker (uses Nginx proxy) |
| `PGADMIN_DEFAULT_EMAIL` | `admin@visionsafe.com` | pgAdmin login email |
| `PGADMIN_DEFAULT_PASSWORD` | `admin` | pgAdmin login password |
| `PGADMIN_PORT` | `5050` | Host port for pgAdmin |
| `SENTRY_DSN` | *(empty)* | Sentry error monitoring DSN (optional) |
| `LOG_LEVEL` | `INFO` | Logging level |

---

## How to Run the Project

### Step 1: Clone the Repository

```bash
git clone https://github.com/hishammohamed445/VisionSafe360.git
cd VisionSafe360
```

### Step 2: Create Environment File

```bash
cp .env.example .env
```

Edit `.env` and set `POSTGRES_PASSWORD` and `SECRET_KEY`:

```bash
# Quick way to generate a secret key:
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### Step 3: Build and Start

Using **Make** (recommended):

```bash
make up
```

Or using **Docker Compose** directly:

```bash
docker compose up --build -d
```

### Step 4: Verify Everything is Running

```bash
# Check container status
make status

# Or:
docker compose ps
```

You should see all 6 services running:

| Container | Status |
| :--- | :--- |
| `visionsafe360-db-1` | Healthy |
| `visionsafe360-redis-1` | Healthy |
| `visionsafe360-backend-1` | Healthy |
| `visionsafe360-worker-1` | Running |
| `visionsafe360-dashboard-1` | Running |
| `visionsafe360-pgadmin-1` | Running |

### Step 5: Open the Application

Open your browser and navigate to **http://localhost**

---

## Accessing the Application

| Service | URL | Description |
| :--- | :--- | :--- |
| **Dashboard** | [http://localhost](http://localhost) | Main application interface |
| **API Documentation** | [http://localhost/api/docs](http://localhost/api/docs) | Interactive Swagger UI |
| **API ReDoc** | [http://localhost/api/redoc](http://localhost/api/redoc) | Alternative API docs |
| **pgAdmin** | [http://localhost:5050](http://localhost:5050) | Database management UI |

### pgAdmin Database Connection

After logging into pgAdmin, register a new server with these settings:

| Field | Value |
| :--- | :--- |
| **Host** | `db` |
| **Port** | `5432` |
| **Database** | `visionsafe360` |
| **Username** | `postgres` |
| **Password** | *(value from your `.env`)* |

---

## Default Login Credentials

The database is automatically seeded with three demo users on first startup:

| Role | Email | Password | Dashboard Access |
| :--- | :--- | :--- | :--- |
| **Admin** | `alex.m@visionsafe.co` | `Admin123` | Full access to all pages |
| **Safety Engineer** | `sarah.c@visionsafe.co` | `Safety123` | Monitoring, alerts, incidents, ergonomics |
| **Data Analyst** | `analyst@visionsafe.co` | `Analyst123` | Reports, incidents, ergonomics |

---

## How the System Works

### Request Flow

```
Browser Request
      │
      ▼
   Nginx (Port 80)
      │
      ├── Path: /              → Serve React SPA (index.html)
      ├── Path: /api/*         → Forward to FastAPI (backend:8000)
      ├── Path: /ws/*          → WebSocket upgrade to FastAPI
      └── Path: /assets/*      → Serve static files (JS, CSS, images)
```

### API Routing

The backend registers routes under two prefixes for compatibility:

| Prefix | Purpose |
| :--- | :--- |
| `/api/v1/...` | Versioned API (recommended for new integrations) |
| `/api/...` | Legacy prefix (used by current dashboard) |

**Key API Endpoints:**

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/auth/login` | Authenticate and receive JWT token |
| `GET` | `/api/auth/me` | Get current user profile |
| `GET` | `/api/stats` | Dashboard statistics summary |
| `GET` | `/api/alerts/all` | List all safety alerts |
| `GET` | `/api/cameras` | List registered cameras |
| `GET` | `/api/incidents/all` | List all incidents |
| `GET` | `/api/media/videos` | List available test videos |
| `GET` | `/api/media/videos/{name}` | Stream video file (MP4) |
| `GET` | `/api/media/video_feed/{name}` | Live MJPEG stream with AI overlay |
| `GET` | `/api/jobs/status` | Edge AI worker job status |
| `POST` | `/api/jobs/start` | Start Edge AI processing on a video |
| `POST` | `/api/jobs/stop` | Stop Edge AI processing |
| `GET` | `/healthz` | Liveness probe |
| `GET` | `/readyz` | Readiness probe (checks DB + Redis) |

---

## Authentication Flow

```
1. User opens http://localhost
       │
       ▼
2. React app checks localStorage for existing token
       │
       ├── Token found → Call GET /api/auth/me to validate
       │   ├── Valid   → Load dashboard
       │   └── Invalid → Clear token, show login page
       │
       └── No token → Show login page
       
3. User submits email + password
       │
       ▼
4. POST /api/auth/login
       │
       ├── 200 OK → { "access_token": "eyJ..." }
       │   └── Token saved to localStorage
       │       └── All subsequent requests include:
       │           Authorization: Bearer <token>
       │
       ├── 401 → Invalid credentials
       └── 429 → Too many attempts (rate limited)
```

**Security features:**
- Passwords are hashed with **bcrypt** (never stored in plain text)
- JWT tokens expire after **8 hours** by default
- Login attempts are **rate limited** to 5 per IP per 5 minutes
- All authentication events are written to an **audit log**

---

## Video Streaming

VisionSafe supports two video viewing modes in the Live Monitoring page:

### 1. File Mode (Direct MP4 Playback)

```
GET /api/media/videos/{video_name}
```

- Serves the raw `.mp4` file from `edge_ai/vids_test/`
- Uses the browser's native `<video>` player with controls
- Best for reviewing recorded footage

### 2. Stream Mode (Live MJPEG with AI Overlay)

```
GET /api/media/video_feed/{video_name}
```

- OpenCV reads the video frame-by-frame on the backend
- Each frame is processed with lightweight motion detection:
  - **Fall detection** (high aspect-ratio motion regions)
  - **PPE violation** (motion in upper frame regions)
  - **Normal activity** (standard motion)
- Annotated frames are sent as a continuous **MJPEG stream**
- Rendered in the browser via an `<img>` tag (auto-refreshing)
- Loops automatically when the video reaches the end

### Adding Test Videos

Place `.mp4` files in the `edge_ai/vids_test/` directory. They will automatically appear in the dashboard's Live Monitoring page after restarting the backend.

---

## WebSocket Real-Time Communication

The dashboard maintains a persistent WebSocket connection for live incident updates.

### Connection Details

| Property | Value |
| :--- | :--- |
| **Endpoint** | `ws://localhost/ws/incidents` |
| **Authentication** | Query parameter: `?token=<JWT>` |
| **Protocol** | JSON messages over WebSocket |

### Message Types

**Server → Client:**

```json
// On connection established
{
  "type": "connected",
  "timestamp": "2026-04-26T16:00:00+00:00",
  "message": "incident stream connected"
}

// When a new incident is created by the Edge AI worker
{
  "type": "incident_created",
  "incident": {
    "id": "INC-2026-042",
    "zone": "Zone A - Welding",
    "classification": "Near Miss",
    "severity": "High",
    "root_cause": "Worker not wearing helmet",
    "corrective_action": "Issue PPE reminder",
    "created_at": "2026-04-26T16:05:00+00:00"
  }
}
```

### Frontend Reconnection

The dashboard automatically reconnects with exponential backoff if the WebSocket connection drops:
- 1st retry: 1 second
- 2nd retry: 2 seconds
- 3rd retry: 3 seconds
- Maximum backoff: 10 seconds

---

## Makefile Commands Reference

The project includes a comprehensive Makefile for convenience:

### 🚀 Startup

| Command | Description |
| :--- | :--- |
| `make up` | Build images (if changed) and start all services |
| `make build` | Build all Docker images without starting |
| `make rebuild` | Force rebuild from scratch (no cache) and start |
| `make start` | Start already-built containers (no rebuild) |

### 🛑 Shutdown

| Command | Description |
| :--- | :--- |
| `make down` | Stop and remove containers (volumes preserved) |
| `make stop` | Stop containers without removing them |
| `make restart` | Restart all services |

### 📋 Logs

| Command | Description |
| :--- | :--- |
| `make logs` | Tail logs for all services |
| `make logs-backend` | Tail backend logs only |
| `make logs-worker` | Tail worker logs only |
| `make logs-dashboard` | Tail dashboard/Nginx logs only |
| `make logs-db` | Tail PostgreSQL logs only |
| `make logs-redis` | Tail Redis logs only |

### 🔍 Status & Health

| Command | Description |
| :--- | :--- |
| `make ps` | List running containers |
| `make status` | Show health status of all services |
| `make health` | Hit `/healthz` and `/readyz` endpoints |

### 🐚 Shells

| Command | Description |
| :--- | :--- |
| `make shell-backend` | Open bash inside backend container |
| `make shell-db` | Open `psql` inside PostgreSQL container |
| `make shell-redis` | Open `redis-cli` inside Redis container |

### 🗄️ Database

| Command | Description |
| :--- | :--- |
| `make db-shell` | Alias for `shell-db` |
| `make db-reset` | ⚠️ Drop database volume and restart fresh |

### 🧹 Cleanup

| Command | Description |
| :--- | :--- |
| `make clean` | Remove containers and network (keep volumes) |
| `make clean-all` | ⚠️ Remove everything including volumes and images |

---

## Troubleshooting

### Port 80 already in use

```
Error: Bind for 0.0.0.0:80 failed: port is already allocated
```

**Fix:** Change the dashboard port in `.env`:

```dotenv
DASHBOARD_PORT=3080
```

Then access the dashboard at `http://localhost:3080`.

---

### Docker daemon not running

```
Cannot connect to the Docker daemon
```

**Fix:** Start Docker Desktop or the Docker service:

```bash
sudo systemctl start docker
```

---

### 502 Bad Gateway

This means Nginx is running but the backend hasn't started yet.

**Fix:** Wait for the backend health check to pass (up to 30 seconds), then check:

```bash
make logs-backend
```

Common causes:
- Missing `SECRET_KEY` or `POSTGRES_PASSWORD` in `.env`
- Database not ready yet (health check still pending)

---

### WebSocket not connecting

If the dashboard shows "WS disconnected":

1. **Check if you are logged in** — WebSocket requires a valid JWT token
2. **Check backend logs:**
   ```bash
   make logs-backend | grep ws
   ```
3. **Verify Nginx WebSocket headers** — already configured in `dashboard/nginx/default.conf`

---

### Video not loading in Live Monitoring

1. **Check that test videos exist:**
   ```bash
   ls edge_ai/vids_test/*.mp4
   ```
2. **Check that the volume is mounted** — verify in `docker-compose.yml`:
   ```yaml
   volumes:
     - ./edge_ai/vids_test:/app/edge_ai/vids_test:ro
   ```
3. **Check backend logs for errors:**
   ```bash
   make logs-backend | grep media
   ```

---

### Database connection failed

```bash
# Check if the database container is healthy
docker compose ps db

# Check database logs
make logs-db

# Reset the database completely
make db-reset
```

---

### CORS errors in browser console

This should not happen when accessing via `http://localhost` because all requests go through Nginx (same origin). If you see CORS errors:

1. Make sure you are accessing `http://localhost`, not `http://localhost:8000`
2. Check `ALLOWED_ORIGINS` in `.env` includes your access URL

---

## Development Notes

### Running Frontend Locally (Hot Reload)

If you want to develop the React frontend outside Docker with hot reload:

```bash
cd dashboard
npm install
npm run dev
```

The dev server runs on `http://localhost:3000`. To connect to the Docker backend, create `dashboard/.env.local`:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
```

And make sure the backend's `ALLOWED_ORIGINS` includes `http://localhost:3000`.

---

### Running Backend Locally

```bash
cd backend
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL="postgresql+pg8000://postgres:postgres@localhost:5432/visionsafe360"
export SECRET_KEY="your_dev_secret_key_minimum_32_chars_long"

# Start the server with auto-reload
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

> You will need PostgreSQL and Redis running locally or via Docker.

---

### Useful Development Commands

```bash
# Watch backend logs in real time
make logs-backend

# Open a Python shell inside the backend container
make shell-backend

# Connect to the database directly
make shell-db

# Check API health
curl http://localhost/healthz
curl http://localhost/readyz
```

---

## Production Deployment

### Deploying on a VPS

1. **Set up a VPS** (Ubuntu 22.04+ recommended) with Docker installed
2. **Clone the repository** and configure `.env` with strong, unique secrets
3. **Change default passwords** for all seeded users
4. **Update `ALLOWED_ORIGINS`** in `.env` to your domain:
   ```dotenv
   ALLOWED_ORIGINS=https://yourdomain.com
   ```
5. **Build and start:**
   ```bash
   make up
   ```

### HTTPS with Let's Encrypt

The Nginx configuration includes a pre-written HTTPS block (commented out) in `dashboard/nginx/default.conf`.

To enable HTTPS:

1. **Obtain a certificate:**
   ```bash
   certbot certonly --webroot -w /usr/share/nginx/html -d yourdomain.com
   ```

2. **Uncomment the HTTPS server block** in `dashboard/nginx/default.conf`

3. **Expose port 443** in `docker-compose.yml`:
   ```yaml
   dashboard:
     ports:
       - "80:80"
       - "443:443"
   ```

4. **Mount the certificate volume:**
   ```yaml
   dashboard:
     volumes:
       - /etc/letsencrypt:/etc/letsencrypt:ro
   ```

5. **Rebuild the dashboard:**
   ```bash
   docker compose up --build -d dashboard
   ```

### Production Checklist

- [ ] Change all default user passwords
- [ ] Set a strong, unique `SECRET_KEY` (64+ hex chars)
- [ ] Set a strong `POSTGRES_PASSWORD`
- [ ] Set `APP_ENV=production`
- [ ] Configure `SENTRY_DSN` for error monitoring
- [ ] Set up HTTPS
- [ ] Configure firewall (only expose ports 80 and 443)
- [ ] Set up automated backups for the PostgreSQL volume
- [ ] Review and restrict `ALLOWED_ORIGINS`

---

## License

This project is developed as a graduation project. See the repository for license details.

---

<p align="center">
  Built with ❤️ by the VisionSafe Team
</p>
