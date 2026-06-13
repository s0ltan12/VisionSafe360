.PHONY: build up check-gpu down down-v rebuild config

# Always target the system Docker daemon. Docker Desktop on Linux runs in a VM
# and cannot pass through the host NVIDIA GPU.
DOCKER = docker --context default
COMPOSE = $(DOCKER) compose

build: check-gpu
	$(COMPOSE) up --build -d --remove-orphans

up: check-gpu
	$(COMPOSE) up -d

check-gpu:
	@command -v nvidia-smi >/dev/null 2>&1 || { echo "⚠ NVIDIA driver not found – worker will fall back to CPU."; }
	@$(DOCKER) info --format '{{json .Runtimes}}' 2>/dev/null | grep -q '"nvidia"' || { echo "⚠ NVIDIA runtime not registered in Docker – worker will fall back to CPU."; }

down:
	$(COMPOSE) down

down-v:
	$(COMPOSE) down -v

rebuild: check-gpu
	$(COMPOSE) build --no-cache
	$(COMPOSE) up -d --remove-orphans

config:
	$(COMPOSE) config

makemigrations:
	$(COMPOSE) exec -it api alembic revision --autogenerate -m "$(name)"

migrate:
	$(COMPOSE) exec -it api alembic upgrade head

history:
	$(COMPOSE) exec -it api alembic history

current-migration:
	$(COMPOSE) exec -it api alembic current

downgrade:
	$(COMPOSE) exec -it api alembic downgrade $(version)

inspect-network:
	$(DOCKER) network inspect visionsafe360_internal

psql:
	$(COMPOSE) exec -it db psql -U $${POSTGRES_USER:-postgres} -d $${POSTGRES_DB:-visionsafe360}

logs:
	$(COMPOSE) logs -f

db-clear-alembic:
	$(COMPOSE) exec db psql -U $${POSTGRES_USER:-postgres} -d $${POSTGRES_DB:-visionsafe360} -c "DELETE FROM alembic_version;"

check-models:
	$(COMPOSE) exec backend python -c "from backend.app.core.model_registry import load_models; from sqlmodel import SQLModel; load_models(); print(SQLModel.metadata.tables.keys())"

shell:
	$(COMPOSE) exec -it backend bash

exp-req:
	uv export --format requirements-txt --no-hashes > backend/requirements.txt

