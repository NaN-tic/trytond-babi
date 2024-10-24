import csv
import time
import traceback
import datetime as mdatetime
from datetime import datetime
import logging
import sql
import unidecode
import json
import tempfile
from openpyxl import Workbook
from openpyxl.writer.excel import save_workbook
from simpleeval import EvalWithCompoundTypes
from trytond import backend
from trytond.bus import notify
from trytond.transaction import Transaction
from trytond.pool import Pool
from trytond.model import (ModelView, ModelSQL, fields, Unique,
    DeactivableMixin, sequence_ordered, Workflow)
from trytond.exceptions import UserError
from trytond.i18n import gettext
from trytond.pyson import Bool, Eval, PYSONDecoder
from trytond.config import config
from trytond.modules.company.model import (
    employee_field, reset_employee, set_employee)
from trytond.report import Report
from .babi import TimeoutChecker, TimeoutException, FIELD_TYPES, QUEUE_NAME
from .babi_eval import babi_eval

VALID_FIRST_SYMBOLS = 'abcdefghijklmnopqrstuvwxyz'
VALID_NEXT_SYMBOLS = '_0123456789'
VALID_SYMBOLS = VALID_FIRST_SYMBOLS + VALID_NEXT_SYMBOLS


logger = logging.getLogger(__name__)

def save_virtual_workbook(workbook):
    with tempfile.NamedTemporaryFile() as tmp:
        save_workbook(workbook, tmp.name)
        with open(tmp.name, 'rb') as f:
            return f.read()

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

def generate_html_table(records):
    table = "<table>"
    tag = 'th'
    for row in records:
        table += "<tr>"
        for cell in row:
            align = 'right'
            if cell is None:
                cell = '<i>NULL</i>'
            elif isinstance(cell, datetime):
                cell = cell.strftime('%Y-%m-%d %H:%M:%S')
            elif isinstance(cell, mdatetime.date):
                cell = cell.strftime('%Y-%m-%d')
            elif isinstance(cell, mdatetime.time):
                cell = cell.strftime('%H:%M:%S')
            elif isinstance(cell, (float, int)):
                cell = str(cell)
            else:
                cell = str(cell)
                align = 'left'
            table += f"<{tag} align='{align}'>{cell}</{tag}>"
        tag = 'td'
        table += "</tr>"
    table += "</table>"
    return table


class TableUser(ModelSQL):
    'BABI Table User'
    __name__ = 'babi.table-res.user'
    babi_table = fields.Many2One('babi.table', 'Table', required=True,
        ondelete='CASCADE')
    user = fields.Many2One('res.user', 'User', required=True,
        ondelete='CASCADE')


class TableGroup(ModelSQL):
    'BABI Table Group'
    __name__ = 'babi.table-res.group'
    babi_table = fields.Many2One('babi.table', 'Table', required=True,
        ondelete='CASCADE')
    user = fields.Many2One('res.group', 'Group', required=True,
        ondelete='CASCADE')


