build:
<<<<<<< HEAD
	docker compose up --build -d --remove-orphans

up:
	docker compose up -d

down:
	docker compose down

down-v:
	docker compose down -v

rebuild:
	docker compose build --no-cache
	docker compose up -d --remove-orphans

nextgen-config:
	docker compose config

makemigrations:
	docker compose exec -it api alembic revision --autogenerate -m "$(name)"

migrate:
	docker compose exec -it api alembic upgrade head

history:
	docker compose exec -it api alembic history

current-migration:
	docker compose exec -it api alembic current

downgrade:
	docker compose exec -it api alembic downgrade $(version)
=======
	docker compose -f docker-compose.yml up --build -d --remove-orphans

up:
	docker compose -f docker-compose.yml up -d

down:
	docker compose -f docker-compose.yml down

down-v:
	docker compose -f docker-compose.yml down -v

rebuild:
	docker compose -f docker-compose.yml build --no-cache
	docker compose -f docker-compose.yml up -d --remove-orphans

nextgen-config:
	docker compose -f docker-compose.yml config

makemigrations:
	docker compose -f docker-compose.yml exec -it api alembic revision --autogenerate -m "$(name)"

migrate:
	docker compose -f docker-compose.yml exec -it api alembic upgrade head

history:
	docker compose -f docker-compose.yml exec -it api alembic history

current-migration:
	docker compose -f docker-compose.yml exec -it api alembic current

downgrade:
	docker compose -f docker-compose.yml exec -it api alembic downgrade $(version)
>>>>>>> 4e894b3 (fix: stabilize live monitoring and incident metadata)

inspect-network:
	docker network inspect nextgen_local_nw

psql:
<<<<<<< HEAD
	docker compose exec -it postgres psql -U fayedolla -d nextgen

logs:
	docker compose logs -f api

db-clear-alembic:
	docker compose exec postgres psql -U fayedolla -d nextgen -c "DELETE FROM alembic_version;"

check-models:
	docker compose exec api python -c "from backend.app.core.model_registry import load_models; from sqlmodel import SQLModel; load_models(); print(SQLModel.metadata.tables.keys())"

shell:
	docker compose exec -it api bash
=======
	docker compose -f docker-compose.yml exec -it postgres psql -U fayedolla -d nextgen

logs:
	docker compose -f docker-compose.yml logs -f api

db-clear-alembic:
	docker compose -f docker-compose.yml exec postgres psql -U fayedolla -d nextgen -c "DELETE FROM alembic_version;"

check-models:
	docker compose -f docker-compose.yml exec api python -c "from backend.app.core.model_registry import load_models; from sqlmodel import SQLModel; load_models(); print(SQLModel.metadata.tables.keys())"

shell:
	docker compose -f docker-compose.yml exec -it api bash
>>>>>>> 4e894b3 (fix: stabilize live monitoring and incident metadata)

exp-req:
	uv export --format requirements-txt --no-hashes > backend/requirements.txt