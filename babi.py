# encoding: utf-8
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import datetime as mdatetime
import logging
import time
import unicodedata
import itertools
import html

from sql import Column
from datetime import datetime

from trytond.model import DeactivableMixin, ModelSQL, ModelView, fields
from trytond.model.fields import depends
from trytond.pyson import Bool, Eval, Not, PYSONDecoder
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction
from trytond.config import config as config_
from .babi_eval import babi_eval
from trytond.i18n import gettext
from trytond.exceptions import UserError, UserWarning

FIELD_TYPES = [
    (None, ''),
    ('char', 'Char'),
    ('integer', 'Integer'),
    ('float', 'Float'),
    ('numeric', 'Numeric'),
    ('boolean', 'Boolean'),
    ('many2one', 'Many To One'),
    ('date', 'Date'),
    ('datetime', 'Date & Time'),
    ]

AGGREGATE_TYPES = [
    ('avg', 'Average'),
    ('sum', 'Sum'),
    ('count', 'Count'),
    ('max', 'Max'),
    ('min', 'Min'),
    ]

# Red Circle Emoji
FIRE_HTML = '&#x1F525;'
FIRE = html.unescape(FIRE_HTML)
TICK_HTML = '&#x2705;'
TICK = html.unescape(TICK_HTML)

SRC_CHARS = """ .'"()/*-+?¿!&$[]{}@#`'^:;<>=~%,|\\"""
DST_CHARS = """__________________________________"""

RETENTION_DAYS = config_.getint('babi', 'retention_days', default=30)
MAX_BD_COLUMN = config_.getint('babi', 'max_db_column', default=60)
QUEUE_NAME = config_.get('babi', 'queue_name', default='default')

logger = logging.getLogger(__name__)


def unaccent(text):
    if not (isinstance(text, str)):
        return str(text)
    if isinstance(text, str) and bytes == str:
        text = str(text, 'utf-8')
    text = text.lower()
    for c in range(len(SRC_CHARS)):
        if c >= len(DST_CHARS):
            break
        text = text.replace(SRC_CHARS[c], DST_CHARS[c])
    text = unicodedata.normalize('NFKD', text)
    if bytes == str:
        text = text.encode('ASCII', 'ignore')
    return text


def _replace(x):
    return x.replace("'", '')


def sanitanize(x):
    if (isinstance(x, str) or isinstance(x, str)
            or isinstance(x, str)):
        x = x.replace('|', '-')
    if not isinstance(x, str) and isinstance(x, str):
        return str(x.decode('utf-8'))
    else:
        return str(x)



class DimensionError(UserError):
    pass

class MeasureError(UserError):
    pass

class TimeoutException(Exception):
    pass


class TimeoutChecker:
    def __init__(self, timeout, callback):
        self._timeout = timeout
        self._callback = callback
        self._start = datetime.now()

    @property
    def elapsed(self):
        return (datetime.now() - self._start).seconds

    def check(self):
        if self.elapsed > self._timeout:
            self._callback()