class Table(DeactivableMixin, ModelSQL, ModelView):
    'BABI Table'
    __name__ = 'babi.table'
    name = fields.Char('Name', required=True)
    type = fields.Selection([
            (None, ''),
            ('model', 'Model'),
            ('table', 'Table'),
            ('view', 'View'),
            ], 'Type', required=True)
    internal_name = fields.Char('Internal Name', required=True)
    model = fields.Many2One('ir.model', 'Model', states={
            'invisible': Eval('type') != 'model',
            'required': Eval('type') == 'model',
            }, domain=[('babi_enabled', '=', True)])
    filter = fields.Many2One('babi.filter', 'Filter', domain=[
            ('model', '=', Eval('model')),
            ], states={
            'invisible': Eval('type') != 'model',
            })
    fields_ = fields.One2Many('babi.field', 'table', 'Fields')
    query = fields.Text('Query', states={
            'invisible': ~Eval('type').in_(['table', 'view']),
            }, depends=['type'])
    timeout = fields.Integer('Timeout', required=True, states={
            'invisible': ~Eval('type').in_(['model', 'table']),
            }, help='If table '
        'calculation should take more than the specified timeout (in seconds) '
        'the process will be stopped automatically.')
    preview_limit = fields.Integer('Preview Limit', required=True)
    preview = fields.Function(fields.Binary('Preview',
        filename='preview_filename'), 'get_preview')
    preview_filename = fields.Function(fields.Char('Preview Filename'),
        'get_preview_filename')
    babi_raise_user_error = fields.Boolean('Raise User Error',
        help='Will raise a UserError in case of an error in the table.')
    compute_error = fields.Text('Compute Error', states={
            'invisible': ~Bool(Eval('compute_error')),
            }, readonly=True)
    compute_warning_error = fields.Text('Compute Warning Error', states={
            'invisible': ~Bool(Eval('compute_warning_error')),
            }, readonly=True,)
    crons = fields.One2Many('ir.cron', 'babi_table', 'Schedulers', context={
            'babi_table': Eval('id', -1),
            }, depends=['id'])
    requires = fields.One2Many('babi.table.dependency', 'required_by',
        'Requires', readonly=True)
    required_by = fields.One2Many('babi.table.dependency', 'table',
        'Required By', readonly=True)
    ai_request = fields.Text('AI Request', states={
            'invisible': Eval('type') == 'model',
            })
    ai_response = fields.Text('AI Response', readonly=True, states={
            'invisible': Eval('type') == 'model',
            })
    warn = fields.Selection([
            (None, 'Never'),
            ('records', 'Records Found'),
            ('no-records', 'No Records Found'),
            ('always', 'Always'),
            ], 'Warn')
    email_template = fields.Many2One('electronic.mail.template',
        'Email Template', domain=[('model.model', '=', 'babi.warning')],
        states={
            'invisible': ~Bool(Eval('warn')),
            })
    warning_description = fields.Text('Description', states={
            'invisible': ~Bool(Eval('warn')),
            })
    calculation_date = fields.DateTime('Date of calculation', readonly=True,
        states={
            'invisible': ~Bool(Eval('warn')),
            })
    calculation_time = fields.Float('Time taken to calculate (in seconds)',
        digits=(16, 6), readonly=True, states={
            'invisible': ~Bool(Eval('warn')),
            })
    last_warning_execution = fields.DateTime('Last Warning Execution',
        readonly=True)
    related_field = fields.Many2One('babi.field', 'Related Field', domain=[
            ('table.id', '=', Eval('id', -1)),
            ], states={
            'invisible': ~Bool(Eval('warn'))
            },ondelete='SET NULL')
    related_model = fields.Many2One('ir.model', 'Related Model', states={
            'required': Bool(Eval('related_field')),
            'invisible': ~Bool(Eval('warn'))
            })
    group = fields.Many2One('res.group', 'Group', ondelete='SET NULL', states={
            'invisible': ~Bool(Eval('warn'))
            })
    user = fields.Many2One('res.user', 'User', ondelete='SET NULL', states={
            'invisible': Bool(Eval('user_field')) | ~Bool(Eval('warn')),
            })
    user_field = fields.Many2One('babi.field', 'User Field', domain=[
            ('table.id', '=', Eval('id', -1)),
            ], ondelete='SET NULL', states={
            'invisible': Bool(Eval('user')) | ~Bool(Eval('warn')),
            })
    employee = fields.Many2One('company.employee', 'Employee',
        ondelete='SET NULL', states={
            'invisible': Bool(Eval('employee_field')) | ~Bool(Eval('warn')),
            })
    employee_field = fields.Many2One('babi.field', 'Employee Field', domain=[
            ('table.id', '=', Eval('id', -1)),
            ], ondelete='SET NULL', states={
            'invisible': Bool(Eval('employee')) | ~Bool(Eval('warn')),
            })
    company = fields.Many2One('company.company', 'Company', ondelete='SET NULL',
        states={
        'invisible': Bool(Eval('company_field')) | ~Bool(Eval('warn')),
        })
    company_field = fields.Many2One('babi.field', 'Company Field', domain=[
            ('table.id', '=', Eval('id', -1)),
            ], ondelete='SET NULL', states={
            'invisible': Bool(Eval('company')) | ~Bool(Eval('warn')),
            })
    party = fields.Many2One('party.party', 'Party', ondelete='SET NULL',
        states={
        'invisible': Bool(Eval('party_field')) | ~Bool(Eval('warn')),
        },
        context={
            'company': Eval('company', -1),
            },
        depends={'company'})
    party_field = fields.Many2One('babi.field', 'Party Field', domain=[
            ('table.id', '=', Eval('id', -1)),
            ], ondelete='SET NULL', states={
            'invisible': Bool(Eval('party')) | ~Bool(Eval('warn')),
            })
    pivot_table = fields.Function(fields.Char('Pivot Table'), 'get_pivot_table')
    access_users = fields.Many2Many('babi.table-res.user', 'babi_table', 'user',
        'Access Users')
    access_groups = fields.Many2Many('babi.table-res.group', 'babi_table', 'user',
        'Access Groups')

    @staticmethod
    def default_timeout():
        Config = Pool().get('babi.configuration')
        config = Config(1)
        return config.default_timeout or 30

    @staticmethod
    def default_preview_limit():
        return 10

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls._order.insert(0, ('name', 'ASC'))
        cls._buttons.update({
                'ai': {},
                'compute': {},
                'compute_warning': {
                    'invisible': ~Bool(Eval('warn')),
                    },
                })

    @classmethod
    def __register__(cls, module_name):
        super().__register__(module_name)
        cursor = Transaction().connection.cursor()
        sql_table = cls.__table__()

        # Migration to 7.2: rename query to view
        cursor.execute(*sql_table.update([sql_table.type], ['view'],
                where=sql_table.type == 'query'))

    @classmethod
    def view_attributes(cls):
        return super().view_attributes() + [
            ('//page[@id="warning"]', 'states', {
                    'invisible': ~Bool(Eval('warn')),
                    })
            ]

    @classmethod
    def create(cls, vlist):
        tables = super().create(vlist)
        for table in tables:
            table.update_table_dependencies()
        return tables

    @classmethod
    def write(cls, *args):
        args = [x.copy() for x in args]
        actions = iter(args)
        for tables, values in zip(actions, actions):
            if 'ai_request' in values and not 'ai_response' in values:
                values['ai_response'] = None
            if 'internal_name' not in values:
                continue
            for table in tables:
                table._drop()

        super().write(*args)

        actions = iter(args)
        for tables, values in zip(actions, actions):
            for table in tables:
                table.update_table_dependencies()
                if 'internal_name' in values:
                    table._drop()

    @classmethod
    def delete(cls, tables):
        for table in tables:
            table._drop()
        super().delete(tables)

    @fields.depends('user_field')
    def on_change_user(self):
        if self.user_field:
            self.user = None

    @fields.depends('user')
    def on_change_user_field(self):
        if self.user:
            self.user_field = None

    @fields.depends('employee_field')
    def on_change_employee(self):
        if self.employee_field:
            self.employee = None

    @fields.depends('employee')
    def on_change_employee_field(self):
        if self.employee:
            self.employee_field = None

    @fields.depends('company_field')
    def on_change_company(self):
        if self.company_field:
            self.company = None

    @fields.depends('company')
    def on_change_company_field(self):
        if self.company:
            self.company_field = None

    def update_table_dependencies(self):
        pool = Pool()
        Dependency = pool.get('babi.table.dependency')

        Dependency.delete(self.requires)
        Dependency.delete(self.required_by)

        tables = {x.table_name: x for x in self.search([])}
        to_save = []

        required_tables = self.get_required_table_names()
        for name in required_tables:
            dependency = Dependency()
            dependency.required_by = self
            dependency.name = name
            dependency.table = tables.get(name)
            to_save.append(dependency)

        requiredby_tables = self.get_required_by_table_names() - required_tables
        for name in requiredby_tables:
            dependency = Dependency()
            dependency.required_by = tables.get(name)
            dependency.name = self.table_name
            dependency.table = self
            to_save.append(dependency)

        Dependency.save(to_save)

    def get_required_table_names(self):
        if self.type and self.type == 'model':
            return set()
        query = self.query or ''
        tables = {x for x in query.split() if x.startswith('__')}
        return tables

    def get_required_by_table_names(self):
        tables = self.search([
                ('type', 'in', ['table', 'view']),
                ('query', 'ilike', '%' + self.table_name + '%'),
                ])
        res = set()
        for table in tables:
            if self.table_name in table.get_required_table_names():
                res.add(table.table_name)
        return res

    def get_records(self):
        table = []
        table.append([x.internal_name for x in self.fields_])
        try:
            table += self.execute_query(limit=self.preview_limit)
        except Exception as e:
            raise UserError(gettext('babi.msg_error_obtaining_records',
                    table=self.rec_name, error=str(e)))
        return table

    def get_preview(self, name):
        start = time.time()
        content = None
        try:
            records = self.execute_query(limit=self.preview_limit)
        except Exception as e:
            content = str(e).encode('utf-8')

        elapsed = time.time() - start

        if not content:
            table = []
            row = [x.internal_name for x in self.fields_]
            table.append(row)
            for record in records:
                table.append(record)
            content = '%(table)s<br/>%(elapsed).2fms' % {
                'table': generate_html_table(table),
                'elapsed': elapsed * 1000,
                }

        preview = '''<!DOCTYPE html>
             <html>
             <head>
             <style>
             table, th, td {
                border: 1px solid black;
                border-collapse: collapse;
                padding: 5px;
             }
             * {
                font-family: monospace;
             }
             </style>
             </head>
             <body>%s</body></html>
        ''' % content
        return preview.encode()

    def get_preview_filename(self, name):
        return self.internal_name + '.html'

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

    def get_pivot_table(self, name):
        if config.get("web", "cors"):
            return f'{(config.get("web", "cors"))}/{Transaction().database.name}/babi/pivot/__{self.internal_name}/null'
        return f'http://{(config.get("web", "listen"))}/{Transaction().database.name}/babi/pivot/__{self.internal_name}/null'

    @property
    def ai_sql_tables(self):
        return {'account_invoice', 'account_invoice_line'}

    @classmethod
    @ModelView.button
    def csv(cls, tables):
        for table in tables:
            try:
                records = table.execute_query()
            except Exception as e:
                raise UserError(gettext('babi.msg_table_csv_error',
                        table=table.rec_name, error=str(e)))
            filename = table.internal_name + '.csv'
            with open(filename, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerows(records)


    @classmethod
    @ModelView.button
    def ai(cls, tables):
        cursor = Transaction().connection.cursor()

        from openai import OpenAI
        client = OpenAI(
            organization=config.get('openai', 'organization'),
            api_key=config.get('openai', 'api_key')
            )
        for table in tables:
            sqltables = dict.fromkeys(table.ai_sql_tables)

            t = sql.Table('columns', schema='information_schema')
            query = t.select(t.table_name, t.column_name,
                t.data_type)
            query.where = (t.table_schema == 'public') & \
                (t.table_name.in_(tuple(sqltables.keys())))
            cursor.execute(*query)
            for table_name, column_name, data_type in cursor.fetchall():
                sqltables[table_name] = sqltables[table_name] or {}
                sqltables[table_name][column_name] = data_type

            request = '''Given the following tables:

            %s

            Write an SQL query that returns the following information:

            %s

            Query:''' % (json.dumps(sqltables), table.ai_request)
            messages = [{
                'role': 'system',
                'content': 'Always return an SQL query that is suitable for PostgreSQL',
                }, {
                'role': 'user',
                'content': request,
                }]
            response = client.chat.completions.create(model="gpt-3.5-turbo",
            messages=messages)
            if response.choices:
                query = response.choices[0].message.content
                if not table.query:
                    table.query = query
                table.ai_response = query
                table.save()

    @classmethod
    @ModelView.button
    def compute(cls, tables):
        with Transaction().set_context(queue_name=QUEUE_NAME):
            for table in tables:
                if not table.active:
                    continue
                cls.__queue__._compute(table)

    @classmethod
    @ModelView.button
    def compute_warning(cls, tables):
        with Transaction().set_context(queue_name=QUEUE_NAME):
            for table in tables:
                if not table.active:
                    continue
                cls.__queue__.compute_warnings(table)

    @property
    def table_name(self):
        # Add a suffix to the table name to prevent removing production tables
        return '__' + self.internal_name

    def get_query(self, fields=None, where=None, groupby=None, limit=None):
        query = 'SELECT '
        if fields:
            query += ', '.join(fields) + ' '
        else:
            query += '* '

        if self.type == 'view':
            query += 'FROM (%s) AS a ' % self._stripped_query
        else:
            query += 'FROM %s ' % self.table_name
        if where:
            where = where.format(**Transaction().context)
            query += 'WHERE %s ' % where

        if groupby:
            query += 'GROUP BY %s ' % ', '.join(groupby) + ' '

        if fields:
            query += 'ORDER BY %s' % ', '.join(fields)

        if limit:
            query += ' LIMIT %d' % limit
        return query

    def execute_query(self, fields=None, where=None, groupby=None, timeout=None,
            limit=None):
        if timeout is None:
            timeout = 10
        if (self.type != 'view'
                and not backend.TableHandler.table_exist(self.table_name)):
            return []
        with Transaction().new_transaction() as transaction:
            cursor = transaction.connection.cursor()
            cursor.execute('SET statement_timeout TO %s;' % int(timeout * 1000))
            query = self.get_query(fields, where=where, groupby=groupby,
                limit=limit)
            cursor.execute(query)
            records = cursor.fetchall()
            cursor.execute('SET statement_timeout TO 0;')
        return records

    def timeout_exception(self):
        raise TimeoutException

    def _compute(self, processed=None, compute_warnings=False):
        start_time = time.time()
        if processed is None:
            processed = []
        if self in processed:
            seq = ' > '.join([x.rec_name for x in processed] + [self.rec_name])
            raise UserError(gettext('babi.msg_circular_dependency',
                    sequence=seq))
        try:
            if self.type == 'model':
                if not self.fields_:
                    raise UserError(gettext('babi.msg_table_no_fields',
                            table=self.name))

                if self.filter and self.filter.parameters:
                    raise UserError(gettext('babi.msg_filter_with_parameters',
                            table=self.rec_name))

            if self.type == 'model':
                self._compute_model()
            elif self.type == 'table':
                self._compute_table()
            elif self.type == 'view':
                self._compute_view()

            for dependency in self.required_by:
                dependency.required_by._compute(processed + [self])
        except Exception as e:
            # In case there is a create view error or SQL typo,
            # we do rollback to obtain a value from the gettext()
            Transaction().connection.rollback()
            notify(gettext('babi.msg_table_failed', table=self.rec_name))
            self.compute_error = f'{e}\n{traceback.format_exc()}'
            self.save()
            return

        self.compute_error = None
        end_time = time.time()
        self.save()
        notify(gettext('babi.msg_table_successful', table=self.rec_name))
        self.calculation_date = datetime.now()
        self.calculation_time = round(end_time - start_time,
            self.__class__.calculation_time.digits[1])
        self.save()
        if compute_warnings:
            self.__class__.__queue__.compute_warnings(self)

    def compute_warnings(self):
        self.compute_warning_error = None
        self.save()
        query = self.get_query()
        if query:
            user_id = None
            if self.user_field:
                user_id = self.user_field.internal_name
            elif self.user:
                user_id = self.user.id
            else:
                user_id = 'NULL'

            employee_id = None
            if self.employee_field:
                employee_id = self.employee_field.internal_name
            elif self.employee:
                employee_id = self.employee.id
            else:
                employee_id = 'NULL'

            company_id = None
            if self.company_field:
                company_id = self.company_field.internal_name
            elif self.company:
                company_id = self.company.id
            else:
                company_id = 'NULL'

            if self.party_field:
                party_id = self.party_field.internal_name
            elif self.party:
                party_id = self.party.id
            else:
                party_id = 'NULL'

            query_full = 'SELECT '
            query_full += '   count(*), '
            query_full += f'  {user_id} AS user_id, '
            query_full += f'  {employee_id} as employee_id, '
            query_full += f'  {party_id} as party_id, '
            query_full += f'  {company_id} as company_id '
            query_full += 'FROM (%s) AS compute_warnings_subquery ' % query

            group_by = [user_id, employee_id, company_id, party_id]
            group_by = [x for x in group_by
                if isinstance(x, str) and x != 'NULL']
            if group_by:
                query_full += 'GROUP BY ' + ', '.join(group_by)

        to_create = []
        self.last_warning_execution = datetime.now()
        cursor = Transaction().connection.cursor()
        cursor.execute(query_full)
        query_last = cursor.fetchall()
        for x in query_last:
            count = x[0]
            if (self.warn == 'always'
                    or (self.warn == 'records' and count)
                    or (self.warn == 'no-records' and not count)):
                to_create.append({
                        'timestamp': self.last_warning_execution,
                        'table': self.id,
                        'count': count,
                        'user': x[1],
                        'employee': x[2],
                        'party': x[3],
                        'company': x[4],
                        'group': self.group,
                        })
        if to_create:
            try:
                warnings = Warning.create(to_create)
                for warning in warnings:
                    warning.send()
            except Exception as e:
                Transaction().connection.rollback()
                self.compute_warning_error = f'{e}\n{traceback.format_exc()}'
                self.save()

    def update_fields(self, field_names):
        pool = Pool()
        Field = pool.get('babi.field')

        # Update self.fields_
        to_save = []
        to_delete = []
        existing_fields = set([])
        for field in self.fields_:
            if field.internal_name not in field_names:
                to_delete.append(field)
                continue
            field.sequence = field_names.index(field.internal_name)
            existing_fields.add(field.internal_name)
            to_save.append(field)

        for field_name in (set(field_names) - existing_fields):
            field = Field()
            field.table = self
            field.name = field_name
            field.internal_name = field_name
            field.sequence = field_names.index(field.internal_name)
            to_save.append(field)

        Field.save(to_save)
        Field.delete(to_delete)

    @property
    def _stripped_query(self):
        if self.query:
            return self.query.strip().rstrip(';')
        else:
            return ''

    def _drop(self):
        # Given that the type may be changed from view to table and viceversa
        # we cannot rely on self.type to know if we have to execute DROP TABLE
        # or DROP VIEW.
        cursor = Transaction().connection.cursor()
        if backend.name != 'postgresql':
            cursor.execute('DROP TABLE IF EXISTS %s' % self.table_name)
            cursor.execute('DROP VIEW IF EXISTS %s' % self.table_name)
            return
        # In Postgres, trying to execute DROP VIEW on a TABLE will make
        # postgres complaint (even with the 'IF EXISTS' clause). And the same
        # will happen with DROP TABLE on a VIEW. So we must check if it exists
        # and its type.
        cursor.execute("SELECT table_type FROM information_schema.tables "
            "WHERE table_name=%s AND table_schema='public'", (self.table_name,))
        record = cursor.fetchone()
        if not record:
            return
        if record[0] == 'VIEW':
            cursor.execute('DROP VIEW IF EXISTS "%s" CASCADE' % self.table_name)
        else:
            cursor.execute('DROP TABLE IF EXISTS %s CASCADE' % self.table_name)

    def _compute_view(self):
        with Transaction().new_transaction() as transaction:
            cursor = transaction.connection.cursor()
            # We must use a subquery because the _stripped_query may contain a
            # LIMIT clause
            cursor.execute('SELECT * FROM (%s) AS subquery LIMIT 1' %
                self._stripped_query)

        field_names = [x[0] for x in cursor.description]
        self.update_fields(field_names)

        cursor = Transaction().connection.cursor()
        self._drop()
        cursor.execute('CREATE VIEW "%s" AS %s' % (self.table_name, self._stripped_query))

    def _compute_table(self):
        with Transaction().new_transaction() as transaction:
            self._drop()
            cursor = transaction.connection.cursor()
            cursor.execute('CREATE TABLE "%s" AS %s' % (self.table_name,
                    self._stripped_query))
            cursor.execute('SELECT * FROM "%s" LIMIT 1' % self.table_name)

        field_names = [x[0] for x in cursor.description]
        self.update_fields(field_names)

    def _compute_model(self):
        Model = Pool().get(self.model.model)

        with Transaction().new_transaction() as transaction:
            cursor = transaction.connection.cursor()
            self._drop()
            fields = []
            for field in self.fields_:
                fields.append('"%s" %s' % (field.internal_name, field.sql_type()))
            cursor.execute('CREATE TABLE IF NOT EXISTS "%s" (%s);' % (
                    self.table_name, ', '.join(fields)))

            checker = TimeoutChecker(self.timeout, self.timeout_exception)
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

            table = sql.Table(self.table_name)
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

    def check_access(self, user=None):
        pool = Pool()
        User = pool.get('res.user')

        if not user:
            user = User(Transaction().user)

        access = True
        if not user:
            access = False
        if access and user and self.access_users:
            if user not in self.access_users:
                access = False
        if access and user and self.access_groups:
            access = False
            for group in user.groups:
                if group in self.access_groups:
                    access = True
                    break

        return access


class Field(sequence_ordered(), ModelSQL, ModelView):
    'BABI Field'
    __name__ = 'babi.field'
    table = fields.Many2One('babi.table', 'Table', required=True,
        ondelete='CASCADE')
    name = fields.Char('Name', required=True)
    internal_name = fields.Char('Internal Name', required=True)
    expression = fields.Many2One('babi.expression', 'Expression', states={
            'invisible': Eval('table_type') != 'model',
            'required': Eval('table_type') == 'model'
            }, domain=[
            ('model', '=', Eval('model')),
            ])
    model = fields.Function(fields.Many2One('ir.model', 'Model'),
        'on_change_with_model')
    type = fields.Function(fields.Selection(FIELD_TYPES, 'Type'),
        'on_change_with_type')
    table_type = fields.Function(fields.Selection([
            ('model', 'Model'),
            ('table', 'Table'),
            ('view', 'View'),
            ], 'Table Type'), 'on_change_with_table_type')

    @fields.depends('expression')
    def on_change_with_type(self, name=None):
        if self.expression:
            return self.expression.ttype

    @fields.depends('table', '_parent_table.type')
    def on_change_with_table_type(self, name=None):
        if self.table:
            return self.table.type

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
    def validate(cls, babi_fields):
        super().validate(babi_fields)
        for babi_field in babi_fields:
            babi_field.check_internal_name()

    def sql_type(self):
        mapping = {
            'char': 'VARCHAR',
            'integer': 'INTEGER',
            'float': 'FLOAT',
            'numeric': 'NUMERIC',
            'boolean': 'BOOLEAN',
            'many2one': 'INTEGER',
            'date': 'DATE',
            'datetime': 'DATETIME',
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

    @fields.depends('table', '_parent_table.model')
    def on_change_with_model(self, name=None):
        if self.table and self.table.model:
            return self.table.model.id


class TableDependency(ModelSQL, ModelView):
    'BABI Table Dependency'
    __name__ = 'babi.table.dependency'
    required_by = fields.Many2One('babi.table', 'Required By', required=True,
        ondelete='CASCADE')
    name = fields.Char('Name')
    table = fields.Many2One('babi.table', 'Requires', ondelete='SET NULL')

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls.__access__.add('table')


class Warning(Workflow, ModelSQL, ModelView):
    'BABI Warning'
    __name__ = 'babi.warning'

    timestamp = fields.DateTime('Timestamp', required=True, readonly=True)
    table = fields.Many2One('babi.table', 'Table', required=True, readonly=True,
        ondelete='CASCADE')
    has_related_records = fields.Function(fields.Boolean('Has Related Field'),
            'get_has_related_records')
    count = fields.Integer('Records found', readonly=True, required=True)
    state = fields.Selection([
            ('pending', 'Pending'),
            ('done', 'Done'),
            ('ignored', 'Ignored'),
            ], 'State', readonly=True)
    company = fields.Many2One('company.company', 'Company', readonly=True,
            ondelete='CASCADE')
    employee = fields.Many2One('company.employee', 'Employee', readonly=True)
    description = fields.Function(fields.Text('Description', readonly=True),
            'get_description',)
    user = fields.Many2One('res.user', 'User', readonly=True,
            ondelete='CASCADE')
    group = fields.Many2One('res.group', 'Group', ondelete='CASCADE',
            readonly=True)
    party = fields.Many2One('party.party', 'Party', ondelete='CASCADE',
            readonly=True, context={
                'company': Eval('company', -1),
            }, depends=['company'])

    users = fields.Function(fields.Many2Many('res.user', None, None, 'Users'),
        'get_users')
    emails = fields.Function(fields.Char('E-mails'), 'get_emails')
    done_by = employee_field("Done By", states=['pending', 'done', 'ignored'])
    ignored_by = employee_field("Ignored By",
        states=['pending', 'done', 'ignored'])

    def get_rec_name(self, name):
        return f'{self.count} - {self.table.name}'

    @classmethod
    def search_rec_name(cls, name, clause):
        return [('table.name',) + tuple(clause[1:])]

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls._transitions |= set((
                ('pending', 'done'),
                ('pending', 'ignored'),
                ('done', 'ignored'),
                ('ignored', 'pending'),
                ))
        cls._buttons.update({
                'pending': {
                    'invisible': ((Eval('state') == 'done')
                        | (Eval('state') == 'pending')),
                    'depends': ['state'],
                    'icon': 'tryton-back'
                    },
                'do': {
                    'invisible': Eval('state') != 'pending',
                    'depends': ['state'],
                    'icon': 'tryton-ok',
                    },
                'ignore': {
                    'invisible': Eval('state') == 'ignored',
                    'depends': ['state'],
                    'icon': 'tryton-cancel',
                    },
                'open': {
                    'invisible': ~Bool(Eval('has_related_records')),
                    'depends': ['has_related_records'],
                    'icon': 'tryton-add',
                    },
                })

    @staticmethod
    def default_state():
        return 'pending'

    def get_has_related_records(self, name):
        if not self.table.related_field:
            return False
        return bool(self.count)

    def get_users(self, name):
        pool = Pool()
        User = pool.get('res.user')

        if self.user:
            return [self.user]
        if self.employee:
            return User.search([
                    ('employee.id', '=', self.employee.id),
                    ])
        if self.group:
            return [x for x in self.group.users if x.active]
        if self.company:
            return User.search([
                    ('companies.id', '=', self.company.id),
                    ])
        return User.search([])

    def get_emails(self, name):
        User = Pool().get('res.user')

        emails = []
        if self.user:
            emails = [self.user.email]
        elif self.employee:
            emails = [self.employee.party.email]
        elif self.group:
            users = User.search([('groups.id', '=', self.group.id)])
            emails = [user.email for user in users]
        elif self.company:
            users = User.search([('companies.id', '=', self.company.id)])
            emails = [user.email for user in users]
        elif self.party:
            emails = [self.party.email]
        else:
            users = User.search([])
            emails = [user.email for user in users]
        return ', '.join(sorted(list({x for x in emails if x})))

    @classmethod
    @ModelView.button
    @Workflow.transition('pending')
    @reset_employee('done_by', 'ignored_by')
    def pending(cls, warnings):
        pass

    @classmethod
    @ModelView.button
    @Workflow.transition('done')
    @set_employee('done_by')
    def do(cls, warnings):
        pass

    @classmethod
    @ModelView.button
    @Workflow.transition('ignored')
    @set_employee('ignored_by')
    def ignore(cls, warnings):
        pass

    def get_description(self, name):
        return self.table.warning_description

    def get_ids(self):
        pool = Pool()
        Table = pool.get('babi.table')

        if not self.table.related_model:
            return []

        user_index = 1
        fields = [self.table.related_field.internal_name]
        if self.table.company_field:
            user_index += 1
            fields.append(self.table.company_field.internal_name)
        if self.table.user_field:
            fields.append(self.table.user_field.internal_name)
        if self.table.employee_field:
            fields.append(self.table.employee_field.internal_name)
        if self.table.party_field:
            fields.append(self.table.party_field.internal_name)
        records = Table.execute_query(self.table,
            fields=fields)

        if self.table.company_field and self.company:
            records = [x for x in records if x[1] == self.company.id]
        if self.table.user_field and self.user:
            records = [x for x in records if x[user_index] == self.user.id]
        if self.table.employee_field and self.employee:
            records = [x for x in records if x[user_index] == self.employee.id]
        if self.table.party_field and self.party:
            records = [x for x in records if x[user_index] == self.party.id]

        try:
            ids = []
            for record in records:
                value = record[0]
                if value is None:
                    continue
                # Allow using arrays (using array_agg) of ids or
                # just ids
                if isinstance(value, (tuple, list)):
                    ids += list([int(x) for x in value])
                else:
                    ids.append(int(value))
        except:
            raise UserError(gettext('babi.msg_not_converted',
                field=self.table.related_field.rec_name))
        return ids

    def get_records(self, ids=None):
        pool = Pool()
        Model = pool.get(self.table.related_model.model)
        if ids is None:
            ids = self.get_ids()
        return Model.search([('id', 'in', ids)])

    @classmethod
    @ModelView.button
    def open(cls, warnings):
        if len(set([x.table for x in warnings])) > 1:
            raise UserError(gettext('babi.msg_open_warning_single'))

        ids = []
        records = []
        for warning in warnings:
            wids = warning.get_ids()
            records += warning.get_records(wids)
            ids += wids

        if len(records) != len(ids):
            raise UserError(gettext('babi.msg_wrong_info',
                field=warning.table.related_field.rec_name,
                query_count=str(len(ids)),
                model_query_count=str(len(records))))

        return {
            'res_model': warning.table.related_model.model,
            'type': 'ir.action.act_window',
            'name': warning.table.related_model.name,
            'pyson_domain': f'[["id", "in", {ids}]]',
            'pyson_context': '{}',
            'pyson_order': '[]',
            'domains': [],
            }

    def send(self):
        if self.table.warn and self.table.email_template:
            self.table.email_template.render_and_send(
                self.table.email_template.id, [self])


class Excel(Report):
    'Table Excel Export'
    __name__ = 'babi.table.excel'

    @classmethod
    def execute(cls, ids, data):
        pool = Pool()
        Table = pool.get('babi.table')

        if not ids:
            return
        cls.check_access()

        tables = Table.browse(ids)
        wb = Workbook()
        wb.remove(wb.active)
        for table in tables:
            ws = wb.create_sheet(table.name)
            for record in table.get_records():
                ws.append(record)

        if len(tables) == 1:
            name = table.name
        else:
            name = 'tables'
        return ('xlsx', save_virtual_workbook(wb), False, name)
