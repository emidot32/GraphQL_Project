from collections import defaultdict
from decimal import Decimal

import graphene
from graphene.types import Scalar
from graphene_sqlalchemy.converter import (convert_sqlalchemy_type, convert_column_to_string,
                                           get_column_doc, is_column_nullable)
from graphene.types.datetime import DateTime as GrapheneDateTime
from graphene_sqlalchemy import SQLAlchemyObjectType
from graphql.language import ast
from sqlalchemy.dialects import postgresql
from sqlalchemy import desc, or_, and_, types as sqltypes


class PassThroughType(Scalar):
    @staticmethod
    def serialize(value):
        return value

    @staticmethod
    def parse_value(value):
        return value

    @staticmethod
    def parse_literal(node):
        return node.value


class CurrencyType(Scalar):
    @staticmethod
    def serialize(value):
        return float(value)

    @classmethod
    def parse_literal(cls, node):
        return cls.parse_value(node.value)

    @staticmethod
    def parse_value(value):
        val = Decimal(str(value))
        assert round(val, 2) == val, 'Too many decimal places'
        return val


ARG_TYPES = defaultdict(lambda: graphene.String)
ARG_TYPES[sqltypes.DateTime] = GrapheneDateTime
ARG_TYPES[sqltypes.SmallInteger] = graphene.Int
ARG_TYPES[sqltypes.Integer] = graphene.Int
ARG_TYPES[sqltypes.Boolean] = graphene.Boolean
ARG_TYPES[postgresql.NUMERIC] = CurrencyType
ARG_TYPES[postgresql.JSONB] = graphene.JSONString



@convert_sqlalchemy_type.register(postgresql.JSONB)
def convert_column_to_dict(type, column, registry=None):
    return PassThroughType(description=get_column_doc(column),
                           required=not(is_column_nullable(column)))




# mid level: give me a model and i'll give you a resolver or a mutator

# TODO: Document the filter syntax
def args_to_filters(model, attrs, args):
    # Used both in app API "resources" and in filtering admin graphql queries.
    clauses = []
    clause_joiners = {
        'and': and_,
        'or': or_,
    }
    # TODO: loop over the args instead of the filterables, since an arg might be provided more
    # than once, as when doing "x=>:10&x=<:100"
    for fname in attrs:
        if fname in args:
            # there might be an operator
            arg = args[fname]
            if isinstance(arg, str):
                op, sep, val_string = arg.partition(':')
                if sep == '':
                    # no operator supplied.  assume '='.  pull val from first position.
                    val_string = op
                    op = '='
                vals = val_string.split('|')
            else:
                op = '='
                vals = [arg]
            attr = getattr(model, fname)
            if op == '=':
                clauses.append(attr.in_(vals))
            elif op == '!':
                clauses.append(~attr.in_(vals))
    if clauses:
        joiner = clause_joiners[args.get('qtype', 'and')]
        joined_clauses = joiner(*clauses)
        return [joined_clauses]
    return []


def build_resolver(model):
    def resolve(self, info, **kwargs):
        q = info.context['db'].query(model)
        order_by = kwargs.pop('order_by', None)
        order_by_desc = kwargs.pop('order_by_desc', None)

        if kwargs:
            field_names = model.__table__.columns.keys()
            q = q.filter(*args_to_filters(model, field_names, kwargs))

        if order_by:
            field = getattr(model, order_by)
            if order_by_desc:
                field = desc(field)
            q = q.order_by(field)
        return q.all()
    return resolve


INPUT_OBJECTS = {}
def build_input_object(model):
    if model not in INPUT_OBJECTS:
        INPUT_OBJECTS[model] = type(
            model.__name__ + 'Input',
            (graphene.InputObjectType,),
            {c.name: ARG_TYPES[c.type.__class__]() for c in model.__table__.columns if c.name!='id'}
        )
    return INPUT_OBJECTS[model]


