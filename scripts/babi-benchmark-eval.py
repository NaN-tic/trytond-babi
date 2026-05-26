#!/usr/bin/env python3
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.

import datetime
import statistics
import timeit
from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace

from dateutil.relativedelta import relativedelta
from simpleeval import EvalWithCompoundTypes

from trytond.modules.babi.babi_eval import (
    date,
    day,
    month,
    safe_getattr,
    safe_hasattr,
    safe_isinstance,
    week,
    year,
    year_month,
    year_month_day,
)
from trytond.pool import Pool
from trytond.transaction import Transaction


@dataclass
class Case:
    name: str
    expression: str
    obj: object
    digits: int | None = None
    ttype: str | None = None


BASE_FUNCTIONS = {
    'Pool': Pool,
    'Transaction': Transaction,
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
    'Decimal': Decimal,
    'str': str,
    'getattr': safe_getattr,
    'hasattr': safe_hasattr,
    'isinstance': safe_isinstance,
}


def normalize(value, digits=None, ttype=None):
    if digits:
        if isinstance(value, (int, float)) and ttype == 'numeric':
            value = Decimal(value)
        if isinstance(value, Decimal):
            quantize = Decimal(10) ** -Decimal(digits)
            value = value.quantize(quantize)
        elif isinstance(value, float):
            value = round(value, digits)
    return value


def native_eval(expression, obj, digits=None, ttype=None):
    objects = {'o': obj}
    objects.update(BASE_FUNCTIONS)
    return normalize(eval(expression, objects), digits=digits, ttype=ttype)


def simpleeval_fresh(expression, obj, digits=None, ttype=None):
    evaluator = EvalWithCompoundTypes(
        names={'o': obj}, functions=BASE_FUNCTIONS.copy())
    return normalize(evaluator.eval(expression), digits=digits, ttype=ttype)


def simpleeval_reused(evaluator, expression, obj, digits=None, ttype=None):
    evaluator.names = {'o': obj}
    return normalize(evaluator.eval(expression), digits=digits, ttype=ttype)


def benchmark(case, number, repeat):
    reused = EvalWithCompoundTypes(
        names={'o': case.obj}, functions=BASE_FUNCTIONS.copy())

    def run_native():
        native_eval(case.expression, case.obj, case.digits, case.ttype)

    def run_fresh():
        simpleeval_fresh(case.expression, case.obj, case.digits, case.ttype)

    def run_reused():
        simpleeval_reused(
            reused, case.expression, case.obj, case.digits, case.ttype)

    native_times = timeit.repeat(run_native, number=number, repeat=repeat)
    fresh_times = timeit.repeat(run_fresh, number=number, repeat=repeat)
    reused_times = timeit.repeat(run_reused, number=number, repeat=repeat)

    return {
        'native': native_times,
        'simpleeval_fresh': fresh_times,
        'simpleeval_reused': reused_times,
    }


def mean_us(times, number):
    return statistics.mean(times) * 1_000_000 / number


def slowdown(times, baseline):
    return statistics.mean(times) / statistics.mean(baseline)


def main():
    party = SimpleNamespace(rec_name='Benchmark Party')
    record = SimpleNamespace(
        id=42,
        category='odd',
        amount=Decimal('25.50'),
        date=datetime.date(2026, 1, 15),
        party=party,
    )
    cases = [
        Case('field', 'o.category', record),
        Case('date_helpers', 'ymd(o.date - relativedelta(days=1))', record),
        Case('nested_attr', 'o.party.rec_name', record),
        Case('ternary_decimal',
            '"big" if o.amount > Decimal("20") else "small"', record),
        Case('getattr_hasattr',
            'getattr(o, "category").upper() if hasattr(o, "category") else ""',
            record),
        Case('list_comp',
            '",".join([str(x) for x in [y(o.date), m(o.date), d(o.date)]])',
            record),
    ]

    number = 20_000
    repeat = 7

    print(f'Iterations per sample: {number}')
    print(f'Samples per case: {repeat}')
    print()
    print(
        'case'.ljust(18),
        'eval us/call'.rjust(14),
        'simpleeval us/call'.rjust(20),
        'slowdown'.rjust(10),
        'reused us/call'.rjust(18),
        'slowdown'.rjust(10),
    )
    print('-' * 92)

    for case in cases:
        timings = benchmark(case, number=number, repeat=repeat)
        native_us = mean_us(timings['native'], number)
        fresh_us = mean_us(timings['simpleeval_fresh'], number)
        reused_us = mean_us(timings['simpleeval_reused'], number)
        fresh_slowdown = slowdown(
            timings['simpleeval_fresh'], timings['native'])
        reused_slowdown = slowdown(
            timings['simpleeval_reused'], timings['native'])
        print(
            case.name.ljust(18),
            f'{native_us:14.3f}',
            f'{fresh_us:20.3f}',
            f'{fresh_slowdown:10.2f}x',
            f'{reused_us:18.3f}',
            f'{reused_slowdown:10.2f}x',
        )

    print()
    print('Interpretation:')
    print('- `simpleeval us/call` matches the current babi_eval pattern.')
    print('- `reused us/call` isolates the evaluator engine cost if reused.')


if __name__ == '__main__':
    main()
