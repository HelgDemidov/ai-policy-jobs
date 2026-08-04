"""add_search_vector

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-04 22:10:32.349310

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Raw SQL, not op.add_column: a STORED generated column with a tsvector
    expression isn't expressible through SQLAlchemy Core's Column, and
    tsvector/GIN have no SQLite equivalent — this is the one place the
    schema stops being dialect-portable (spec §5). title outweighs
    description in ranking (setweight 'A' vs 'B').
    """
    op.execute(
        """
        ALTER TABLE postings ADD COLUMN search_vector tsvector
          GENERATED ALWAYS AS (
            setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
            setweight(to_tsvector('english', coalesce(description, '')), 'B')
          ) STORED
        """
    )
    op.execute("CREATE INDEX ix_postings_search_vector ON postings USING GIN (search_vector)")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS ix_postings_search_vector")
    op.execute("ALTER TABLE postings DROP COLUMN IF EXISTS search_vector")
