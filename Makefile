# ══════════════════════════════════════════════════════════════════════════════
#  VisionSafe360 — Makefile
#  Usage: make <target>
#  Run `make help` to see all available targets.
# ══════════════════════════════════════════════════════════════════════════════

# ── Config ────────────────────────────────────────────────────────────────────
COMPOSE         := docker compose
ENV_FILE        := .env
BACKEND_SVC     := backend
WORKER_SVC      := worker
DASHBOARD_SVC   := dashboard
DB_SVC          := db
REDIS_SVC       := redis

# Colours
RESET  := \033[0m
BOLD   := \033[1m
GREEN  := \033[0;32m
YELLOW := \033[0;33m
CYAN   := \033[0;36m
RED    := \033[0;31m

.DEFAULT_GOAL := help
.PHONY: help \
        up down restart build rebuild \
        start stop \
        logs logs-backend logs-worker logs-dashboard logs-db logs-redis \
        ps status health \
        shell-backend shell-db shell-redis \
        db-reset db-shell \
        clean clean-all \
        check-env

# ══════════════════════════════════════════════════════════════════════════════
#  HELP
# ══════════════════════════════════════════════════════════════════════════════
help:
	@echo ""
	@echo "$(BOLD)$(CYAN)VisionSafe360 — Docker Makefile$(RESET)"
	@echo "$(CYAN)════════════════════════════════════════════$(RESET)"
	@echo ""
	@echo "$(BOLD)🚀 Startup$(RESET)"
	@echo "  $(GREEN)make up$(RESET)            Build (if needed) and start all services detached"
	@echo "  $(GREEN)make build$(RESET)         Build all Docker images without starting"
	@echo "  $(GREEN)make rebuild$(RESET)       Force rebuild all images (no cache) and start"
	@echo "  $(GREEN)make start$(RESET)         Start already-built containers (no rebuild)"
	@echo ""
	@echo "$(BOLD)🛑 Shutdown$(RESET)"
	@echo "  $(GREEN)make down$(RESET)          Stop and remove containers + network"
	@echo "  $(GREEN)make stop$(RESET)          Stop containers without removing them"
	@echo "  $(GREEN)make restart$(RESET)       Restart all services"
	@echo ""
	@echo "$(BOLD)📋 Logs$(RESET)"
	@echo "  $(GREEN)make logs$(RESET)          Tail logs for ALL services"
	@echo "  $(GREEN)make logs-backend$(RESET)  Tail backend logs only"
	@echo "  $(GREEN)make logs-worker$(RESET)   Tail worker logs only"
	@echo "  $(GREEN)make logs-dashboard$(RESET) Tail dashboard logs only"
	@echo "  $(GREEN)make logs-db$(RESET)       Tail Postgres logs only"
	@echo "  $(GREEN)make logs-redis$(RESET)    Tail Redis logs only"
	@echo ""
	@echo "$(BOLD)🔍 Status$(RESET)"
	@echo "  $(GREEN)make ps$(RESET)            List running containers"
	@echo "  $(GREEN)make status$(RESET)        Show health status of all services"
	@echo "  $(GREEN)make health$(RESET)        Hit /healthz and /readyz endpoints"
	@echo ""
	@echo "$(BOLD)🐚 Shells$(RESET)"
	@echo "  $(GREEN)make shell-backend$(RESET) Open bash inside backend container"
	@echo "  $(GREEN)make shell-db$(RESET)      Open psql inside db container"
	@echo "  $(GREEN)make shell-redis$(RESET)   Open redis-cli inside redis container"
	@echo ""
	@echo "$(BOLD)🗄️  Database$(RESET)"
	@echo "  $(GREEN)make db-reset$(RESET)      Drop postgres volume and restart fresh"
	@echo "  $(GREEN)make db-shell$(RESET)      Alias for shell-db"
	@echo ""
	@echo "$(BOLD)🧹 Cleanup$(RESET)"
	@echo "  $(GREEN)make clean$(RESET)         Remove containers, network (keep volumes)"
	@echo "  $(GREEN)make clean-all$(RESET)     Remove containers, network, volumes, images"
	@echo ""
	@echo "$(BOLD)⚙️  Misc$(RESET)"
	@echo "  $(GREEN)make check-env$(RESET)     Verify .env file exists and has required keys"
	@echo ""

# ══════════════════════════════════════════════════════════════════════════════
#  STARTUP
# ══════════════════════════════════════════════════════════════════════════════

## Build images (if changed) then start all services detached
up: check-env
	@echo "$(CYAN)▶  Starting VisionSafe360...$(RESET)"
	$(COMPOSE) up --build -d --remove-orphans
	@echo ""
	@echo "$(GREEN)✅ All services started!$(RESET)"
	@echo "$(BOLD)   Dashboard → http://localhost:$${DASHBOARD_PORT:-80}$(RESET)"
	@echo "$(BOLD)   API       → http://localhost:8000$(RESET)"
	@echo "$(BOLD)   API Docs  → http://localhost:8000/docs$(RESET)"
	@echo ""
	@echo "$(YELLOW)Waiting for health checks... run 'make status' in 30s$(RESET)"

## Build all images (without starting containers)
build: check-env
	@echo "$(CYAN)🔨 Building all Docker images...$(RESET)"
	$(COMPOSE) build

## Force rebuild from scratch (no cache) then start
rebuild: check-env
	@echo "$(CYAN)🔨 Rebuilding all images (no cache)...$(RESET)"
	$(COMPOSE) build --no-cache
	$(COMPOSE) up -d --remove-orphans
	@echo "$(GREEN)✅ Rebuild complete!$(RESET)"

## Start already-built containers without rebuilding
start: check-env
	@echo "$(CYAN)▶  Starting containers...$(RESET)"
	$(COMPOSE) up -d --remove-orphans
	@echo "$(GREEN)✅ Started!$(RESET)"

# ══════════════════════════════════════════════════════════════════════════════
#  SHUTDOWN
# ══════════════════════════════════════════════════════════════════════════════

## Stop and remove containers + network (volumes are preserved)
down:
	@echo "$(YELLOW)⏹  Stopping and removing containers...$(RESET)"
	$(COMPOSE) down --remove-orphans
	@echo "$(GREEN)✅ All containers stopped.$(RESET)"

## Stop containers (keep them, don't remove)
stop:
	@echo "$(YELLOW)⏸  Stopping containers...$(RESET)"
	$(COMPOSE) stop
	@echo "$(GREEN)✅ Stopped.$(RESET)"

## Restart all services
restart:
	@echo "$(CYAN)🔄 Restarting all services...$(RESET)"
	$(COMPOSE) restart
	@echo "$(GREEN)✅ Restarted.$(RESET)"

# ══════════════════════════════════════════════════════════════════════════════
#  LOGS  (Ctrl+C to exit any log stream)
# ══════════════════════════════════════════════════════════════════════════════

## Stream logs for ALL services
logs:
	$(COMPOSE) logs -f --tail=100

## Stream backend-only logs
logs-backend:
	$(COMPOSE) logs -f --tail=100 $(BACKEND_SVC)

## Stream worker-only logs
logs-worker:
	$(COMPOSE) logs -f --tail=100 $(WORKER_SVC)

## Stream dashboard-only logs
logs-dashboard:
	$(COMPOSE) logs -f --tail=100 $(DASHBOARD_SVC)

## Stream Postgres logs
logs-db:
	$(COMPOSE) logs -f --tail=100 $(DB_SVC)

## Stream Redis logs
logs-redis:
	$(COMPOSE) logs -f --tail=100 $(REDIS_SVC)

# ══════════════════════════════════════════════════════════════════════════════
#  STATUS / HEALTH
# ══════════════════════════════════════════════════════════════════════════════

## Show running containers with status
ps:
	$(COMPOSE) ps

## Compact health overview
status:
	@echo "$(CYAN)📊 Service Health Status$(RESET)"
	@echo "$(CYAN)─────────────────────────────────────$(RESET)"
	$(COMPOSE) ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

## Hit the backend health endpoints
health:
	@echo "$(CYAN)🏥 Checking backend health...$(RESET)"
	@curl -sf http://localhost:8000/healthz && echo " $(GREEN)✅ /healthz OK$(RESET)" || echo " $(RED)❌ /healthz FAIL$(RESET)"
	@curl -sf http://localhost:8000/readyz  && echo " $(GREEN)✅ /readyz  OK$(RESET)" || echo " $(RED)❌ /readyz  FAIL$(RESET)"

# ══════════════════════════════════════════════════════════════════════════════
#  SHELLS
# ══════════════════════════════════════════════════════════════════════════════

## Open an interactive bash shell inside the backend container
shell-backend:
	$(COMPOSE) exec $(BACKEND_SVC) /bin/bash

## Open psql inside the Postgres container
shell-db:
	$(COMPOSE) exec $(DB_SVC) psql -U $${POSTGRES_USER:-postgres} -d $${POSTGRES_DB:-visionsafe360}

## Open redis-cli inside the Redis container
shell-redis:
	$(COMPOSE) exec $(REDIS_SVC) redis-cli

# ══════════════════════════════════════════════════════════════════════════════
#  DATABASE
# ══════════════════════════════════════════════════════════════════════════════

## Alias for shell-db
db-shell: shell-db

## ⚠️  Drop the postgres_data volume and restart fresh (ALL DATA LOST)
db-reset:
	@echo "$(RED)⚠️  WARNING: This will DELETE all database data!$(RESET)"
	@printf "$(YELLOW)Are you sure? [y/N] $(RESET)" && read ans && [ "$${ans}" = "y" ] || (echo "Aborted." && exit 1)
	$(COMPOSE) down -v --remove-orphans
	$(COMPOSE) up --build -d --remove-orphans
	@echo "$(GREEN)✅ Database reset complete. Fresh seed data will load on startup.$(RESET)"

# ══════════════════════════════════════════════════════════════════════════════
#  CLEANUP
# ══════════════════════════════════════════════════════════════════════════════

## Remove containers and network (volumes are kept)
clean:
	@echo "$(YELLOW)🧹 Removing containers and network...$(RESET)"
	$(COMPOSE) down --remove-orphans
	@echo "$(GREEN)✅ Clean done (volumes preserved).$(RESET)"

## Remove containers, network, volumes AND local images (full reset)
clean-all:
	@echo "$(RED)⚠️  This removes ALL containers, volumes, and images for this project!$(RESET)"
	@printf "$(YELLOW)Are you sure? [y/N] $(RESET)" && read ans && [ "$${ans}" = "y" ] || (echo "Aborted." && exit 1)
	$(COMPOSE) down --volumes --remove-orphans --rmi local
	@echo "$(GREEN)✅ Full cleanup done.$(RESET)"

# ══════════════════════════════════════════════════════════════════════════════
#  MISC
# ══════════════════════════════════════════════════════════════════════════════

## Check that .env exists and has the critical keys
check-env:
	@test -f $(ENV_FILE) || (echo "$(RED)❌ .env file not found! Copy .env.example to .env and fill in the values.$(RESET)" && exit 1)
	@grep -q "^SECRET_KEY=" $(ENV_FILE)       || (echo "$(RED)❌ .env is missing SECRET_KEY$(RESET)"       && exit 1)
	@grep -q "^POSTGRES_PASSWORD=" $(ENV_FILE) || (echo "$(RED)❌ .env is missing POSTGRES_PASSWORD$(RESET)" && exit 1)
	@echo "$(GREEN)✅ .env looks good.$(RESET)"
