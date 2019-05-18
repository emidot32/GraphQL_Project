from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker

# Create database engine
url = "postgresql://[here enter your db username]:[your password]@localhost:5432/my_books"
engine = create_engine(url)

# Declarative base model to create database tables and classes
Base = declarative_base()
Base.metadata.bind = engine  # Bind engine to metadata of the base class

# Create database session object
db_session = scoped_session(sessionmaker(bind=engine, expire_on_commit=False))
Base.query = db_session.query_property()  # Used by graphql to execute queries