MODEL_OBJECTS = {}
def build_model_object(model, base=SQLAlchemyObjectType):
    if model not in MODEL_OBJECTS:
        obj = type(model.__name__, (base,), {
            'Meta': type('Meta', (), {'model': model})
        })

        # If the model has a graphene_extra_fields classmethod, call that
        # and use the returned dict to set extra fields
        if callable(getattr(model, 'graphene_extra_fields', None)):
            extras = model.graphene_extra_fields()
            for k, v in extras.items():
                obj._meta.fields[k] = v
        MODEL_OBJECTS[model] = obj
    return MODEL_OBJECTS[model]


def build_model_arguments(model):
    arguments = {
        'order_by': graphene.Argument(graphene.String),
        'order_by_desc': graphene.Argument(graphene.Boolean),
    }
    for k, v in model.__dict__.items():
        if k in model.__table__.columns:
            col = model.__table__.columns[k]
            # we have some columns named 'type' but graphene doesn't like that since it uses it as a
            # kwarg in the Argument constructor.
            if k == 'type':
                k = 'type_'
            arguments[k] = graphene.Argument(ARG_TYPES[col.type.__class__])
    return arguments


def build_creator(model):
    attrs = {}

    input_obj = build_input_object(model)
    Arguments = type('Arguments', (), {'_data': graphene.Argument(input_obj)})
    attrs['Arguments'] = Arguments

    obj = build_model_object(model)
    instance_field_name = model.__name__.lower()
    attrs[instance_field_name] = graphene.Field(lambda: obj)

    def mutate(cls, root, info, **kwargs):
        db = info.context['db']
        instance = model(**kwargs['_data'])
        db.add(instance)
        db.commit()
        return cls(**{instance_field_name: instance})


    attrs['mutate'] = classmethod(mutate)

    creator = type(
        'Create' + model.__name__,
        (graphene.Mutation,),
        attrs
    )

    return creator


def build_updater(model):
    attrs = {}

    # new fields to be set will be in the 'Data' argument, which looks like '_data' on the python
    # side.  Graphene does that name mangling by default, but the use of "Data" for the new fields
    # is an HPX convention.
    input_obj = build_input_object(model)
    input_attrs = {'_data': graphene.Argument(input_obj)}
    if 'id' in model.__table__.columns:
        # most of our IDs are strings, but some are integers.  Build our lookup field with the right
        # type.
        input_attrs['id'] = ARG_TYPES[model.__table__.columns.id.type]()

    Arguments = type('Arguments', (), input_attrs)
    attrs['Arguments'] = Arguments

    instance_field_name = model.__name__.lower()
    obj = build_model_object(model)
    attrs[instance_field_name] = graphene.Field(lambda: obj)

    def mutate(cls, root, info, **kwargs):
        db = info.context['db']
        instance = db.query(model).filter_by(id=kwargs['id']).one()
        data_in = kwargs.get('_data', {})
        for k, v in data_in.items():
            setattr(instance, k, v)
        db.commit()
        return cls(**{instance_field_name: instance})

    attrs['mutate'] = classmethod(mutate)

    updater = type(
        'Update' + model.__name__,
        (graphene.Mutation,),
        attrs
    )
    return updater


def build_deleter(model):
    pass

# high level: give me all your models and i'll give you a schema with query and mutation all filled
# in.

def build_query_object(models, extra_attrs=None):
    attrs = extra_attrs or {}
    for model in models:
        name = model.__name__.lower()
        attrs[name] = graphene.List(
            build_model_object(model),
            **build_model_arguments(model)
        )
        attrs['resolve_' + name] = build_resolver(model)
    return type('Query', (graphene.ObjectType,), attrs)


def build_mutation_object(models, extra_attrs=None):
    attrs = extra_attrs or {}
    for model in models:
        name = model.__name__.lower()
        attrs['create_' + name] = build_creator(model).Field()
        attrs['update_' + name] = build_updater(model).Field()
    return type('Mutation', (graphene.ObjectType,), attrs)


def build_schema(models, query_extras=None, mutation_extras=None):
    query = build_query_object(models, extra_attrs=query_extras)
    mutation = build_mutation_object(models, extra_attrs=mutation_extras)
    return graphene.Schema(query=query, mutation=mutation)
