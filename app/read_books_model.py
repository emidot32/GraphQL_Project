from app.base import Base
from sqlalchemy import Column, Integer, String, Date


class ReadBooksModel(Base):
    """Read books model."""

    __tablename__ = 'read_books'

    id = Column('id', Integer, primary_key=True)
    name = Column('name', String)
    author = Column('author', String)
    date = Column('date', Date)
