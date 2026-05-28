#!/usr/bin/env python3
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.

import datetime
import statistics
import timeit
from decimal import Decimal
from types import SimpleNamespace

from trytond.modules.babi.babi_eval import babi_eval, babi_eval_batch


SIZES = [1, 2, 5, 10, 15, 20, 25, 50, 100]
NUMBER = 5_000
REPEAT = 5


def mean_us(times):
    return statistics.mean(times) * 1_000_000 / NUMBER


def build_expressions(size):
    expressions = []
    while len(expressions) < size:
        expressions.extend(BASE_EXPRESSIONS)
    return expressions[:size]


BASE_EXPRESSIONS = [
    'o.id',
    'o.category',
    'o.amount',
    'y(o.date)',
    'm(o.date)',
    'd(o.date)',
    'ymd(o.date - relativedelta(days=1))',
    'o.party.rec_name',
    'getattr(o, "category").upper() if hasattr(o, "category") else ""',
    '"big" if o.amount > Decimal("20") else "small"',
]


def main():
    party = SimpleNamespace(rec_name='Benchmark Party')
    record = SimpleNamespace(
        id=42,
        category='odd',
        amount=Decimal('25.50'),
        date=datetime.date(2026, 1, 15),
        party=party,
    )
    print(f'Iterations per sample: {NUMBER}')
    print(f'Samples per case: {REPEAT}')
    print()
    print('exprs'.rjust(5), 'separate us/record'.rjust(20),
        'batch us/record'.rjust(18), 'speedup'.rjust(10),
        'sep us/expr'.rjust(14), 'batch us/expr'.rjust(16))
    print('-' * 92)
    for size in SIZES:
        expressions = build_expressions(size)
        separate_result = tuple(babi_eval(expr, record)
            for expr in expressions)
        batch_result = babi_eval_batch(expressions, record,
            convert_none='empty')
        assert separate_result == batch_result, (
            size, separate_result, batch_result)

        def run_separate():
            return tuple(babi_eval(expr, record) for expr in expressions)

        def run_batch():
            return babi_eval_batch(expressions, record,
                convert_none='empty')

        separate_times = timeit.repeat(run_separate, number=NUMBER,
            repeat=REPEAT)
        batch_times = timeit.repeat(run_batch, number=NUMBER, repeat=REPEAT)
        separate_us = mean_us(separate_times)
        batch_us = mean_us(batch_times)
        speedup = (statistics.mean(separate_times)
            / statistics.mean(batch_times))

        print(
            f'{size:5d}'
            f'{separate_us:20.3f}'
            f'{batch_us:18.3f}'
            f'{speedup:10.2f}x'
            f'{separate_us / size:14.3f}'
            f'{batch_us / size:16.3f}')
    print('Notes:')
    print('- Both paths use the current babi_eval implementation.')
    print('- The batch path evaluates one tuple expression per record.')
    print('- Speedup depends on how many expressions are grouped together.')


if __name__ == '__main__':
    main()