class Filter(DeactivableMixin, ModelSQL, ModelView):
    "Filter"
    __name__ = 'babi.filter'
    _history = True

    name = fields.Char('Name', required=True, translate=True)
    model = fields.Many2One('ir.model', 'Model', required=True,
        domain=[('babi_enabled', '=', True)])
    model_name = fields.Function(fields.Char('Model Name'),
        'on_change_with_model_name')
    view_search = fields.Many2One('ir.ui.view_search', 'Search',
        domain=[('model', '=', Eval('model_name'))])
    checked = fields.Boolean('Checked', readonly=True)
    domain = fields.Char('Domain')
    domain_error = fields.Char('Domain Error', readonly=True, states={
            'invisible': ~Bool(Eval('domain_error')),
            })
    python_expression = fields.Char('Python Expression',
        help='The python expression introduced will be evaluated. If the '
        'result is True the record will be included, it will be discarded '
        'otherwise.')
    expression_error = fields.Char('Expression Error', readonly=True, states={
            'invisible': ~Bool(Eval('expression_error')),
            })
    context = fields.Char('Context',
        help="A dict to eval context:\n"
        "- date: eval string to date. Format: %Y-%m-%d.\n"
        "  Example: {'stock_date_end': date('2023-12-01')}\n"
        "- datetime: eval string to date time. Format %Y-%m-%d %H:%M:%S.\n"
        "  Example: {'name': datetime('2023-12-01 10:00:00')}\n"
        "- today: eval current date\n"
        "  Example: {'stock_date_end': today}")
    parameters = fields.One2Many('babi.filter.parameter', 'filter',
        'Parameters')
    fields = fields.Function(fields.Many2Many('ir.model.field', None, None,
            'Model Fields'), 'on_change_with_fields')

    @depends('model')
    def on_change_with_model_name(self, name=None):
        return self.model.name if self.model else None

    @depends('model')
    def on_change_with_fields(self, name=None):
        if not self.model:
            return []
        return [x.id for x in self.model.fields]

    @depends('view_search')
    def on_change_with_domain(self):
        return self.view_search.domain if self.view_search else None

    @depends('model_name', 'domain')
    def on_change_with_view_search(self):
        ViewSearch = Pool().get('ir.ui.view_search')
        searches = ViewSearch.search([
                ('model', '=', self.model_name),
                ('domain', '=', self.domain),
                ])
        if not searches:
            return None
        return searches[0].id

    def get_rec_name(self, name):
        name = ''
        if self.checked:
            if self.domain_error or self.expression_error:
                name = FIRE
            else:
                name = TICK
        name += ' ' + self.name
        return name

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls._buttons.update({
                'check': {},
                })

    @classmethod
    def write(cls, *args):
        args = [x.copy() for x in args]
        actions = iter(args)
        for filters, values in zip(actions, actions):
            if 'python_expression' in values:
                values.setdefault('checked', False)
                values.setdefault('expression_error')
            if 'domain' in values:
                values.setdefault('checked', False)
                values.setdefault('domain_error')
        super().write(*args)

    @classmethod
    @ModelView.button
    def check(cls, filters=None):
        if not filters:
            filters = cls.search([])
        for filter in filters:
            filter.single_check()
        cls.save(filters)

    def single_check(self, cumulate=False):
        pool = Pool()

        self.checked = True
        self.domain_error = None
        self.expression_error = None

        if self.parameters:
            return True

        Model = pool.get(self.model.name)
        records = None

        if self.domain:
            domain = self.domain
            try:
                if '__' in domain:
                    domain = str(PYSONDecoder().decode(domain))
                domain = eval(domain, {
                        'datetime': mdatetime,
                        'false': False,
                        'true': True,
                        })
                records = Model.search(domain, limit=100,
                    order=[('id', 'DESC')])
            except Exception as e:
                self.domain_error = str(e)

        expression = self.python_expression
        if not expression:
            return

        records = Model.search([], limit=100, order=[('id', 'DESC')])
        records += Model.search([], limit=100, order=[('id', 'ASC')])
        start = time.time()
        for record in records:
            try:
                babi_eval(expression, record, convert_none=False)
            except Exception as e:
                self.expression_error = str(e)
            if time.time() - start > 5:
                logger.info('Waited too much for expression: %s',
                    expression)
                break


class FilterParameter(ModelSQL, ModelView):
    "Filter Parameter"
    __name__ = 'babi.filter.parameter'
    _history = True

    filter = fields.Many2One('babi.filter', 'Filter', required=True)
    name = fields.Char('Name', required=True, translate=True, help='Name used '
        'on the domain substitution')
    ttype = fields.Selection(FIELD_TYPES + [('many2many', 'Many To Many')],
        'Field Type', required=True)
    related_model = fields.Many2One('ir.model', 'Related Model', states={
            'required': Eval('ttype').in_(['many2one', 'many2many']),
            'readonly': Not(Eval('ttype').in_(['many2one', 'many2many'])),
            })

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls.__access__.add('filter')

    @classmethod
    def __register__(cls, module_name):
        super(FilterParameter, cls).__register__(module_name)
        cursor = Transaction().connection.cursor()
        sql_table = cls.__table__()

        # Migration from int to integer
        cursor.execute(*sql_table.update([Column(sql_table, 'ttype')],
                ['integer'], where=sql_table.ttype == 'int'))
        # Migration from bool to boolean
        cursor.execute(*sql_table.update([Column(sql_table, 'ttype')],
                ['boolean'], where=sql_table.ttype == 'bool'))

    def check_parameter_in_filter(self):
        Warning = Pool().get('res.user.warning')

        placeholder = '{%s}' % self.name
        if ((self.filter.domain and placeholder not in self.filter.domain)
                and (self.filter.python_expression
                    and placeholder not in self.filter.python_expression)):
            key = 'task_babi_check_parameter_in_filter.%d' % self.id
            if Warning.check(key):
                raise UserWarning('babi_check_parameter_in_filter.{}'.format(
                        self.name), gettext('babi.parameter_not_found',
                            parameter=self.rec_name,
                            filter=self.filter.rec_name))

            return False
        return True


