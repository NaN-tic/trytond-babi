import datetime as mdatetime
from datetime import datetime
import logging
import sql
import unidecode
from simpleeval import EvalWithCompoundTypes
from trytond.bus import notify
from trytond.transaction import Transaction
from trytond.pool import Pool
from trytond.model import ModelView, ModelSQL, fields, Unique, DeactivableMixin
from trytond.exceptions import UserError
from trytond.i18n import gettext
from trytond.pyson import Eval, PYSONDecoder
from .babi import TimeoutChecker, TimeoutException
from .babi_eval import babi_eval

VALID_FIRST_SYMBOLS = 'abcdefghijklmnopqrstuvwxyz'
VALID_NEXT_SYMBOLS = '_0123456789'
VALID_SYMBOLS = VALID_FIRST_SYMBOLS + VALID_NEXT_SYMBOLS

logger = logging.getLogger(__name__)

def convert_to_symbol(text):
    if not text:
        return 'x'
    text = unidecode.unidecode(text)
    text = text.lower()
    if text[0] not in VALID_FIRST_SYMBOLS:
        symbol = '_'
    else:
        symbol = ''
    for x in text:
        if not x in VALID_SYMBOLS:
            if symbol[-1] == '_':
                continue
            symbol += '_'
        else:
            symbol += x

    if len(symbol) > 1 and symbol[-1] == '_':
        symbol = symbol[:-1]
    return symbol


class Table(DeactivableMixin, ModelSQL, ModelView):
    'BABI Table'
    __name__ = 'babi.table'
    name = fields.Char('Name', required=True)
    internal_name = fields.Char('Internal Name', required=True)
    model = fields.Many2One('ir.model', 'Model', required=True,
        domain=[('babi_enabled', '=', True)])
    filter = fields.Many2One('babi.filter', 'Filter', domain=[
            ('model', '=', Eval('model')),
            ], depends=['model'])
    fields_ = fields.One2Many('babi.field', 'table', 'Fields')
    timeout = fields.Integer('Timeout', required=True, help='If table '
        'calculation should take more than the specified timeout (in seconds) '
        'the process will be stopped automatically.')
    babi_raise_user_error = fields.Boolean('Raise User Error',
        help='Will raise a UserError in case of an error in the table.')
    crons = fields.One2Many('ir.cron', 'babi_table', 'Schedulers', context={
            'babi_table': Eval('id'),
            }, depends=['id'])

    @staticmethod
    def default_timeout():
        Config = Pool().get('babi.configuration')
        config = Config(1)
        return config.default_timeout or 30

    @classmethod
    def __setup__(cls):
        super(Table, cls).__setup__()
        cls._buttons.update({
                'compute': {},
                })

    @classmethod
    def validate(cls, tables):
        super(Table, cls).validate(tables)
        for table in tables:
            table.check_internal_name()
            table.check_filter()

    def check_internal_name(self):
        if not self.internal_name[0] in VALID_FIRST_SYMBOLS:
            raise UserError(gettext(
                'babi.msg_invalid_internal_name_first_character',
                table=self.rec_name, internal_name=self.internal_name))
        for symbol in self.internal_name:
            if not symbol in VALID_SYMBOLS:
                raise UserError(gettext('babi.msg_invalid_internal_name',
                        table=self.rec_name, internal_name=self.internal_name))

    def check_filter(self):
        if self.filter and self.filter.parameters:
            raise UserError(gettext('babi.msg_filter_with_parameters',
                    table=self.rec_name))

    @fields.depends('name')
    def on_change_name(self):
        self.internal_name = convert_to_symbol(self.name)

    def get_python_filter(self):
        if self.filter and self.filter.python_expression:
            return self.filter.python_expression

    def get_domain_filter(self):
        domain = '[]'
        if self.filter and self.filter.domain:
            domain = self.filter.domain
            if '__' in domain:
                domain = str(PYSONDecoder().decode(domain))
        return eval(domain, {
                'datetime': mdatetime,
                'false': False,
                'true': True,
                })

    def get_context(self):
        if self.filter and self.filter.context:
            context = self.replace_parameters(self.filter.context)
            ev = EvalWithCompoundTypes(names={}, functions={
                'date': lambda x: datetime.strptime(x, '%Y-%m-%d').date(),
                'datetime': lambda x: datetime.strptime(x, '%Y-%m-%d'),
                })
            context = ev.eval(context)
            return context

    @classmethod
    @ModelView.button
    def compute(cls, tables):
        for table in tables:
            cls.__queue__._compute(table)

    def _compute(self):
        if not self.fields_:
            raise UserError(gettext('babi.msg_table_no_fields',
                    table=self.name))

        if self.filter and self.filter.parameters:
            raise UserError(gettext('babi.msg_filter_with_parameters',
                    table=self.rec_name))

        Model = Pool().get(self.model.model)

        cursor = Transaction().connection.cursor()

        # Create table
        cursor.execute('DROP TABLE IF EXISTS "%s"' % self.internal_name)
        fields = []
        for field in self.fields_:
            fields.append('"%s" %s' % (field.internal_name, field.sql_type()))
        cursor.execute('CREATE TABLE IF NOT EXISTS "%s" (%s);' % (
                self.internal_name, ', '.join(fields)))

        checker = TimeoutChecker(self.timeout, TimeoutException)
        domain = self.get_domain_filter()

        context = self.get_context()
        if not context:
            context = {}
        else:
            assert isinstance(context, dict)
        context['_datetime'] = None
        # This is needed when execute the wizard to calculate the report, to
        # ensure the company rule is used.
        context['_check_access'] = True

        python_filter = self.get_python_filter()

        table = sql.Table(self.internal_name)
        columns = [sql.Column(table, x.internal_name) for x in self.fields_]
        expressions = [x.expression.expression for x in self.fields_]
        index = 0
        count = 0
        offset = 2000

        with Transaction().set_context(**context):
            try:
                records = Model.search(domain, offset=index * offset,
                    limit=offset)
            except Exception as message:
                if self.babi_raise_user_error:
                    raise UserError(gettext(
                        'babi.create_data_exception',
                        error=repr(message)))
                raise

        while records:
            checker.check()
            logger.info('Calculated %s, %s records in %s seconds'
                % (self.model.model, count, checker.elapsed))

            to_insert = []
            for record in records:
                if python_filter:
                    if not babi_eval(python_filter, record, convert_none=None):
                        continue
                values = []
                for expression in expressions:
                    try:
                        values.append(babi_eval(expression, record,
                                convert_none=None))
                    except Exception as message:
                        notify(gettext('babi.msg_compute_table_exception',
                                table=self.name, field=field.name,
                                record=record.id, error=repr(message)),
                            priority=1)
                        if self.babi_raise_user_error:
                            raise UserError(gettext(
                                'babi.msg_compute_table_exception',
                                table=self.name,
                                field=field.name,
                                record=record.id,
                                error=repr(message)))
                        raise

                to_insert.append(values)

            cursor.execute(*table.insert(columns=columns, values=to_insert))

            index += 1
            count += len(records)
            with Transaction().set_context(**context):
                records = Model.search(domain, offset=index * offset,
                    limit=offset)

        logger.info('Calculated %s, %s records in %s seconds'
            % (self.model.model, count, checker.elapsed))


