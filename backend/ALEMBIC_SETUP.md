# Alembic Migration Setup - Complete

This document summarizes the Alembic database migration system integrated into VisionSafe 360.

## What Was Set Up

### Files Created/Modified

1. **alembic.ini**
   - Main Alembic configuration file
   - Configured to use `alembic/` as the migrations directory
   - Reads `DATABASE_URL` from environment variables

2. **alembic/env.py**
   - Alembic environment script
   - Imports all SQLAlchemy models for autogenerate detection
   - Reads `DATABASE_URL` from `app/config/database.py` or environment
   - Supports both online (direct DB) and offline (SQL generation) modes

3. **alembic/versions/**
   - Migration directory
   - Contains numbered migration files
   - Initial migration generated: `23137d6336b1_initial_migration_create_users_cameras_.py`

4. **MIGRATIONS_GUIDE.md**
   - Comprehensive user guide with examples
   - Quick start instructions
   - Workflow examples
   - Docker and Kubernetes deployment info

5. **alembic/README**
   - Quick reference for the alembic directory structure
   - Common task shortcuts

6. **alembic/versions/EXAMPLE_MIGRATION.py**
   - Reference file showing migration patterns
   - Demonstrates upgrade/downgrade operations
   - Common patterns and best practices

## Current Configuration

### Database Connection

Alembic reads the database URL from:
1. Environment variable: `DATABASE_URL`
2. Fallback in `alembic.ini`: `postgresql://postgres:postgres@localhost:5432/visionsafe360`
3. Code source: `app/config/database.py`

### Models Tracked for Autogenerate

The following models are imported in `alembic/env.py`:
- `User`
- `Camera`
- `Incident`
- `Alert`

Any schema changes to these models will be detected by `alembic revision --autogenerate`.

## Key Commands

### Common Operations

```bash
cd backend

# Generate a new migration
alembic revision --autogenerate -m "Description of changes"

# Apply all pending migrations
alembic upgrade head

# Revert last migration
alembic downgrade -1

# Check current database revision
alembic current

# Show migration history
alembic history --verbose

# Show all migration heads
alembic heads
```

### Deployment

```bash
# Before deploying new code
alembic upgrade head

# In Docker
docker exec <backend-container> alembic upgrade head

# With docker-compose
docker-compose exec backend alembic upgrade head
```

## Migration Workflow

1. **Modify Model**
   ```python
   # In app/models/models.py
   class User(Base):
       # ... existing fields
       phone = Column(String(20))  # New field
   ```

2. **Generate Migration**
   ```bash
   alembic revision --autogenerate -m "Add phone field to User"
   ```

3. **Review Generated File**
   - Opens `alembic/versions/<revision_id>_add_phone_field_to_user.py`
   - Check upgrade() and downgrade() functions
   - Edit if needed for custom logic

4. **Test Locally**
   ```bash
   alembic upgrade head           # Apply
   alembic downgrade -1           # Revert
   alembic upgrade head           # Apply again
   ```

5. **Commit to Git**
   ```bash
   git add alembic/versions/<revision_id>_*.py
   git commit -m "Migration: Add phone field to User"
   ```

6. **Deploy**
   ```bash
   # Run migrations before or after code deployment
   alembic upgrade head
   ```

## Docker Integration

### Running Migrations in docker-compose

```bash
# Apply migrations to existing database
docker-compose exec backend alembic upgrade head

# Check migration status
docker-compose exec backend alembic current

# Revert last migration
docker-compose exec backend alembic downgrade -1
```

### Adding Auto-Migration Service

You can add a migration service that runs before the main backend:

```yaml
# In docker-compose.yml
services:
  db-migrate:
    build: ./backend
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/visionsafe360
    command: sh -c "alembic upgrade head"
    depends_on:
      - db
    networks:
      - visionsafe

  backend:
    build: ./backend
    depends_on:
      - db-migrate  # Ensures migrations run first
      - db
    # ... rest of backend config
```

## Environment Variables

Ensure your `.env` file (or deployment environment) has:

```bash
# Database connection
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/visionsafe360

# Optional: Override in alembic.ini
# ALEMBIC_SQLALCHEMY_URL=...
```

## Verification

To verify Alembic is properly configured:

```bash
cd backend

# Check alembic command works
alembic current

# See migration history
alembic history

# Verify no pending migrations
alembic heads
```

Expected output for `alembic current`:
```
23137d6336b1
```

Expected output for `alembic history`:
```
<base> -> 23137d6336b1 (head), Initial migration: create users cameras incidents alerts tables
```

## Troubleshooting

### "Import failed for app.models"

**Issue**: Alembic can't find your models.

**Solution**:
- Ensure `alembic/env.py` imports all model classes
- Check that `app/config/database.py` is accessible
- Verify PYTHONPATH includes the backend directory

### "No changes detected" when autogenerating

**Issue**: Alembic didn't detect model changes.

**Solutions**:
- Review the model changes are syntactically correct
- Check that the model is imported in `alembic/env.py`
- Force a database refresh or manually write the migration
- Run `alembic revision -m "Description"` for manual migration

### "Cannot downgrade" error

**Issue**: A migration failed to downgrade.

**Solutions**:
- Review the downgrade() function in the migration file
- Some operations cannot be safely reversed (e.g., data deletion)
- Add custom SQL in the downgrade() function if needed
- Contact your DBA if the database is already at that revision

### Database connection refused

**Issue**: Alembic can't connect to the database.

**Solutions**:
- Verify `DATABASE_URL` environment variable is set correctly
- Ensure PostgreSQL is running
- Check database credentials
- Test: `python -c "from app.config.database import DATABASE_URL; print(DATABASE_URL)"`

## Best Practices

1. ✅ **Always review autogenerated migrations** before applying
2. ✅ **Test upgrade AND downgrade** locally before committing
3. ✅ **Write descriptive messages** for each migration
4. ✅ **Keep migrations atomic** (one logical change per migration)
5. ✅ **Commit migration files to git** alongside model changes
6. ✅ **Never manually edit applied migrations** in production
7. ✅ **Test with production-like data** before deployment
8. ✅ **Document complex migrations** with comments in the migration file

## References

- **Alembic Documentation**: https://alembic.sqlalchemy.org/
- **SQLAlchemy ORM**: https://docs.sqlalchemy.org/
- **This Project's Migration Guide**: See `MIGRATIONS_GUIDE.md`

## Support

For questions or issues:
1. Check `MIGRATIONS_GUIDE.md` for detailed examples
2. Review `alembic/versions/EXAMPLE_MIGRATION.py` for patterns
3. Consult Alembic official documentation
4. Review your specific migration file for errors

---

**Setup Date**: April 21, 2026  
**Alembic Version**: 1.13.2  
**Database**: PostgreSQL 16+  
**Status**: ✅ Configured and Ready