class Expression(DeactivableMixin, ModelSQL, ModelView):
    "Expression"
    __name__ = 'babi.expression'
    _history = True

    name = fields.Char('Name', required=True, translate=True)
    model = fields.Many2One('ir.model', 'Model', required=True,
        domain=[('babi_enabled', '=', True)])
    checked = fields.Boolean('Checked', readonly=True)
    error = fields.Char('Error', readonly=True, states={
            'invisible': ~Bool(Eval('error')),
            })
    expression = fields.Char('Expression', required=True,
        help='Python expression that will return the value to be used.\n'
            'The expression can include the following variables:\n\n'
            '- "o": A reference to the current record being processed. For '
            ' example: "o.party.name"\n'
            '\nAnd the following functions apply to dates and timestamps:\n\n'
            '- "y()": Returns the year (as a string)\n'
            '- "m()": Returns the month (as a string)\n'
            '- "w()": Returns the week (as a string)\n'
            '- "d()": Returns the day (as a string)\n'
            '- "ym()": Returns the year-month (as a string)\n'
            '- "ymd()": Returns the year-month-day (as a string).\n')
    ttype = fields.Selection(FIELD_TYPES, 'Field Type', required=True)
    related_model = fields.Many2One('ir.model', 'Related Model', states={
            'required': Eval('ttype') == 'many2one',
            'readonly': Eval('ttype') != 'many2one',
            'invisible': Eval('ttype') != 'many2one',
            })
    decimal_digits = fields.Integer('Decimal Digits', states={
            'invisible': ~Eval('ttype').in_(['float', 'numeric']),
            'required': Eval('ttype').in_(['float', 'numeric']),
            })
    fields = fields.Function(fields.Many2Many('ir.model.field', None, None,
            'Model Fields'), 'on_change_with_fields')

    @classmethod
    def default_decimal_digits(cls):
        return 2

    def get_rec_name(self, name):
        name = ''
        if self.checked:
            if self.error:
                name = FIRE
            else:
                name = TICK
        name += ' ' + self.name
        return name

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls._buttons.update({
                'check': {},
                })

    @classmethod
    def __register__(cls, module_name):
        super(Expression, cls).__register__(module_name)
        cursor = Transaction().connection.cursor()
        sql_table = cls.__table__()

        # Migration from int to integer
        cursor.execute(*sql_table.update([Column(sql_table, 'ttype')],
                ['integer'], where=sql_table.ttype == 'int'))
        # Migration from bool to boolean
        cursor.execute(*sql_table.update([Column(sql_table, 'ttype')],
                ['boolean'], where=sql_table.ttype == 'bool'))

    @classmethod
    def write(cls, *args):
        args = [x.copy() for x in args]
        actions = iter(args)
        for filters, values in zip(actions, actions):
            if 'expression' in values:
                values.setdefault('checked', False)
                values.setdefault('error')
        super().write(*args)

    @depends('model')
    def on_change_with_fields(self, name=None):
        if not self.model:
            return []
        return [x.id for x in self.model.fields]

    @classmethod
    @ModelView.button
    def check(cls, expressions=None):
        pool = Pool()

        if not expressions:
            expressions = cls.search([], order=[('model', 'ASC')])
        else:
            # Ensure the right order
            expressions = cls.search([('id', 'in', expressions)],
                order=[('model', 'ASC')])

        count = 0
        for key, group in itertools.groupby(expressions, key=lambda x: x.model):
            Model = pool.get(key.model)

            group = list(group)
            count += len(list(group))
            records = Model.search([], limit=100, order=[('id', 'ASC')])
            records += Model.search([], limit=100, order=[('id', 'DESC')])
            for expression in group:
                expression.error = None
                expression.checked = False
                start = time.time()
                for record in records:
                    expression.checked = True
                    try:
                        babi_eval(expression.expression, record)
                    except Exception as e:
                        expression.error = str(e)
                        break

                    # We will not spend more than five seconds to test an
                    # expression. We do not want to wait unlimitedly for
                    # complex expressions
                    if time.time() - start > 5:
                        logger.info('Waited too much for expression: %s',
                            expression.expression)
                        break
                expression.save()


class Model(metaclass=PoolMeta):
    __name__ = 'ir.model'

    babi_enabled = fields.Boolean('BI Enabled', help='Check if you want '
        'this model to be available in Business Intelligence reports.')