class Field(ModelSQL, ModelView):
    'BABI Field'
    __name__ = 'babi.field'
    table = fields.Many2One('babi.table', 'Table', required=True)
    name = fields.Char('Name', required=True)
    internal_name = fields.Char('Internal Name', required=True)
    expression = fields.Many2One('babi.expression', 'Expression', required=True,
        domain=[
            ('model', '=', Eval('model')),
            ], depends=['model'])
    model = fields.Function(fields.Many2One('ir.model', 'Model'),
        'on_change_with_model')

    @classmethod
    def __setup__(cls):
        super().__setup__()
        t = cls.__table__()
        cls._sql_constraints += [
            ('table_internal_name_uniq', Unique(t, t.table, t.internal_name),
                'Field must be unique per Table'),
            ]
        cls.__access__.add('table')

    @classmethod
    def validate(cls, tables):
        super().validate(tables)
        for table in tables:
            table.check_internal_name()

    def sql_type(self):
        mapping = {
            'char': 'VARCHAR',
            'integer': 'INTEGER',
            'float': 'FLOAT',
            'numeric': 'NUMERIC',
            'boolean': 'BOOLEAN',
            'many2one': 'INTEGER',
            }
        return mapping[self.expression.ttype]

    def check_internal_name(self):
        if not self.internal_name[0] in VALID_FIRST_SYMBOLS:
            raise UserError(gettext('babi.msg_invalid_field_internal_name',
                    field=self.name, internal_name=self.internal_name))
        for symbol in self.internal_name:
            if not symbol in VALID_SYMBOLS:
                raise UserError(gettext('babi.msg_invalid_field_internal_name',
                        field=self.name, internal_name=self.internal_name))

    @fields.depends('name')
    def on_change_name(self):
        self.internal_name = convert_to_symbol(self.name)

    @fields.depends('name', 'expression', methods=['on_change_name'])
    def on_change_expression(self):
        if self.expression:
            self.name = self.expression.name
            self.on_change_name()

    @fields.depends('table', '_parent_table.id')
    def on_change_with_model(self, name=None):
        if self.table:
            return self.table.model.id
