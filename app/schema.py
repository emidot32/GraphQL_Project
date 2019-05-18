from graphene_sqlalchemy import SQLAlchemyConnectionField
import graphene
import app.schema_read_books


class Query(graphene.ObjectType):
    """Query objects for GraphQL API."""

    node = graphene.relay.Node.Field()
    book = graphene.relay.Node.Field(app.schema_read_books.ReadBooks)
    books = SQLAlchemyConnectionField(app.schema_read_books.ReadBooks)


class Mutation(graphene.ObjectType):
    addBook = app.schema_read_books.AddBook.Field()
    editRecord = app.schema_read_books.EditRecord.Field()
    deleteBook = app.schema_read_books.DeleteBook.Field()


schema = graphene.Schema(query=Query, mutation=Mutation)
