import datetime
import unittest
from decimal import Decimal

from proteus import Model
from trytond.tests.test_tryton import drop_db
from trytond.tests.tools import activate_modules


class Test(unittest.TestCase):

    def setUp(self):
        drop_db()
        super().setUp()

    def tearDown(self):
        drop_db()
        super().tearDown()

    def test(self):

        # Activate module
        activate_modules('babi')

        # Create source records
        TestModel = Model.get('babi.test')
        record = TestModel()
        record.date = datetime.date(2026, 1, 15)
        record.category = 'odd'
        record.amount = Decimal('10.50')
        record.save()

        record = TestModel()
        record.date = datetime.date(2026, 1, 16)
        record.category = 'even'
        record.amount = Decimal('25.00')
        record.save()

        # Enable the model for BABI and define expressions
        IrModel = Model.get('ir.model')
        Expression = Model.get('babi.expression')
        model, = IrModel.find([('name', '=', 'babi.test')])
        model.babi_enabled = True
        model.save()

        expression = Expression()
        expression.name = 'Id'
        expression.model = model
        expression.ttype = 'integer'
        expression.expression = 'o.id'
        expression.save()
        id_expression = expression

        expression = Expression()
        expression.name = 'Category'
        expression.model = model
        expression.ttype = 'char'
        expression.expression = 'o.category'
        expression.save()
        category_expression = expression

        expression = Expression()
        expression.name = 'Amount'
        expression.model = model
        expression.ttype = 'numeric'
        expression.decimal_digits = 2
        expression.expression = 'o.amount'
        expression.save()
        amount_expression = expression

        expression = Expression()
        expression.name = 'Year'
        expression.model = model
        expression.ttype = 'char'
        expression.expression = 'y(o.date)'
        expression.save()
        year_expression = expression

        expression = Expression()
        expression.name = 'Month'
        expression.model = model
        expression.ttype = 'char'
        expression.expression = 'm(o.date)'
        expression.save()
        month_expression = expression

        expression = Expression()
        expression.name = 'Day'
        expression.model = model
        expression.ttype = 'char'
        expression.expression = 'd(o.date)'
        expression.save()
        day_expression = expression

        expression = Expression()
        expression.name = 'Shifted Date'
        expression.model = model
        expression.ttype = 'char'
        expression.expression = 'ymd(o.date - relativedelta(days=1))'
        expression.save()
        shifted_date_expression = expression

        expression = Expression()
        expression.name = 'Category Upper'
        expression.model = model
        expression.ttype = 'char'
        expression.expression = 'getattr(o, "category").upper()'
        expression.save()
        category_upper_expression = expression

        expression = Expression()
        expression.name = 'Has Amount'
        expression.model = model
        expression.ttype = 'char'
        expression.expression = (
            '"has_amount" if hasattr(o, "amount") else "missing_amount"')
        expression.save()
        has_amount_expression = expression

        expression = Expression()
        expression.name = 'Amount Type'
        expression.model = model
        expression.ttype = 'char'
        expression.expression = (
            '"decimal" if isinstance(o.amount, Decimal) else "other"')
        expression.save()
        amount_type_expression = expression

        expression = Expression()
        expression.name = 'Odd Flag'
        expression.model = model
        expression.ttype = 'char'
        expression.expression = 'o.category == "odd" and "ODD" or "NOT_ODD"'
        expression.save()
        odd_flag_expression = expression

        expression = Expression()
        expression.name = 'Size'
        expression.model = model
        expression.ttype = 'char'
        expression.expression = (
            '"big" if o.amount > Decimal("20") else "small"')
        expression.save()
        size_expression = expression

        expression = Expression()
        expression.name = 'Date Parts'
        expression.model = model
        expression.ttype = 'char'
        expression.expression = (
            '",".join([str(x) for x in [y(o.date), m(o.date), d(o.date)]])')
        expression.save()
        date_parts_expression = expression

        # Create and compute a model-based BABI table
        Table = Model.get('babi.table')
        Field = Model.get('babi.field')
        table = Table()
        table.name = 'Model Table'
        table.type = 'model'
        table.model = model

        field = Field()
        field.expression = id_expression
        field.name = id_expression.name
        field.internal_name = 'id'
        table.fields_.append(field)

        field = Field()
        field.expression = category_expression
        field.name = category_expression.name
        field.internal_name = 'category'
        table.fields_.append(field)

        field = Field()
        field.expression = amount_expression
        field.name = amount_expression.name
        field.internal_name = 'amount'
        table.fields_.append(field)

        field = Field()
        field.expression = year_expression
        field.name = year_expression.name
        field.internal_name = 'year'
        table.fields_.append(field)

        field = Field()
        field.expression = month_expression
        field.name = month_expression.name
        field.internal_name = 'month'
        table.fields_.append(field)

        field = Field()
        field.expression = day_expression
        field.name = day_expression.name
        field.internal_name = 'day'
        table.fields_.append(field)

        field = Field()
        field.expression = shifted_date_expression
        field.name = shifted_date_expression.name
        field.internal_name = 'shifted_date'
        table.fields_.append(field)

        field = Field()
        field.expression = category_upper_expression
        field.name = category_upper_expression.name
        field.internal_name = 'category_upper'
        table.fields_.append(field)

        field = Field()
        field.expression = has_amount_expression
        field.name = has_amount_expression.name
        field.internal_name = 'has_amount'
        table.fields_.append(field)

        field = Field()
        field.expression = amount_type_expression
        field.name = amount_type_expression.name
        field.internal_name = 'amount_type'
        table.fields_.append(field)

        field = Field()
        field.expression = odd_flag_expression
        field.name = odd_flag_expression.name
        field.internal_name = 'odd_flag'
        table.fields_.append(field)

        field = Field()
        field.expression = size_expression
        field.name = size_expression.name
        field.internal_name = 'size'
        table.fields_.append(field)

        field = Field()
        field.expression = date_parts_expression
        field.name = date_parts_expression.name
        field.internal_name = 'date_parts'
        table.fields_.append(field)

        table.save()
        table.click('compute')
        table.reload()

        self.assertEqual(len(table.fields_), 13)
        self.assertIsNotNone(table.calculation_date)
        self.assertEqual(
            [field.internal_name for field in table.fields_],
            ['id', 'category', 'amount', 'year', 'month', 'day',
                'shifted_date', 'category_upper', 'has_amount',
                'amount_type', 'odd_flag', 'size', 'date_parts'])
        self.assertIn('>odd</td>', str(table.preview))
        self.assertIn('>even</td>', str(table.preview))
        self.assertIn('>2026</td>', str(table.preview))
        self.assertIn('>01</td>', str(table.preview))
        self.assertIn('>15</td>', str(table.preview))
        self.assertIn('>16</td>', str(table.preview))
        self.assertIn('>2026-01-14</td>', str(table.preview))
        self.assertIn('>2026-01-15</td>', str(table.preview))
        self.assertIn('>ODD</td>', str(table.preview))
        self.assertIn('>EVEN</td>', str(table.preview))
        self.assertIn('>has_amount</td>', str(table.preview))
        self.assertIn('>decimal</td>', str(table.preview))
        self.assertIn('>NOT_ODD</td>', str(table.preview))
        self.assertIn('>big</td>', str(table.preview))
        self.assertIn('>small</td>', str(table.preview))
        self.assertIn('>2026,01,15</td>', str(table.preview))
        self.assertIn('>2026,01,16</td>', str(table.preview))
