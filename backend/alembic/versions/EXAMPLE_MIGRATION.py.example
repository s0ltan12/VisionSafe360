"""EXAMPLE MIGRATION - Do Not Apply

This file shows the structure and common patterns of Alembic migrations.
It is NOT a real migration and should not be applied.

For actual migrations, see the numbered files in this directory (e.g., 23137d6336b1_*.py).

Revision ID: example_revision
Revises: 
Create Date: 2026-04-21 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'example_revision'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Example upgrade operations:
    
    1. Add a new column:
    """
    # op.add_column('incidents', sa.Column('priority', sa.String(50), nullable=True))
    
    """
    2. Create a new table:
    """
    # op.create_table(
    #     'audit_logs',
    #     sa.Column('id', sa.Integer, primary_key=True),
    #     sa.Column('action', sa.String(255), nullable=False),
    #     sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id')),
    #     sa.Column('created_at', sa.DateTime, default=sa.func.now()),
    # )
    
    """
    3. Add an index:
    """
    # op.create_index('idx_incidents_status', 'incidents', ['status'])
    
    """
    4. Add a unique constraint:
    """
    # op.create_unique_constraint('uq_users_email', 'users', ['email'])
    
    """
    5. Modify a column:
    """
    # op.alter_column('users', 'role', existing_type=sa.String(50), new_column_name='user_role')
    
    """
    6. Drop a column:
    """
    # op.drop_column('incidents', 'legacy_field')
    
    """
    7. Execute raw SQL:
    """
    # op.execute("UPDATE incidents SET status = 'ACTIVE' WHERE status IS NULL")
    pass


def downgrade() -> None:
    """
    Example downgrade operations (reverse of upgrade):
    
    1. Drop the new column:
    """
    # op.drop_column('incidents', 'priority')
    
    """
    2. Drop the new table:
    """
    # op.drop_table('audit_logs')
    
    """
    3. Drop the index:
    """
    # op.drop_index('idx_incidents_status', table_name='incidents')
    
    """
    4. Drop the unique constraint:
    """
    # op.drop_constraint('uq_users_email', 'users', type_='unique')
    pass


"""
COMMON PATTERNS:

1. Adding a Required Column with Default:
   
   op.add_column('table_name', sa.Column('new_column', sa.String(255), nullable=False, server_default='default_value'))
   op.alter_column('table_name', 'new_column', server_default=None)  # Remove default after migration

2. Backfilling Data Before Adding Constraint:
   
   op.add_column('users', sa.Column('status', sa.String(50), nullable=True))
   op.execute("UPDATE users SET status = 'ACTIVE' WHERE status IS NULL")
   op.alter_column('users', 'status', nullable=False)

3. Renaming a Column:
   
   op.alter_column('users', 'role', new_column_name='user_role')

4. Creating a Foreign Key:
   
   op.create_foreign_key(
       'fk_incidents_camera_id',
       'incidents',
       'cameras',
       ['camera_id'],
       ['id'],
       ondelete='CASCADE'
   )

5. Complex Data Migration with Raw SQL:
   
   op.execute('''
       UPDATE incidents
       SET severity = CASE
           WHEN impact_level > 5 THEN 'HIGH'
           WHEN impact_level > 2 THEN 'MEDIUM'
           ELSE 'LOW'
       END
   ''')

MIGRATION LIFECYCLE:

1. Developer modifies model in app/models/models.py
2. Developer runs: alembic revision --autogenerate -m "Description"
3. Developer REVIEWS the generated migration file
4. Developer tests: alembic upgrade head && alembic downgrade -1
5. Developer commits the migration file to git
6. On deployment, operations run: alembic upgrade head

FOR HELP:
- See MIGRATIONS_GUIDE.md for detailed instructions
- See Alembic docs: https://alembic.sqlalchemy.org/
"""
