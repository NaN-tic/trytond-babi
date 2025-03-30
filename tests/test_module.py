
# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.

import datetime
import random
from decimal import Decimal

from trytond.pool import Pool
from trytond.tests.test_tryton import ModuleTestCase, with_transaction
from trytond.transaction import Transaction
from trytond.modules.babi.babi_eval import babi_eval
from trytond.pyson import PYSONEncoder
from trytond.modules.company.tests import CompanyTestMixin

class BabiCompanyTestMixin(CompanyTestMixin):

    @property
    def _skip_company_rule(self):
        return super()._skip_company_rule | {
            ('babi.table', 'company'),
            ('babi.warning', 'company'),
            }


class BabiTestCase(BabiCompanyTestMixin, ModuleTestCase):
    'Test Babi module'
    module = 'babi'

    def create_data(self):
        pool = Pool()
        TestModel = pool.get('babi.test')
        Model = pool.get('ir.model')
        Expression = pool.get('babi.expression')
        Filter = pool.get('babi.filter')

        to_create = []
        year = datetime.date.today().year
        for month in range(1, 13):
            # Create at least one record for each category in each month
            num_records = int(round(random.random() * 10)) + 2
            for x in range(0, num_records):
                category = 'odd' if x % 2 == 0 else 'even'
                day = int(random.random() * 28) + 1
                amount = Decimal(str(round(random.random() * 10000, 2)))
                to_create.append({
                        'date': datetime.date(year, month, day),
                        'category': category,
                        'amount': amount,
                        })

        TestModel.create(to_create)
        model, = Model.search([('name', '=', 'babi.test')])
        Model.write([model], {
                'babi_enabled': True
                })

        Expression.create([{
                    'name': 'Id',
                    'model': model.id,
                    'ttype': 'integer',
                    'expression': 'o.id',
                    }, {
                    'name': 'Year',
                    'model': model.id,
                    'ttype': 'char',
                    'expression': 'y(o.date)',
                    }, {
                    'name': 'Month',
                    'model': model.id,
                    'ttype': 'char',
                    'expression': 'm(o.date)',
                    }, {
                    'name': 'Category',
                    'model': model.id,
                    'ttype': 'char',
                    'expression': 'o.category',
                    }, {
                    'name': 'Amount',
                    'model': model.id,
                    'ttype': 'numeric',
                    'expression': 'o.amount',
                    }, {
                    'name': 'Amount this month',
                    'model': model.id,
                    'ttype': 'numeric',
                    'expression': ('o.amount if o.date >= '
                        'today() - relativedelta(days=today().day - 1) '
                        'else 0.0'),
                    }])

        Filter.create([{
                    'name': 'Odd',
                    'model': model.id,
                    'domain': "[('category', '=', 'odd')]",
                     }, {
                    'name': 'Even',
                    'model': model.id,
                    'domain': "[('category', '=', 'even')]",
                     }, {
                    'name': 'Date',
                    'model': model.id,
                    'domain': PYSONEncoder().encode([
                            ('date', '>=', datetime.date(year, 6, 1)),
                            ]),
                     }])
        Transaction().commit()

    @with_transaction()
    def test_eval(self):
        'Test babi_eval'
        pool = Pool()
        Model = pool.get('ir.model')
        date = datetime.date(2014, 10, 10)
        other_date = datetime.date(2014, 1, 1)
        tests = [
            ('o', None, '(empty)'),
            ('y(o)', date, str(date.year)),
            ('m(o)', date, str(date.month)),
            ('m(o)', other_date, '0' + str(other_date.month)),
            ('d(o)', date, str(date.day)),
            ('d(o)', other_date, '0' + str(other_date.day)),
            ('w(o)', other_date, '00'),
            ('ym(o)', date, '2014-10'),
            ('ym(o)', other_date, '2014-01'),
            ('ymd(o)', date, '2014-10-10'),
            ('ymd(o)', other_date, '2014-01-01'),
            ('date(o)', date, date),
            ('date(o).year', date, 2014),
            ('int(o)', 1.0, 1),
            ('float(o)', 1, 1.0),
            ('max(o[0], o[1])', (date, other_date,), date),
            ('min(o[0], o[1])', (date, other_date,), other_date),
            ('today()', None, datetime.date.today()),
            ('o - relativedelta(days=1)', date, datetime.date(2014, 10, 9)),
            ('o - relativedelta(months=1)', date, datetime.date(2014, 9, 10)),
            ('str(o)', 3.14, '3.14'),
            ('Decimal(o)', 3.14, Decimal(3.14)),
            ('Decimal(0)', None, Decimal(0)),
        ]
        models = Model.search([('name', '=', 'babi.test')])
        tests.append(
            ('Pool().get(\'ir.model\').search(['
                '(\'name\', \'=\', \'babi.test\')])', None, models),
            )
        for expression, obj, result in tests:
            self.assertEqual(babi_eval(expression, obj), result)
        with Transaction().set_context(date=date):
            self.assertEqual(babi_eval(
                    'Transaction().context.get(\'date\')', None), date)

        self.assertEqual(babi_eval('o', None, convert_none='zero'), '0')
        self.assertEqual(babi_eval('o', None, convert_none=''), '')
        self.assertEqual(babi_eval('o', None, convert_none=None), None)

    @with_transaction()
    def test_table(self):
        pool = Pool()
        Table = pool.get('babi.table')
        Field = pool.get('babi.field')
        Model = pool.get('ir.model')
        Expression = pool.get('babi.expression')

        self.create_data()

        table = Table()
        table.type = 'model'
        table.name = 'Table 1'
        table.on_change_name()
        self.assertEqual(table.internal_name, 'table_1')
        table.model, = Model.search([('name', '=', 'babi.test')])

        fields = []
        names = set([])
        for expression in Expression.search([], order=[('name', 'ASC')]):
            field = Field()
            field.expression = expression
            field.on_change_expression()
            field.on_change_name()
            if field.name in names:
                continue
            names.add(field.name)
            fields.append(field)

        table.fields_ = fields
        table.save()
        table._compute()

        cursor = Transaction().connection.cursor()
        cursor.execute('SELECT count(*) FROM "%s"' % table.table_name)
        count = cursor.fetchall()[0][0]
        self.assertNotEqual(count, 0)

        table = Table()
        table.type = 'table'
        table.name = 'Table 2'
        table.on_change_name()
        table.query = 'SELECT amount, category FROM babi_test'
        table.save()
        table._compute()
        fields = sorted([x.internal_name for x in table.fields_])
        self.assertEqual(fields, ['amount', 'category'])

        table.query = 'SELECT date, amount FROM babi_test'
        table.save()
        table._compute()
        fields = sorted([x.internal_name for x in table.fields_])
        self.assertEqual(fields, ['amount', 'date'])


del ModuleTestCase
