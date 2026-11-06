"""Exact property selection shared by business views and the field picker."""
import re


def resolve_property(entity, reference):
    if not isinstance(reference, str) or not reference:
        raise ValueError('Select a known entity property')
    columns = entity['columns']
    exact = [column for column in columns if column['sql_name'] == reference]
    if len(exact) == 1:
        return exact[0]
    matches = [column for column in columns if column['name'] == reference or
               f"{column.get('source_kind', '')}:{column.get('source_qname', '')}" == reference]
    if len(matches) != 1:
        raise ValueError('Property is missing or ambiguous; select its exact SQL field identifier')
    return matches[0]


def numeric_type(sql_type):
    return sql_type in {'NUMERIC', 'INTEGER', 'BIGINT', 'SMALLINT', 'REAL', 'DOUBLE PRECISION'} or bool(
        re.fullmatch(r'NUMERIC\([1-9][0-9]{0,3},[0-9]{1,4}\)', str(sql_type)))
