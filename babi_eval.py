# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from decimal import Decimal
import datetime
from functools import lru_cache
import math
from dateutil.relativedelta import relativedelta
from simpleeval import EvalWithCompoundTypes
from trytond.pool import Pool
from trytond.transaction import Transaction


def year(text):
    if not text:
        return None
    text = str(text)
    return text[0:4]


def year_month(text):
    if not text:
        return None
    text = str(text)
    return text[0:4] + '-' + text[5:7]


def year_month_day(text):
    if not text:
        return None
    text = str(text)
    return text[0:10]


def month(text):
    if not text:
        return None
    text = str(text)
    return text[5:7]


def day(text):
    if not text:
        return None
    text = str(text)
    return text[8:10]


def week(text):
    if not text:
        return None
    return datetime.datetime.strptime(year_month_day(text),
        '%Y-%m-%d').strftime('%W')


def date(text):
    if not text:
        return None
    return datetime.datetime.strptime(year_month_day(text), '%Y-%m-%d').date()


def safe_getattr(obj, attr, default=None):
    return getattr(obj, attr, default)


def safe_hasattr(obj, attr):
    return hasattr(obj, attr)


def safe_isinstance(obj, classes):
    return isinstance(obj, classes)


def safe_pool(name):
    return Pool().get(name)

def safe_transaction():
    return Transaction()


FUNCTIONS = {
    'y': year,
    'm': month,
    'd': day,
    'w': week,
    'ym': year_month,
    'ymd': year_month_day,
    'date': date,
    'int': int,
    'float': float,
    'sum': sum,
    'min': min,
    'max': max,
    'now': datetime.datetime.now,
    'today': datetime.date.today,
    'relativedelta': relativedelta,
    'math': math,
    'Decimal': Decimal,
    'str': str,
    'pool': safe_pool,
    'transaction': safe_transaction,
    'getattr': safe_getattr,
    'hasattr': safe_hasattr,
    'isinstance': safe_isinstance,
    }


@lru_cache(maxsize=1024)
def _get_parsed_expression(expression):
    return EvalWithCompoundTypes.parse(expression)


@lru_cache(maxsize=256)
def _get_batch_expression(expressions):
    if len(expressions) == 1:
        return f'({expressions[0]},)'
    return '(' + ', '.join(expressions) + ')'


def _normalize_value(value, convert_none='empty', digits=None, ttype=None):
    if (value is False or value is None):
        if convert_none == 'empty':
            # TODO: Make translatable
            value = '(empty)'
        elif convert_none == 'zero':
            value = '0'
        else:
            value = convert_none
    if digits:
        if isinstance(value, (int, float)) and ttype == 'numeric':
            value = Decimal(value)
        if isinstance(value, Decimal):
            quantize = Decimal(10) ** -Decimal(digits)
            value = value.quantize(quantize)
        elif isinstance(value, float):
            value = round(value, digits)
    return value


def _expand_batch_option(option, size):
    if isinstance(option, (list, tuple)):
        assert len(option) == size
        return option
    return [option] * size


def babi_eval(expression, obj, convert_none='empty', digits=None, ttype=None):
    return babi_eval_batch([expression], obj, convert_none=convert_none,
        digits=digits, ttypes=ttype)[0]


def babi_eval_batch(expressions, obj, convert_none='empty', digits=None,
        ttypes=None):
    expressions = tuple(expressions)
    if not expressions:
        return tuple()

    evaluator = EvalWithCompoundTypes(
        names={'o': obj}, functions=FUNCTIONS.copy())
    if len(expressions) == 1:
        value = evaluator.eval(expressions[0],
            previously_parsed=_get_parsed_expression(expressions[0]))
        return (_normalize_value(value, convert_none=convert_none,
                digits=digits, ttype=ttypes),)

    batch_expression = _get_batch_expression(expressions)
    values = evaluator.eval(batch_expression,
        previously_parsed=_get_parsed_expression(batch_expression))
    convert_nones = _expand_batch_option(convert_none, len(expressions))
    digits_list = _expand_batch_option(digits, len(expressions))
    ttypes_list = _expand_batch_option(ttypes, len(expressions))
    return tuple(_normalize_value(value, convert_none=convert_none_,
            digits=digits_, ttype=ttype_)
        for value, convert_none_, digits_, ttype_
        in zip(values, convert_nones, digits_list, ttypes_list))
