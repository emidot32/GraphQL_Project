from graphene_sqlalchemy import SQLAlchemyObjectType
from app.base import db_session
import graphene
from graphql_relay.node.node import from_global_id
from app.read_books_model import ReadBooksModel


def input_to_dictionary(input):
    """Method to convert Graphene inputs into dictionary"""
    dictionary = {}
    for key in input:
        # Convert GraphQL global id to database id
        if key[-2:] == 'id':
            input[key] = from_global_id(input[key])[1]
        dictionary[key] = input[key]
    return dictionary


class ReadBooksAttribute:
    #id = graphene.ID(description="id of the book.")
    name = graphene.String(description="Name of the book.")
    author = graphene.String(description="Author of the book.")
    date = graphene.Date(description="Date of reading.")


class ReadBooks(SQLAlchemyObjectType, ReadBooksAttribute):
    """Read books node."""

    class Meta:
        model = ReadBooksModel
        interfaces = (graphene.relay.Node,)


class AddBookInput(graphene.InputObjectType, ReadBooksAttribute):
    """Arguments to add a book."""
    pass


class AddBook(graphene.Mutation):
    """Mutation to add a book."""
    book = graphene.Field(lambda: ReadBooks, description="Read book added by this mutation.")

    class Arguments:
        input = AddBookInput(required=True)

    def mutate(self, info, input):
        data = input_to_dictionary(input)
        book = ReadBooksModel(**data)
        db_session.add(book)
        db_session.commit()

        return AddBook(book=book)


class EditRecordInput(graphene.InputObjectType, ReadBooksAttribute):
    """Arguments to update a book."""
    id = graphene.ID(required=True, description="Global Id of the book.")


class EditRecord(graphene.Mutation):
    """Update a book."""
    book = graphene.Field(lambda: ReadBooks, description="Books updated by this mutation.")

    class Arguments:
        input = EditRecordInput(required=True)

    def mutate(self, info, input):
        data = input_to_dictionary(input)
        book = db_session.query(ReadBooksModel).filter_by(id=data['id'])
        book.update(data)
        db_session.commit()
        book = db_session.query(ReadBooksModel).filter_by(id=data['id']).first()
        return EditRecord(book=book)


class DeleteBookInput(graphene.InputObjectType, ReadBooksAttribute):
    """Arguments to delete a book."""
    id = graphene.ID(required=False, description="Global Id of the book.")
    name = graphene.String(required=False, description="Global name of the book.")


class DeleteBook(graphene.Mutation):
    """Delete a book."""
    book = graphene.Field(lambda: ReadBooks, description="Book deleted by this mutation.")

    class Arguments:
        input = DeleteBookInput(required=False)

    def mutate(self, info, input):
        data = input_to_dictionary(input)
        if data.get("id") is not None:
            book = db_session.query(ReadBooksModel).filter_by(id=data['id'])
        else:
            book = db_session.query(ReadBooksModel).filter_by(id=data['name'])
        book.delete()
        db_session.commit()
        return DeleteBook(book=book)
