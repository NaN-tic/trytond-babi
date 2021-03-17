# encoding: utf-8
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import datetime as mdatetime
import pytz
import logging
import os
import sys
import time
import unicodedata
import json

from sql import Null, Column
from sql.operators import Or
from datetime import datetime, timedelta
from collections import defaultdict
from io import BytesIO

from trytond.wizard import (Wizard, StateView, StateAction, StateTransition,
    StateReport, Button)
from trytond.model import (ModelSQL, ModelView, fields, Unique, Check,
    sequence_ordered)
from trytond.model.fields import depends
from trytond.pyson import (Bool, Eval, Id, If, In, Not, Or as pysonOr,
    PYSONDecoder, PYSONEncoder)
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction
from trytond.tools import grouped_slice
from trytond.config import config as config_
from trytond import backend
from trytond.protocols.jsonrpc import JSONDecoder, JSONEncoder
from .babi_eval import babi_eval
from trytond.i18n import gettext
from trytond.exceptions import UserError, UserWarning
from trytond.model.modelstorage import AccessError
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.header import Header
from email.utils import getaddresses
from email import encoders


__all__ = ['Filter', 'Expression', 'Report', 'ReportGroup', 'Dimension',
    'DimensionColumn', 'Measure', 'InternalMeasure', 'Order', 'ActWindow',
    'Menu', 'Keyword', 'Model', 'OpenChartStart', 'OpenChart',
    'ReportExecution', 'OpenExecutionSelect', 'OpenExecution',
    'UpdateDataWizardStart', 'UpdateDataWizardUpdated',
    'FilterParameter', 'CleanExecutionsStart', 'CleanExecutions']


FIELD_TYPES = [
    ('char', 'Char'),
    ('integer', 'Integer'),
    ('float', 'Float'),
    ('numeric', 'Numeric'),
    ('boolean', 'Boolean'),
    ('many2one', 'Many To One'),
    ]

AGGREGATE_TYPES = [
    ('avg', 'Average'),
    ('sum', 'Sum'),
    ('count', 'Count'),
    ('max', 'Max'),
    ('min', 'Min'),
    ]

SRC_CHARS = """ .'"()/*-+?¿!&$[]{}@#`'^:;<>=~%,|\\"""
DST_CHARS = """__________________________________"""

BABI_CELERY = config_.getboolean('babi', 'celery', default=True)
BABI_RETENTION_DAYS = config_.getint('babi', 'retention_days', default=30)
BABI_CELERY_TASK = config_.get('babi', 'celery_task',
    default='trytond.modules.babi.tasks.calculate_execution')
BABI_MAX_BD_COLUMN = config_.getint('babi', 'max_db_column', default=60)

try:
    import celery
except ImportError:
    celery = None
except AttributeError:
    # If run from within frepple we will get
    # AttributeError: 'module' object has no attribute 'argv'
    pass
CELERY_CONFIG = config_.get('celery', 'config',
    default='trytond.modules.babi.celeryconfig')
CELERY_BROKER = 'amqp://%(user)s:%(password)s@%(host)s:%(port)s/%(vhost)s' % {
    'user': config_.get('celery', 'user', default='guest'),
    'password': config_.get('celery', 'password', default='guest'),
    'host': config_.get('celery', 'host', default='localhost'),
    'port': config_.getint('celery', 'port', default=5672),
    'vhost': config_.get('celery', 'vhost', default='/'),
    }

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


class DynamicModel(ModelSQL, ModelView):
    @classmethod
    def __setup__(cls):
        super(DynamicModel, cls).__setup__()
        pool = Pool()
        Execution = pool.get('babi.report.execution')
        executions = Execution.search([
                ('babi_model.model', '=', cls.__name__),
                ])
        if not executions or len(executions) > 1:
            return
        execution, = executions
        try:
            cls._order = execution.get_orders()
        except AssertionError:
            # An exception error is raisen on tests where Execution is not
            # properly loaded in the pool
            pass

    @classmethod
    def fields_view_get(cls, view_id=None, view_type='form'):
        pool = Pool()
        Execution = pool.get('babi.report.execution')
        Dimension = pool.get('babi.dimension')
        InternalMeasure = pool.get('babi.internal.measure')

        model_name = '_'.join(cls.__name__.split('_')[0:2])
        executions = Execution.search([
                ('babi_model.model', '=', cls.__name__),
                ], limit=1)
        if not executions:
            raise UserError(gettext('babi.report_not_exists',
                report=cls.__name__))

        context = Transaction().context
        execution, = executions
        with Transaction().set_context(_datetime=execution.create_date):
            report = execution.report
            view_type = context.get('view_type', view_type)

            result = {}
            result['type'] = view_type
            result['view_id'] = view_id
            result['field_childs'] = None
            fields = []
            if view_type == 'tree' or view_type == 'form':
                keyword = ''
                if view_type == 'tree':
                    keyword = 'keyword_open="1"'
                    fields.append('children')
                xml = '<%s string="%s" %s>\n' % (view_type, report.model.name,
                    keyword)
                for field in report.dimensions + execution.internal_measures:
                    # Avoid duplicated fields
                    if field.internal_name in fields:
                        continue
                    if view_type == 'form':
                        xml += '<label name="%s"/>\n' % (field.internal_name)
                    xml += '<field name="%s"/>\n' % (field.internal_name)
                    fields.append(field.internal_name)
                xml += '</%s>\n' % (view_type)
                result['arch'] = xml
                if view_type == 'tree' and context.get('babi_tree_view'):
                    result['field_childs'] = 'children'
            elif view_type == 'graph':
                # TODO: Remove it on 3.6 as client autogenerates it
                colors = ['#FF0000', '#0000FF', '#008000', '#FFFF00',
                    '#800080', '#FF00FF', '#FFA500', '#C0C0C0', '#000000']
                model_name = context.get('model_name')
                graph_type = context.get('graph_type')
                measure_ids = context.get('measures')
                legend = context.get('legend') and 1 or 0
                interpolation = context.get('interpolation', 'linear')
                dimension = Dimension(context.get('dimension'))

                x_xml = '<field name="%s"/>\n' % dimension.internal_name
                fields.append(dimension.internal_name)

                y_xml = ''
                for i, measure in enumerate(InternalMeasure.browse(
                            measure_ids)):
                    color = colors[i % len(colors)]
                    y_xml += ('<field name="%s" interpolation="%s" '
                        'color="%s"/> \n') % (measure.internal_name,
                            interpolation, color)
                    fields.append(measure.internal_name)

                xml = '''<?xml version="1.0"?>
                    <graph string="%(graph_name)s" type="%(graph_type)s"
                        legend="%(legend)s" background="#FFFFFF">
                        <x>
                            %(x_fields)s
                        </x>
                        <y>
                            %(y_fields)s
                        </y>
                    </graph>''' % {
                        'graph_type': graph_type,
                        'graph_name': model_name,
                        'legend': legend,
                        'x_fields': x_xml,
                        'y_fields': y_xml,
                        }
                result['arch'] = xml
            else:
                assert False
        result['fields'] = cls.fields_get(fields)
        return result

    def get_rec_name(self, name):
        result = []
        for field in self._babi_dimensions:
            value = getattr(self, field)
            if not value:
                result.append('-')
            elif isinstance(value, ModelSQL):
                result.append(value.rec_name)
            elif not isinstance(value, str):
                result.append(str(value))
            else:
                result.append(value)
        return ' / '.join(result)


def create_columns(name, ffields):
    "Create fields of new model"
    columns = {}
    for field in ffields:
        fname = field['name']
        field_name = field['internal_name']
        ttype = field['ttype']
        digits = field['decimal_digits']
        if digits is None:
            digits = 2
        if ttype == 'integer':
            columns[field_name] = fields.Integer(fname)
        elif ttype == 'float':
            columns[field_name] = fields.Float(fname, digits=(16, digits))
        elif ttype == 'numeric':
            columns[field_name] = fields.Numeric(fname, digits=(16, digits))
        elif ttype == 'char':
            columns[field_name] = fields.Char(fname)
        elif ttype == 'boolean':
            columns[field_name] = fields.Boolean(fname)
        elif ttype == 'many2one':
            columns[field_name] = fields.Many2One(field['related_model'],
                fname, ondelete='SET NULL')
        else:
            raise ValueError("Unknown type: %s" % ttype)

    columns['babi_group'] = fields.Char('Group', size=500)
    columns['parent'] = fields.Many2One(name, 'Parent', ondelete='CASCADE',
        select=True, left='parent_left', right='parent_right')
    columns['children'] = fields.One2Many(name, 'parent', 'Children')
    columns['parent_left'] = fields.Integer('Parent Left', select=True)
    columns['parent_right'] = fields.Integer('Parent Right', select=True)
    return columns


def create_class(name, description, dimensions, measures):
    "Create class, and make instance"
    body = {
        '__doc__': description,
        '__name__': name,
        # Used in get_rec_name()
        '_defaults': {},
        '_babi_dimensions': [x['internal_name'] for x in dimensions],
        }
    body.update(create_columns(name, dimensions + measures))
    return type(name, (DynamicModel, ), body)


def register_class(internal_name, name, dimensions, measures, avoid_registration=False):
    "Register class an return model"
    pool = Pool()
    Model = pool.get('ir.model')

    Class = create_class(internal_name, name, dimensions, measures)
    Pool.register(Class, module='babi', type_='model')
    Class.__setup__()
    pool.add(Class, type='model')
    Class.__post_setup__()
    if avoid_registration:
        models = Model.search([
                ('model', '=', internal_name),
                ])
        if models:
            return models[0]

    # Register only if the model does not yet exist as otherwise
    # we can have concurrency errors on the database when ir.model's
    # register() method updates name and info fields in the database
    Class.__register__('babi')
    model, = Model.search([
            ('model', '=', internal_name),
            ])
    return model


def create_groups_access(model, groups):
    "Creates group access for a given model"
    pool = Pool()
    ModelAccess = pool.get('ir.model.access')
    to_create = []
    for group in groups:
        exists = ModelAccess.search([
                ('model', '=', model.id),
                ('group', '=', group.id),
                ])
        if not exists:
            to_create.append({
                    'model': model.id,
                    'group': group.id,
                    'perm_read': True,
                    'perm_create': True,
                    'perm_write': True,
                    'perm_delete': True,
                    })
    if to_create:
        ModelAccess.create(to_create)


class TimeoutException(Exception):
    pass


class TimeoutChecker:
    def __init__(self, timeout, callback):
        self._timeout = timeout
        self._callback = callback
        self._start = datetime.now()

    def check(self):
        elapsed = (datetime.now() - self._start).seconds
        if elapsed > self._timeout:
            self._callback()


class DimensionIterator:
    def __init__(self, values):
        """
        values should be a dictionary where its values are
        non-empty lists.
        """
        self.values = values
        self.keys = sorted(values.keys())
        self.keys.reverse()
        self.current = dict.fromkeys(values.keys(), 0)
        self.current[self.keys[0]] = -1

    def __iter__(self):
        return self

    def __next__(self):
        for x in range(len(self.keys)):
            key = self.keys[x]
            if self.current[key] >= len(self.values[key]) - 1:
                if x == len(self.keys) - 1:
                    raise StopIteration
                self.current[key] = 0
            else:
                self.current[key] += 1
                break
        return self.current


class Filter(ModelSQL, ModelView):
    "Filter"
    __name__ = 'babi.filter'
    _history = True

    name = fields.Char('Name', required=True, translate=True)
    model = fields.Many2One('ir.model', 'Model', required=True,
        domain=[('babi_enabled', '=', True)])
    model_name = fields.Function(fields.Char('Model Name'),
        'on_change_with_model_name')
    view_search = fields.Many2One('ir.ui.view_search', 'Search',
        domain=[('model', '=', Eval('model_name'))],
        depends=['model_name'])
    domain = fields.Char('Domain')
    python_expression = fields.Char('Python Expression',
        help='The python expression introduced will be evaluated. If the '
        'result is True the record will be included, it will be discarded '
        'otherwise.')
    parameters = fields.One2Many('babi.filter.parameter', 'filter',
        'Parameters',
        states={
            'invisible': Not(Eval('context', {}).get('groups', []).contains(
                Id('babi', 'group_babi_admin'))),
            })
    fields = fields.Function(fields.Many2Many('ir.model.field', None, None,
            'Model Fields', depends=['model']),
        'on_change_with_fields')

    @depends('model')
    def on_change_with_model_name(self, name=None):
        return self.model.model if self.model else None

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


class FilterParameter(ModelSQL, ModelView):
    "Filter Parameter"
    __name__ = 'babi.filter.parameter'
    _history = True

    filter = fields.Many2One('babi.filter', 'Filter', required=True)
    name = fields.Char('Name', required=True, translate=True, help='Name used '
        'on the domain substitution')
    ttype = fields.Selection(FIELD_TYPES + [('date', 'Date'),
        ('many2many', 'Many To Many')], 'Field Type', required=True)
    related_model = fields.Many2One('ir.model', 'Related Model', states={
            'required': Eval('ttype').in_(['many2one', 'many2many']),
            'readonly': Not(Eval('ttype').in_(['many2one', 'many2many'])),
            }, depends=['ttype'])

    def create_keyword(self):
        pool = Pool()
        Action = pool.get('ir.action.wizard')
        ModelData = pool.get('ir.model.data')
        Keyword = pool.get('ir.action.keyword')

        if self.ttype in ['many2one', 'many2many']:
            action = Action(ModelData.get_id('babi', 'open_execution_wizard'))
            keyword = Keyword()
            keyword.keyword = 'form_relate'
            keyword.model = '%s,-1' % self.related_model.model
            keyword.action = action.action
            keyword.babi_filter_parameter = self
            keyword.save()

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
                        self.name),gettext('babi.parameter_not_found',
                            parameter=self.rec_name,
                            filter=self.filter.rec_name))

            return False
        return True

    @classmethod
    def create(cls, vlist):
        filters = super(FilterParameter, cls).create(vlist)
        for filter in filters:
            filter.create_keyword()
        return filters

    @classmethod
    def write(cls, *args):
        pool = Pool()
        Keyword = pool.get('ir.action.keyword')
        super(FilterParameter, cls).write(*args)
        actions = iter(args)
        for filters, values in zip(actions, actions):
            if 'related_model' in values:
                filter_ids = [f.id for f in filters]
                Keyword.delete(Keyword.search([
                            ('babi_filter_parameter', 'in', filter_ids),
                        ]))
                for filter in filters:
                    filter.create_keyword()

    @classmethod
    def delete(cls, filters):
        pool = Pool()
        Keyword = pool.get('ir.action.keyword')
        Keyword.delete(Keyword.search([
                    ('babi_filter_parameter', 'in', [f.id for f in filters]),
                ]))
        super(FilterParameter, cls).delete(filters)


class Expression(ModelSQL, ModelView):
    "Expression"
    __name__ = 'babi.expression'
    _history = True

    name = fields.Char('Name', required=True, translate=True)
    model = fields.Many2One('ir.model', 'Model', required=True,
        domain=[('babi_enabled', '=', True)])
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
            }, depends=['ttype'])
    decimal_digits = fields.Integer('Decimal Digits', states={
            'invisible': ~Eval('ttype').in_(['float', 'numeric']),
            'required': Eval('ttype').in_(['float', 'numeric']),
            })
    fields = fields.Function(fields.Many2Many('ir.model.field', None, None,
            'Model Fields'), 'on_change_with_fields')

    @classmethod
    def default_decimal_digits(cls):
        return 2

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

    @depends('model')
    def on_change_with_fields(self, name=None):
        if not self.model:
            return []
        return [x.id for x in self.model.fields]


class Report(ModelSQL, ModelView):
    "Report"
    __name__ = 'babi.report'
    _history = True

    name = fields.Char('Name', required=True, translate=True,
        help='New virtual model name.')
    model = fields.Many2One('ir.model', 'Model', required=True,
        domain=[('babi_enabled', '=', True)],
        states={'readonly': pysonOr(
                Bool(Eval('dimensions', [0])),
                Bool(Eval('columns', [0])),
                Bool(Eval('measures', [0]))
                ),
            },
        help='Model for data extraction')
    model_name = fields.Function(fields.Char('Model Name'),
        'on_change_with_model_name')
    internal_name = fields.Function(fields.Char('Internal Name', states={
                'invisible': Not(Eval('context', {}).get('groups', []
                        ).contains(Id('babi', 'group_babi_admin'))),
                }),
        'get_internal_name')
    filter = fields.Many2One('babi.filter', 'Filter',
        domain=[('model', '=', Eval('model'))], depends=['model'])
    dimensions = fields.One2Many('babi.dimension', 'report',
        'Dimensions')
    columns = fields.One2Many('babi.dimension.column', 'report',
        'Dimensions on Columns')
    measures = fields.One2Many('babi.measure', 'report', 'Measures')
    order = fields.One2Many('babi.order', 'report', 'Order', order=[
            ('sequence', 'ASC')
            ])
    groups = fields.Many2Many('babi.report-res.group', 'report', 'group',
        'Groups', help='User groups that will be able to see use this report.')
    parent_menu = fields.Many2One('ir.ui.menu', 'Parent Menu',
        required=True)
    menus = fields.One2Many('ir.ui.menu', 'babi_report', 'Menus',
        readonly=True,
        states={
            'invisible': Not(Eval('context', {}).get('groups', []).contains(
                Id('babi', 'group_babi_admin'))),
            })
    actions = fields.One2Many('ir.action.act_window', 'babi_report',
        'Actions', readonly=True,
        states={
            'invisible': Not(Eval('context', {}).get('groups', []).contains(
                Id('babi', 'group_babi_admin'))),
            })
    keywords = fields.One2Many('ir.action.keyword', 'babi_report', 'Keywords',
        readonly=True,
        states={
            'invisible': Not(Eval('context', {}).get('groups', []).contains(
                Id('babi', 'group_babi_admin'))),
            })
    timeout = fields.Integer('Timeout', required=True, help='If report '
        'calculation should take more than the specified timeout (in seconds) '
        'the process will be stopped automatically.')
    executions = fields.One2Many('babi.report.execution', 'report',
        'Executions', readonly=True, order=[('date', 'DESC')],
        states={
            'invisible': Not(Eval('context', {}).get('groups', []).contains(
                Id('babi', 'group_babi_admin'))),
            })
    last_execution = fields.Function(fields.Many2One('babi.report.execution',
        'Last Executions', readonly=True), 'get_last_execution')
    crons = fields.One2Many('ir.cron', 'babi_report', 'Schedulers')
    report_cell_level = fields.Integer('Cell Level',
        help='Start cell level that not has indentation')
    email = fields.Boolean('E-mail',
        help='Mark to see the options to send an email when '
            'executing the cron')
    to = fields.Char('To', states={
        'invisible': Bool(~Eval('email')),
        'required': Bool(Eval('email')),
        }, depends=['email'])
    subject = fields.Char('Subject', states={
        'invisible': Bool(~Eval('email')),
        'required': Bool(Eval('email')),
        }, depends=['email'])
    smtp = fields.Many2One('smtp.server', 'SMTP', states={
        'invisible': Bool(~Eval('email')),
        'required': Bool(Eval('email')),
        }, depends=['email'])

    @classmethod
    def __setup__(cls):
        super(Report, cls).__setup__()
        cls._buttons.update({
                'calculate': {},
                'create_menus': {},
                'remove_menus': {},
                })

    @staticmethod
    def default_timeout():
        Config = Pool().get('babi.configuration')
        config = Config(1)
        return config.default_timeout

    @staticmethod
    def default_report_cell_level():
        Config = Pool().get('babi.configuration')
        config = Config(1)
        return config.report_cell_level or 3

    @depends('model')
    def on_change_with_model_name(self, name=None):
        return self.model.model if self.model else None

    def get_internal_name(self, name):
        return 'babi_report_%d' % self.id

    def get_last_execution(self, name):
        if self.executions:
            for execution in self.executions:
                if execution.state == 'calculated' and not execution.filtered:
                    return execution.id

    @classmethod
    def write(cls, *args):
        actions = iter(args)
        Warning = Pool().get('res.user.warning')
        for reports, values in zip(actions, actions):
            if 'name' in values:
                for report in reports:
                    key ='report_modification_warning_%s' % report.id
                    if report.name != values['name'] and Warning.check(key):
                        raise UserWarning(key,
                            gettext('babi.report_modification_warning',
                                report=report.name))

        return super(Report, cls).write(*args)

    @classmethod
    def delete(cls, reports):
        with Transaction().set_user(0), \
                Transaction().set_context(_check_access=False,
                    user=0,
                    babi_order_force=True):
            cls.remove_menus(reports)
            cls.remove_crons(reports)
            super(Report, cls).delete(reports)

    @classmethod
    def copy(cls, reports, default=None):
        if default is None:
            default = {}
        default = default.copy()
        if 'order' not in default:
            default['order'] = None
        default['actions'] = None
        default['keywords'] = None
        default['menus'] = None
        default['executions'] = None
        if 'name' not in default:
            result = []
            for report in reports:
                default['name'] = '%s (2)' % report.name
                result.extend(super(Report, cls).copy([report], default))
            return result
        return super(Report, cls).copy(reports, default)

    @classmethod
    def remove_crons(cls, reports):
        pool = Pool()
        Cron = pool.get('ir.cron')
        Cron.delete([c for r in reports for c in r.crons])

    @classmethod
    @ModelView.button
    def remove_menus(cls, reports):
        "Remove all menus and actions created"
        pool = Pool()
        ActWindow = pool.get('ir.action.act_window')
        Menu = pool.get('ir.ui.menu')
        actions = []
        menus = []
        for report in reports:
            actions += report.actions
            menus += report.menus
        ActWindow.delete(actions)
        Menu.delete(menus)

    def create_tree_view_menu(self, langs):
        pool = Pool()
        ActWindow = pool.get('ir.action.act_window')
        Action = pool.get('ir.action.wizard')
        Menu = pool.get('ir.ui.menu')
        ModelData = pool.get('ir.model.data')
        encoder = PYSONEncoder()
        # This action is needed for the wizard to open the data
        action = ActWindow()
        action.name = self.name
        action.res_model = 'babi.report'
        action.domain = encoder.encode([('parent', '=', None)])
        action.babi_report = self
        action.groups = self.groups
        action.context = encoder.encode({'babi_tree_view': True})
        action.save()
        wizard = Action(ModelData.get_id('babi', 'open_execution_wizard'))
        menu = Menu()
        menu.name = self.name
        menu.parent = self.parent_menu
        menu.babi_report = self
        menu.action = str(wizard)
        menu.icon = 'tryton-tree'
        menu.groups = self.groups
        menu.babi_type = 'tree'
        menu.save()
        if langs:
            for lang in langs:
                with Transaction().set_context(language=lang.code,
                        fuzzy_translation=False):
                    data, = self.read([self.id], fields_names=['name'])
                    Menu.write([menu], {'name': data['name']})
        return menu.id

    def create_list_view_menu(self, parent, langs):
        "Create list view and action to open"
        pool = Pool()
        ActWindow = pool.get('ir.action.act_window')
        Action = pool.get('ir.action.wizard')
        ModelData = pool.get('ir.model.data')
        Menu = pool.get('ir.ui.menu')
        # This action is needed for the wizard to open the data
        action = ActWindow()
        action.name = self.name
        action.res_model = 'babi.report'
        action.babi_report = self
        action.groups = self.groups
        action.save()
        wizard = Action(ModelData.get_id('babi', 'open_execution_wizard'))
        menu = Menu()
        menu.name = self.name
        menu.parent = parent
        menu.babi_report = self
        menu.action = str(wizard)
        menu.icon = 'tryton-list'
        menu.groups = self.groups
        menu.babi_type = 'list'
        menu.save()
        if langs:
            for lang in langs:
                with Transaction().set_context(language=lang.code,
                        fuzzy_translation=False):
                    data, = self.read([self.id], fields_names=['name'])
                    Menu.write([menu], {'name': data['name']})
        return menu.id

    def create_update_wizard_menu(self, parent):
        pool = Pool()
        Menu = pool.get('ir.ui.menu')
        Action = pool.get('ir.action.wizard')
        ModelData = pool.get('ir.model.data')
        action = Action(ModelData.get_id('babi', 'open_execution_wizard'))
        menu = Menu(ModelData.get_id('babi', 'menu_update_data'))
        menu, = Menu.copy([menu], {
                'parent': parent,
                'babi_report': self.id,
                'icon': 'tryton-launch',
                'groups': [x.id for x in self.groups],
                'babi_type': 'wizard',
                'active': True,
                })
        menu.action = str(action)
        menu.save()

    def create_history_menu(self, parent):
        pool = Pool()
        Action = pool.get('ir.action.wizard')
        ModelData = pool.get('ir.model.data')
        Menu = pool.get('ir.ui.menu')
        action = Action(ModelData.get_id('babi', 'open_execution_wizard'))
        menu = Menu(ModelData.get_id('babi', 'menu_historical_data'))
        menu, = Menu.copy([menu], {
                'parent': parent,
                'babi_report': self.id,
                'icon': 'tryton-launch',
                'groups': [x.id for x in self.groups],
                'babi_type': 'history',
                'active': True,
                })
        menu.action = str(action)
        menu.save()

    @classmethod
    @ModelView.button
    def create_menus(cls, reports):
        """Regenerates all actions and menu entries"""
        pool = Pool()
        Lang = pool.get('ir.lang')
        langs = Lang.search([
            ('translatable', '=', True),
            ])
        cls.remove_menus(reports)
        for report in reports:
            menu = report.create_tree_view_menu(langs)
            report.create_list_view_menu(menu, langs)
            report.create_update_wizard_menu(menu)
            report.create_history_menu(menu)
        return 'reload menu'

    def get_dimensions(self, with_columns=False):
        dimensions = []
        for dimension in self.dimensions:
            dimensions.append(dimension.get_dimension_data())
        if with_columns:
            for dimension in self.columns:
                dimensions.append(dimension.get_dimension_data())

        return dimensions

    def get_execution_data(self):
        return {
            'report': self.id,
            'timeout': self.timeout,
            'company': Transaction().context.get('company'),
            }

    @classmethod
    def calculate_babi_report(cls, reports):
        """Calculate reports and send email (from cron)"""
        HTMLReport = Pool().get('babi.report.html_report', type='report')

        cls.calculate(reports)
        executions = [r.last_execution for r in reports]
        for execution in executions:
            if not execution.report.email:
                continue

            Model = Pool().get(execution.internal_name)
            records = Model.search([('parent', '=', None)])

            data = {
                'model_name': execution.internal_name,
                'report_name': execution.report.name,
                'records': [x.id for x in records],
                'cell_level': execution.report.report_cell_level or 3,
                }
            report = HTMLReport.execute(records, data)

            if report:
                msg = MIMEMultipart()
                msg['To'] = execution.report.to
                msg['From'] = execution.report.smtp.smtp_email
                msg['Subject'] = Header(execution.report.subject, 'utf-8')
                msg.attach(MIMEText('Business Intelligence', 'plain'))

                part = MIMEBase('application', 'octet-stream')
                part.set_payload(report[1])
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', 'attachment; filename=report.pdf')
                msg.attach(part)
                try:
                    server = execution.report.smtp
                    to_addrs = [a for _, a in getaddresses([execution.report.to])]
                    server.send_mail(msg['From'], to_addrs, msg.as_string())
                    logger.info('Send email report: %s' % (execution.report.rec_name))
                except Exception as exception:
                    logger.error('Unable to delivery email report: %s:\n %s' % (
                        execution.report.rec_name, exception))

    def execute(self, execution):
        Execution = Pool().get('babi.report.execution')

        transaction = Transaction()
        user = transaction.user
        database_name = transaction.database.name

        logger.info('Babi execution %s (report "%s")' % (
            execution.id, self.rec_name))

        if celery and BABI_CELERY:
            os.system(
                '%s/celery call %s '
                '--broker=%s --args=[%d,%d] --config="%s" --queue=%s' % (
                    os.path.dirname(sys.executable),
                    BABI_CELERY_TASK,
                    CELERY_BROKER,
                    execution.id,
                    user,
                    CELERY_CONFIG,
                    database_name))
        else:
            # Fallback to synchronous mode if celery is not available
            Execution.calculate([execution])

    @classmethod
    @ModelView.button
    def calculate(cls, reports):
        Execution = Pool().get('babi.report.execution')

        for report in reports:
            if not report.measures:
                raise UserError(gettext('babi.no_measures',
                    report=report.rec_name))
            if not report.dimensions:
                raise UserError(gettext('babi.no_dimensions',
                    report=report.rec_name))
            execution, = Execution.create([report.get_execution_data()])
            Transaction().commit()
            report.execute(execution)


class ReportExecution(ModelSQL, ModelView):
    "Report Execution"
    __name__ = 'babi.report.execution'

    report = fields.Many2One('babi.report', 'Report', required=True,
        readonly=True, ondelete='CASCADE')
    date = fields.DateTime('Execution Date', required=True, readonly=True)
    internal_name = fields.Function(fields.Char('Internal Name'),
        'get_internal_name')
    report_model = fields.Function(fields.Many2One('ir.model', 'Report Model'),
        'on_change_with_report_model')
    babi_model = fields.Many2One('ir.model', 'BI Model', readonly=True,
            help='Link to new model instance')
    state = fields.Selection([
            ('pending', 'Pending'),
            ('in_progress', 'In progress'),
            ('calculated', 'Calculated'),
            ('timeout', 'Timeout'),
            ('failed', 'Failed'),
            ('cancelled', "Cancelled"),
            ], 'State', required=True, readonly=True)
    timeout = fields.Integer('Timeout', required=True, readonly=True,
        help='If report calculation should take more than the specified '
        'timeout (in seconds) the process will be stopped automatically.')
    duration = fields.Float('Duration', readonly=True,
        help='Number of seconds the calculation took.')
    filtered = fields.Boolean('Filtered', help='Used to mark executions with '
        'parameter filters evaluated', readonly=True)
    filter_values = fields.Text('Filter Values', readonly=True)
    internal_measures = fields.One2Many('babi.internal.measure',
        'execution', 'Internal Measures', readonly=True)
    pid = fields.Integer('Pid', readonly=True)
    company = fields.Many2One('company.company', 'Company', required=True,
        domain=[
            ('id', If(Eval('context', {}).contains('company'), '=', '!='),
                Eval('context', {}).get('company', -1)),
            ],
        select=True)

    @classmethod
    def __setup__(cls):
        super(ReportExecution, cls).__setup__()
        cls._order.insert(0, ('date', 'DESC'))
        cls._buttons.update({
                'open': {
                    'invisible': Eval('state') != 'calculated',
                    },
                'cancel': {
                    'invisible': ((Eval('state') != 'in_progress') &
                        ~Eval('pid', False)),
                    },
                })

    @classmethod
    def __register__(cls, module_name):
        cursor = Transaction().connection.cursor()
        sql_table = cls.__table__()

        super(ReportExecution, cls).__register__(module_name)

        # Migration from 5.6: rename state canceled to cancelled
        cursor.execute(*sql_table.update(
                [sql_table.state], ['cancelled'],
                where=sql_table.state == 'canceled'))

    @staticmethod
    def default_date():
        return datetime.now()

    @staticmethod
    def default_state():
        return 'pending'

    @staticmethod
    def default_filtered():
        return False

    @staticmethod
    def default_timeout():
        Config = Pool().get('babi.configuration')
        config = Config(1)
        return config.default_timeout

    @staticmethod
    def default_company():
        return Transaction().context.get('company')

    def get_rec_name(self, name):
        Company = Pool().get('company.company')
        company_id = Transaction().context.get('company')
        date = self.date
        if company_id:
            company = Company(company_id)
            if company.timezone:
                timezone = pytz.timezone(company.timezone)
                date = timezone.localize(self.date)
                date = self.date + date.utcoffset()
        return '%s (%s)' % (self.report.rec_name, date)

    def get_internal_name(self, name):
        return 'babi_execution_%d' % self.id

    def get_measures(self):
        measures = []
        for measure in self.internal_measures:
            measures.append(measure.get_measure_data())
        return measures

    def get_orders(self):
        order = []
        with Transaction().set_context(_datetime=self.date):
            for record in self.report.order:
                if record.dimension:
                    field = record.dimension.internal_name
                    order.append((field, record.order))
                else:
                    for measure in record.measure.internal_measures:
                        if measure.execution == self:
                            field = measure.internal_name
                            order.append((field, record.order))
        return order

    @depends('report')
    def on_change_with_report_model(self, name=None):
        if self.report:
            return self.report.model.id

    @classmethod
    @ModelView.button_action('babi.open_execution_wizard')
    def open(cls, executions):
        pass

    @classmethod
    @ModelView.button
    def cancel(cls, executions):
        for execution in executions:
            if execution.state != 'in_progress':
                continue
            if not execution.pid:
                continue
            os.kill(execution.pid, 15)
            execution.state = 'cancelled'
            execution.save()

    @classmethod
    def delete(cls, executions):
        Model = Pool().get('ir.model')
        Model.delete([x.babi_model for x in executions if x.babi_model])
        cls.remove_data(executions)
        cls.remove_keywords(executions)
        to_delete = set([e.internal_name for e in executions])
        super(ReportExecution, cls).delete(executions)
        # We should remove the classes from the pool so when removing related
        # records it doesn't fail checking unexisting models
        pool = Pool()
        with pool.lock:
            for name in to_delete:
                try:
                    del pool._pool[pool.database_name]['model'][name]
                except KeyError:
                    # The model may not be registered on the pool
                    continue

    @classmethod
    def remove_keywords(cls, executions):
        pool = Pool()
        Keyword = pool.get('ir.action.keyword')

        models = ['%s,-1' % e.babi_model.model for e in executions
            if e.babi_model]
        keywords = Keyword.search([('model', 'in', models)])
        Keyword.delete(keywords)

    @classmethod
    def clean(cls, date=None):
        pool = Pool()
        Date = pool.get('ir.date')
        if date is None:
            date = Date.today() - timedelta(days=BABI_RETENTION_DAYS)

        date = datetime.combine(date, mdatetime.time.min)
        executions = cls.search([('date', '<', date)])
        if executions:
            cls.delete(executions)

        executions = cls.search([()])
        Keyword = pool.get('ir.action.keyword')
        models = ['%s,-1' % e.babi_model.model for e in executions
            if e.babi_model]
        keywords = Keyword.search([('model', 'not in', models),
            ('babi_report', '!=', None)])
        Keyword.delete(keywords)
        return True

    @classmethod
    def remove_data(cls, executions):
        TableHandler = backend.get('TableHandler')
        cursor = Transaction().connection.cursor()
        # Add a transaction for each 200 executions otherwise locks are not
        # released on Postgresql and a exception is raised about too many locks
        for sub_executions in grouped_slice(executions, 200):
            for execution in sub_executions:
                table = execution.internal_name
                if not TableHandler.table_exist(table):
                    continue
                # Table and model are the same.
                TableHandler.drop_table(table, table)
                # There is no method to remove sequence in table
                # handler, so we must remove them manually
                try:
                    # SQLite doesn't have sequences
                    cursor.execute("DROP SEQUENCE IF EXISTS %s_id_seq"
                        % table)
                except:
                    pass
            Transaction().commit()

    def validate_model(self, with_columns=False, avoid_registration=False):
        "makes model available on Tryton and pool instance"

        try:
            dimensions = self.report.get_dimensions(with_columns)
        except AccessError:
            # Do not crash if report no longer exists
            # Tryton will call ir.model's clean() which will check if all
            # models stored in ir.model table exist and try to remove them if
            # they no longer exist.
            return
        measures = self.get_measures()

        model = register_class(self.internal_name, self.report.name,
            dimensions, measures, avoid_registration)

        if not self.babi_model:
            self.babi_model = model
            self.save()

        create_groups_access(model, self.report.groups)
        # Commit transaction to avoid locks
        Transaction().commit()

    def timeout_exception(self):
        raise TimeoutException

    @staticmethod
    def save_state(execution_id, state, exception=False):
        " Save state in a new transaction"
        DatabaseOperationalError = backend.get('DatabaseOperationalError')
        Transaction().rollback()
        with Transaction().new_transaction() as new_transaction:
            try:
                pool = Pool()
                Execution = pool.get('babi.report.execution')
                Model = pool.get('ir.model')
                new_instances = Execution.browse([execution_id])
                to_write = {'state': state}
                if state == 'in_progress':
                    to_write['pid'] = os.getpid()
                Execution.write(new_instances, to_write)
                if exception:
                    Execution.remove_data(new_instances)
                    Model.delete([e.babi_model for e in new_instances])
                new_transaction.commit()
            except DatabaseOperationalError:
                new_transaction.rollback()

    @classmethod
    def calculate(cls, executions):
        transaction = Transaction()
        for execution in executions:
            execution.save_state(execution.id, 'in_progress')
            date = execution.create_date
            with transaction.set_context(_datetime=date):
                execution.validate_model()
                with transaction.set_user(0):
                    execution.create_keywords()
                try:
                    execution.create_data()
                except TimeoutException:
                    execution.save_state(execution.id, 'timeout',
                        exception=True)
                    raise UserError(gettext('babi.timeout_exception'))
                except Exception:
                    execution.save_state(execution.id, 'failed',
                        exception=True)
                    execution.save()
                    raise

    def replace_parameters(self, expression):
        if self.report.filter and self.report.filter.parameters:
            if not self.filter_values:
                raise UserError(gettext('babi.filter_parameters',
                        execution=self.rec_name))
            filter_data = json.loads(self.filter_values,
                object_hook=JSONDecoder())
            parameters = dict((p.id, p.name) for p in
                self.report.filter.parameters)
            values = {}
            for key, value in filter_data.items():
                filter_name = parameters[int(key.split('_')[-1:][0])]
                if not value or filter_name not in expression:
                    continue
                values[filter_name] = value
            expression = expression.format(**values)
        return expression

    def get_python_filter(self):
        if self.report.filter and self.report.filter.python_expression:
            return self.replace_parameters(
                self.report.filter.python_expression)

    def get_domain_filter(self):
        domain = '[]'
        if self.report.filter and self.report.filter.domain:
            domain = self.report.filter.domain
            if '__' in domain:
                domain = str(PYSONDecoder().decode(domain))
        domain = self.replace_parameters(domain)
        # TODO: Use a PYSON domain?
        return eval(domain, {
                'datetime': mdatetime,
                'false': False,
                'true': True,
                })

    def create_keywords(self):
        pool = Pool()
        Action = pool.get('ir.action.wizard')
        ModelData = pool.get('ir.model.data')
        Keyword = pool.get('ir.action.keyword')

        action = Action(ModelData.get_id('babi', 'open_chart_wizard'))
        keyword = Keyword()
        keyword.keyword = 'tree_open'
        keyword.model = '%s,-1' % self.babi_model.model
        keyword.action = action.action
        keyword.babi_report = self.report
        keyword.groups = self.report.groups
        keyword.save()

    def create_data(self):
        "Creates data for this execution"
        pool = Pool()
        Model = pool.get(self.report.model.model)
        transaction = Transaction()
        cursor = transaction.connection.cursor()

        BIModel = pool.get(self.babi_model.model)
        checker = TimeoutChecker(self.timeout, self.timeout_exception)

        logger.info('Updating Data of report: %s' % self.rec_name)
        update_start = time.time()
        model = self.report.model.model
        if not self.report.measures:
            raise UserError(gettext('babi.no_measures', report=self.rec_name))
        if not self.report.dimensions:
            raise UserError(gettext('babi.no_dimensions',
                    report=self.rec_name))

        domain = self.get_domain_filter()
        start = datetime.today()
        self.update_internal_measures()
        with_columns = len(self.report.columns) > 0
        self.validate_model(with_columns=with_columns)

        dimension_names = [x.internal_name for x in self.report.dimensions]
        dimension_expressions = [(x.expression.expression,
                        '' if x.expression.ttype == 'many2one'
                        else 'empty') for x in
            self.report.dimensions]
        measure_names = [x.internal_name for x in
            self.internal_measures]
        measure_expressions = [x.expression for x in
            self.internal_measures]
        if self.report.columns:
            dimension_names.extend([x.internal_name for x in
                    self.report.columns])
            dimension_expressions.extend([(x.expression.expression,
                        '' if x.expression.ttype == 'many2one'
                        else 'empty') for x in self.report.columns])

        columns = (['create_date', 'create_uid'] + dimension_names +
            measure_names)
        columns = ['"%s"' % x for x in columns]
        # Some older versions of psycopg do not allow column names
        # to be of type unicode
        columns = [str(x) for x in columns]

        uid = transaction.user
        python_filter = self.get_python_filter()

        table = BIModel._table
        if self.report.columns:
            table = BIModel._table + '_tmp'
            # Save data to a temporally table:
            cursor.execute('CREATE TEMP TABLE %s AS SELECT * FROM %s WHERE '
                ' 0 = 1' % (table, BIModel._table))

        # Process records
        offset = 2000
        index = 0

        def sanitanize(x):
            if (isinstance(x, str) or isinstance(x, str)
                    or isinstance(x, str)):
                x = x.replace('|', '-')
            if not isinstance(x, str) and isinstance(x, str):
                return str(x.decode('utf-8'))
            else:
                return str(x)

        with transaction.set_context(_datetime=None):
            records = Model.search(domain, offset=index * offset, limit=offset)
        while records:
            checker.check()
            logger.info('Calculated %s,  %s records in %s seconds'
                % (model, index * offset, datetime.today() - start))

            to_create = '' if bytes == str else b''
            # var o it's used on expression!!
            # Don't rename var
            # chunk = records[index * offset:(index + 1) * offset]
            for record in records:
                if python_filter:
                    if not babi_eval(python_filter, record,
                            convert_none=False):
                        continue
                vals = ['now()', str(uid)]
                vals += [sanitanize(babi_eval(x[0], record, convert_none=x[1]))
                    for x in dimension_expressions]
                vals += [sanitanize(babi_eval(x, record, convert_none='zero'))
                    for x in measure_expressions]
                record = '|'.join(vals).replace('\n', ' ')
                record.replace('\\', '')
                record += '\n'
                record = record.encode('utf-8')
                to_create += record

            if to_create:
                data = BytesIO(to_create)
                if hasattr(cursor, 'copy_from'):
                    cursor.copy_from(data, table, sep='|', null='',
                        columns=columns)
                    data.close()
                else:
                    base_query = 'INSERT INTO %s (' % table
                    base_query += ','.join([str(x) for x in columns])
                    base_query += ' ) VALUES '
                    for line in data.readlines():
                        if len(line) == 0:
                            continue
                        if bytes != str:
                            line = line.decode('utf-8')
                        query = base_query + '(now(),'
                        query += ','.join(["'%s'" % str(x)
                                for x in line.split('|')[1:]])
                        query += ')'
                        cursor.execute(query)

            index += 1
            with transaction.set_context(_datetime=None):
                records = Model.search(domain, offset=index * offset,
                    limit=offset)

        if self.report.columns:
            distincts = self.distinct_dimension_columns(cursor, table)
            self.update_internal_measures(distincts)
            self.validate_model()
            query = 'INSERT INTO %s ('
            query += ','.join([str(x) for x in columns])
            query += ',' + ','.join([str(x.internal_name) for x in
                    self.internal_measures])
            query += ') SELECT '
            query += ','.join([str(x) for x in columns])
            query += ',' + ','.join([str(x.expression) for x in
                    self.internal_measures])
            query += ' FROM %s '
            cursor.execute(query % (BIModel._table, table))
            cursor.execute('DROP TABLE %s ' % (table))

        self.update_measures(checker)

        logger.info('Calc all %s records in %s seconds'
            % (model, datetime.today() - start))

        self.state = 'calculated'
        self.duration = time.time() - update_start
        self.save()
        logger.info('End Update Data of report: %s' % self.rec_name)

    def distinct_dimension_columns(self, cursor, tablename):
        distincts = {}
        for dimension in self.report.columns:
            cursor.execute('SELECT %s from %s group by 1 order by 1' % (
                    dimension.internal_name, tablename))
            distincts[dimension.id] = [str(x[0]) for x in
                cursor.fetchall()]
        return distincts

    def update_internal_measures(self, distincts=None):
        InternalMeasure = Pool().get('babi.internal.measure')

        to_create = []
        if distincts is None:
            distincts = {}

        for key in distincts.keys():
            # TODO: Make translatable
            distincts[key] = ['(all)'] + sorted(list(distincts[key]))

        columns = {}
        for column in self.report.columns:
            columns[column.id] = column

        InternalMeasure.delete(self.internal_measures)
        sequence = 0
        for measure in self.report.measures:
            sequence += 1
            related_model_id = None
            if measure.expression.ttype == 'many2one':
                related_model_id = measure.expression.related_model.id
            if distincts:
                iterator = DimensionIterator(distincts)
            else:
                iterator = [None]
            for combination in iterator:
                name = []
                internal_names = []
                expression = measure.expression.expression
                if combination:
                    for key, index in combination.items():
                        dimension = columns[key]
                        value = distincts[key][index]
                        name.append(dimension.name + ' ' + value)
                        internal_names.append(
                            dimension.internal_name + '_' + unaccent(value))
                        # Zero will always be the '(all)' entry added above
                        if index > 0:
                            expression = ('CASE WHEN "%s" = \'%s\' THEN "%s"'
                                'END') % (dimension.internal_name,
                                    _replace(value), measure.internal_name)
                        else:
                            expression = "%s" % (measure.internal_name)

                name.append(measure.name)
                internal_names.append(measure.internal_name)
                name = '/'.join(name)
                # PSQL default column name max characters
                if ((len(internal_names) > 1)
                        and (len('_'.join(internal_names)) > BABI_MAX_BD_COLUMN)):
                    measure_len = len(measure.internal_name)
                    max_len = BABI_MAX_BD_COLUMN - measure_len
                    combination_name = internal_names.pop(0)[:max_len]
                    internal_names.insert(0, combination_name)
                to_create.append({
                        'execution': self.id,
                        'measure': measure.id,
                        'sequence': sequence,
                        'name': name,
                        'internal_name': '_'.join(internal_names),
                        'aggregate': measure.aggregate,
                        'expression': expression,
                        'ttype': measure.expression.ttype,
                        'related_model': related_model_id,
                        'decimal_digits': measure.expression.decimal_digits,
                        })
        if to_create:
            InternalMeasure.create(to_create)

    def update_measures(self, checker):
        # Mapping from types to their null values
        types_null = defaultdict(int)
        types_null['bool'] = False
        types_null['char'] = "''"

        def query_inserts(table_name, measures, select_group, group,
                extra=None):
            """Inserts a group record"""
            transaction = Transaction()
            cursor = transaction.connection.cursor()

            babi_group = ""

            if group:
                babi_group = ",MAX('%s') as babi_group" % group
            local_measures = measures + babi_group

            if extra_data:
                local_measures += ", %s" % extra_data

            select_query = "SELECT %s FROM %s where babi_group IS NULL" % (
                local_measures, table_name)

            if select_group:
                select_query += " GROUP BY %s" % select_group

            if extra_data:
                select_query += ", %s" % extra_data

            fields = []
            for measure in local_measures.split(','):
                if ' as ' in measure:
                    measure = measure.split(' as ')[-1]
                measure = measure.replace('"', '').strip()
                fields.append(unaccent(measure))

            query = "INSERT INTO %s(%s)" % (table_name, ','.join(fields))

            if not transaction.database.has_returning():
                previous_id = 0
                cursor.execute('SELECT MAX(id) FROM %s' % table_name)
                row = cursor.fetchone()
                if row:
                    previous_id = row[0] or 0
                query += select_query
                cursor.execute(query)
                cursor.execute('SELECT id from %s WHERE id > %s ' % (
                        table_name, previous_id))
            else:
                query += " %s RETURNING id" % select_query
                cursor.execute(query)
            return [x[0] for x in cursor.fetchall()]

        def update_parent(table_name, parent_id, group, group_by,
                group_by_types):
            sql_query = []
            for group_item in group_by:
                values = {
                    'item': group_item,
                    'def': types_null[group_by_types[group_item]],
                    'table': table_name,
                    'parent_id': parent_id,
                    }
                # Values should be coalesce to avoid parent errors when null
                group_query = ('Coalesce("%(item)s", %(def)s)=(select '
                    'Coalesce("%(item)s", %(def)s) from %(table)s '
                    'where id = %(parent_id)d)') % values
                sql_query.append(group_query)

            sql_query = ' AND '.join(sql_query)
            sql_query[:-5]

            query = """
                UPDATE """ + table_name + """ set parent=%s
                WHERE
                    parent IS NULL AND
                    id != %s AND
                    babi_group = '%s'
                    """ % (parent_id, parent_id, group)
            if sql_query:
                query += 'AND %s' % sql_query
            cursor.execute(query)

        pool = Pool()
        BIModel = pool.get(self.babi_model.model)

        if not self.internal_measures:
            return

        group_by_types = dict([(x.internal_name, x.expression.ttype)
                for x in self.report.dimensions if x.group_by])
        group_by = [x.internal_name for x in self.report.dimensions
            if x.group_by]

        extra_data = ",".join([x.internal_name for x in self.report.dimensions
            if not x.group_by])

        table_name = Pool().get(self.babi_model.model)._table
        cursor = Transaction().connection.cursor()

        group_by_iterator = group_by[:]

        aggregate = None
        current_group = None

        while group_by_iterator:
            checker.check()

            group = ['"%s"' % x for x in group_by_iterator]
            measures = ['%s("%s") as %s' % (
                        x.aggregate == 'count' and aggregate or x.aggregate,
                        x.internal_name,
                        x.internal_name,
                        ) for x in self.internal_measures] + group
            measures = ','.join(measures)
            group = ','.join(group)

            logger.info('SELECT table_name %s, measures %s, groups %s' % (
                    table_name, measures, group))

            child_group = current_group
            current_group = group_by[len(group_by_iterator) - 1]
            parent_ids = query_inserts(table_name, measures, group,
                current_group, extra_data)

            if group_by != group_by_iterator:
                for parent_id in parent_ids:
                    update_parent(table_name, parent_id, child_group,
                        group_by_iterator, group_by_types)

            child_group = current_group
            group_by_iterator.pop()
            extra_data = None

        # ROOT
        measures = ",".join(['%s("%s") as %s' % (
                    x.aggregate == 'count' and aggregate or x.aggregate,
                    x.internal_name, x.internal_name) for x in
                    self.internal_measures])
        group = None
        parent_id = query_inserts(table_name, measures, None, None)[0]
        # TODO: Translate '(all)'
        if group_by_types[group_by[0]] != 'many2one':
            cursor.execute("UPDATE " + table_name + " SET \"" + group_by[0] +
                "\"='" + '(all)' + "' WHERE id=%s" % parent_id)
        update_parent(table_name, parent_id, child_group, group_by_iterator,
            group_by_types)
        delete = 'DELETE FROM %s WHERE babi_group IS NULL' % (table_name)
        cursor.execute(delete + ' and id != %s ' % parent_id)
        # Update parent_left, parent_right
        BIModel._rebuild_tree('parent', None, 0)


class OpenExecutionSelect(ModelView):
    "Open Report Execution - Select Values"
    __name__ = 'babi.report.execution.open.select'

    # TODO: Add domain for validating report permisions
    report = fields.Many2One('babi.report', 'Report', required=True,
        states={
            'readonly': Bool(Eval('report_readonly')),
            }, depends=['report_readonly'])
    execution = fields.Many2One('babi.report.execution', 'Execution',
        required=True, domain=[
            ('report', '=', Eval('report')),
            ('state', '=', 'calculated'),
            ],
        states={
            'readonly': Bool(Eval('execution_readonly')),
            }, depends=['report', 'execution_readonly'])
    view_type = fields.Selection([
            ('tree', 'Tree'),
            ('list', 'List'),
            ], 'View type', required=True)

    report_readonly = fields.Boolean('Report Readonly')
    execution_readonly = fields.Boolean('Execution Readonly')

    @classmethod
    def default_get(cls, fields, with_rec_name=True):
        pool = Pool()
        Execution = pool.get('babi.report.execution')
        Menu = pool.get('ir.ui.menu')

        result = super(OpenExecutionSelect, cls).default_get(fields,
            with_rec_name)

        active_id = Transaction().context.get('active_id')
        model_name = Transaction().context.get('active_model')

        if model_name == 'babi.report.execution':
            execution = Execution(active_id)
            result.update({
                    'execution': execution.id,
                    'report': execution.report.id,
                    'view_type': 'tree',
                    'report_readonly': True,
                    'execution_readonly': True,
                    })
        elif model_name == 'ir.ui.menu':
            menu = Menu(active_id)
            result.update({
                    'report': menu.babi_report.id,
                    'view_type': 'tree',
                    'report_readonly': True,
                    })
            if menu.babi_type == 'filtered':
                result.update({
                        'execution_readonly': True,
                        })

        return result

    @depends('report')
    def on_change_report(self):
        if not self.report:
            self.execution = None


class OpenExecutionFiltered(StateView):

    def __init__(self):
        buttons = [
                Button('Cancel', 'end', 'tryton-cancel'),
                Button('Open', 'create_execution', 'tryton-ok', True),
                ]
        super(OpenExecutionFiltered, self).__init__('babi.report', 0, buttons)

    def get_view(self, wizard, state_name):
        pool = Pool()
        Menu = pool.get('ir.ui.menu')
        Report = pool.get('babi.report')
        Execution = pool.get('babi.report.execution')
        Parameter = pool.get('babi.filter.parameter')

        context = Transaction().context
        model = context.get('active_model')

        execution_definitions = Execution.fields_get(fields_names=[
                'report', 'report_model'])
        report_definition = execution_definitions['report']
        report_definition['required'] = True

        result = {}
        result['type'] = 'form'
        result['view_id'] = None
        result['model'] = 'babi.report.execution'
        result['field_childs'] = None
        fields = {}
        parameter2report = {}

        if model == 'ir.ui.menu':
            menu = Menu(context.get('active_id'))
            filter = menu.babi_report.filter
            report_definition['readonly'] = True
            parameters = Parameter.search([('filter', '=', filter)])
        else:
            # TODO: Report definition add domain for groups
            parameters = Parameter.search([
                        ('related_model.model', '=',
                            context.get('active_model'))],
                )
            report_definition['readonly'] = False
            reports = Report.search([('filter', 'in',
                        [p.filter for p in parameters])])

            for report in reports:
                key = report.filter.id
                if key in parameter2report:
                    parameter2report[key].append(report.id)
                else:
                    parameter2report[key] = [report.id]
            report_definition['domain'] = ['id', 'in', [r.id for r in reports]]

        parameters_to_remove = []
        for parameter in parameters:
            if not parameter.check_parameter_in_filter():
                parameters_to_remove.append(parameter)
        for parameter in parameters_to_remove:
            parameters.remove(parameter)

        xml = '<form string="Generate Filtered Report">\n'
        xml += '<label name="report"/>\n'
        xml += '<field name="report" colspan="3"/>\n'
        fields['report'] = report_definition
        encoder = PYSONEncoder()
        xml += '<group id="filters" string="Filters" colspan="4">\n'
        for parameter in parameters:
            # The wizard breaks with non unicode data
            name = 'filter_parameter_%d' % parameter.id
            field_definition = {
                'loading': 'eager',
                'name': name,
                'string': parameter.name,
                'searchable': True,
                'create': True,
                'help': '',
                'context': {},
                'delete': True,
                'type': parameter.ttype,
                'select': False,
                'readonly': False,
                'required': True,
            }
            if parameter.ttype in['many2one', 'many2many']:
                field_definition['relation'] = parameter.related_model.model
            if parameter2report:
                field_definition['states'] = {
                    'invisible': Not(In(Eval('report', 0),
                            parameter2report[parameter.filter.id])),
                    'required': In(Eval('report', 0),
                        parameter2report[parameter.filter.id]),
                    }
            else:
                field_definition['states'] = {}
            # Copied from Model.fields_get
            for attr in ('states', 'domain', 'context', 'digits', 'size',
                    'add_remove', 'format'):
                if attr in field_definition:
                    field_definition[attr] = encoder.encode(
                        field_definition[attr])

            if parameter.ttype == 'many2many':
                xml += '<field name="%s" colspan="4"/>\n' % (name)
            else:
                xml += '<label name="%s"/>\n' % (name)
                xml += '<field name="%s" colspan="3"/>\n' % (name)
            fields[name] = field_definition

        xml += '</group>\n'
        xml += '</form>\n'
        result['arch'] = xml
        result['fields'] = fields
        return result

    def get_defaults(self, wizard, state_name, fields):
        pool = Pool()
        Menu = pool.get('ir.ui.menu')
        Parameter = pool.get('babi.filter.parameter')
        context = Transaction().context
        model = context.get('active_model')

        defaults = {}
        if model == 'ir.ui.menu':
            menu = Menu(context.get('active_id'))
            defaults['report'] = menu.babi_report.id
        else:
            parameters = Parameter.search([
                    ('related_model.model', '=', model),
                    ])
            for parameter in parameters:
                name = '%s_%d' % (parameter.name, parameter.id)
                defaults[name] = context.get('active_id')
        return defaults


class CustomDict(dict):

    def __getattr__(self, name):
        return {}

    def __setattr__(self, name, value):
        self[name] = value


class UpdateDataWizardStart(ModelView):
    "Update Data Wizard Start"
    __name__ = 'babi.update_data.wizard.start'


class UpdateDataWizardUpdated(ModelView):
    "Update Data Wizard Done"
    __name__ = 'babi.update_data.wizard.done'


class OpenExecution(Wizard):
    'Open Report Execution'
    __name__ = 'babi.report.execution.open'

    start = StateTransition()
    update_start = StateView('babi.update_data.wizard.start',
        'babi.update_data_wizard_start_form_view', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Ok', 'update', 'tryton-ok', default=True),
            ])
    filtered = OpenExecutionFiltered()
    create_execution = StateTransition()
    select = StateView('babi.report.execution.open.select',
        'babi.open_execution_select_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Open', 'open_view', 'tryton-ok', True),
            ])
    open_view = StateAction('babi.open_execution_wizard')
    update = StateTransition()
    update_done = StateView('babi.update_data.wizard.done',
        'babi.update_data_wizard_done_form_view', [
            Button('Ok', 'end', 'tryton-ok', default=True),
            ])

    def __getattribute__(self, name):
        if name == 'filtered':
            if not hasattr(self, 'filter_values'):
                self.filter_values = CustomDict()
            name = 'filter_values'
        return super(OpenExecution, self).__getattribute__(name)

    def transition_start(self):
        pool = Pool()
        Menu = pool.get('ir.ui.menu')
        context = Transaction().context
        model_name = context.get('active_model')
        if model_name == 'babi.report.execution':
            return 'select'
        elif model_name == 'ir.ui.menu':
            menu = Menu(context.get('active_id'))
            if menu.babi_report.filter and \
                    len(menu.babi_report.filter.parameters) > 0:
                return 'filtered'
            if menu.babi_type == 'history':
                return 'select'
            if menu.babi_type == 'wizard':
                return 'update_start'
            return 'open_view'
        else:
            return 'filtered'

    def transition_create_execution(self):
        pool = Pool()
        Report = pool.get('babi.report')
        Execution = pool.get('babi.report.execution')

        report = self.filter_values.pop('report', None)
        if not report:
            raise UserError(gettext('babi.no_report_found'))

        data = {}
        for key, value in self.filter_values.items():
            # Fields has id of the field appendend, so it must be removed.
            new_key = '_'.join(key.split('_')[:-1])
            data[new_key] = value
        report = Report(report)
        execution = report.get_execution_data()
        data = json.dumps(self.filter_values, cls=JSONEncoder)
        execution['filter_values'] = data
        execution['filtered'] = True
        execution, = Execution.create([execution])
        Transaction().commit()
        Execution.calculate([execution])

        context = Transaction().context
        context.update({
                'filtered_execution': execution.id,
                })
        return 'open_view'

    def transition_update(self):
        pool = Pool()
        Menu = pool.get('ir.ui.menu')
        Report = pool.get('babi.report')

        menu = Menu(Transaction().context['active_id'])
        Report.calculate([menu.babi_report])
        return 'update_done'

    def do_open_view(self, action):
        pool = Pool()
        Action = pool.get('ir.action')
        ActionWindow = pool.get('ir.action.act_window')
        Menu = pool.get('ir.ui.menu')
        Execution = pool.get('babi.report.execution')

        transaction = Transaction()
        context = transaction.context

        model_name = context.get('active_model')
        if model_name == 'ir.ui.menu':
            menu = Menu(context.get('active_id'))
            if menu.babi_type == 'history' and hasattr(self.select, 'report'):
                report = self.select.report
                execution = self.select.execution
                view_type = self.select.view_type
            else:
                report = menu.babi_report
                if 'filtered_execution' in context:
                    execution = Execution(context.get('filtered_execution'))
                else:
                    execution = report.last_execution
                view_type = menu.babi_type
        else:
            report = self.select.report
            execution = self.select.execution
            view_type = self.select.view_type

        if not execution:
            raise UserError(gettext('babi.no_execution',
                report=report.rec_name))

        with transaction.set_context(_datetime=execution.date):
            execution.validate_model()
        domain = [
            ('babi_report', '=', report.id),
            ]
        if view_type == 'tree':
            domain.append(('context', 'ilike', "%%babi_tree_view%%"))
        else:
            domain.append(('context', 'not ilike', "%%babi_tree_view%%"))
        try:
            action, = ActionWindow.search(domain, limit=1)
            action = Action.get_action_values(action.type, [action.id])[0]
        except ValueError:
            raise UserError(gettext('babi.no_menus', report=report.rec_name))
        action['res_model'] = execution.babi_model.model
        action['name'] = execution.rec_name
        action['context_model'] = None
        return action, {}


class ReportGroup(ModelSQL):
    "Report - Group"
    __name__ = 'babi.report-res.group'

    report = fields.Many2One('babi.report', 'Report', required=True,
        ondelete='CASCADE')
    group = fields.Many2One('res.group', 'Group', required=True)

    @classmethod
    def __setup__(cls):
        super(ReportGroup, cls).__setup__()
        t = cls.__table__()
        cls._sql_constraints += [
            ('report_group_uniq', Unique(t, t.report, t.group),
                'Report and Group must be unique.'),
            ]


class DimensionMixin:

    report = fields.Many2One('babi.report', 'Report', required=True,
        ondelete='CASCADE')
    sequence = fields.Integer('Sequence')
    name = fields.Char('Name', required=True, translate=True)
    internal_name = fields.Function(fields.Char('Internal Name'),
        'get_internal_name')
    expression = fields.Many2One('babi.expression', 'Expression',
        required=True, domain=[
            ('model', '=', Eval('_parent_report', {}).get('model', 0)),
            ])
    group_by = fields.Boolean('Group By This Dimension')
    width = fields.Integer('Width',
        help='Width report columns (%)')

    def get_internal_name(self, name):
        return 'babi_dimension_%d' % self.id

    @staticmethod
    def order_sequence(tables):
        table, _ = tables[None]
        return [table.sequence == Null, table.sequence]

    @staticmethod
    def default_group_by():
        return True

    @depends('expression')
    def on_change_with_name(self):
        return self.expression.name if self.expression else None

    def get_dimension_data(self):
        return {
            'name': self.name,
            'internal_name': self.internal_name,
            'expression': self.expression.expression,
            'ttype': self.expression.ttype,
            'related_model': (self.expression.related_model
                and self.expression.related_model.model),
            'decimal_digits': self.expression.decimal_digits,
            }


class Dimension(ModelSQL, ModelView, DimensionMixin):
    "Dimension"
    __name__ = 'babi.dimension'
    _history = True

    @classmethod
    def __setup__(cls):
        super(Dimension, cls).__setup__()
        t = cls.__table__()
        cls._order.insert(0, ('sequence', 'ASC'))
        cls._sql_constraints += [
            ('report_and_name_unique', Unique(t, t.report, t.name),
                'Dimension name must be unique per report.'),
            ]

    @classmethod
    def update_order(cls, dimensions):
        Order = Pool().get('babi.order')
        cursor = Transaction().connection.cursor()
        dimension_ids = [x.id for x in dimensions if x.group_by]
        orders = Order.search([
                ('dimension', 'in', dimension_ids),
                ])
        existing = [x.dimension.id for x in orders]
        missing = set(dimension_ids) - set(existing)
        to_create = []
        for dimension in cls.browse(list(missing)):
            cursor.execute('SELECT MAX(sequence) FROM babi_order WHERE '
                'report=%s' % dimension.report.id)
            sequence = cursor.fetchone()[0] or 0
            to_create.append({
                    'report': dimension.report.id,
                    'sequence': sequence + 10,
                    'dimension': dimension.id,
                    })
        with Transaction().set_context({'babi_order_force': True}):
            Order.create(to_create)

    @classmethod
    def create(cls, values):
        dimensions = super(Dimension, cls).create(values)
        cls.update_order(dimensions)
        return dimensions

    @classmethod
    def write(cls, *args):
        actions = iter(args)
        to_update = []
        for dimensions, _ in zip(actions, actions):
            to_update += dimensions
        cls.update_order(to_update)
        return super(Dimension, cls).write(*args)

    @classmethod
    def delete(cls, dimensions):
        Order = Pool().get('babi.order')
        orders = Order.search([
                ('dimension', 'in', [x.id for x in dimensions]),
                ])
        if orders:
            with Transaction().set_context({'babi_order_force': True}):
                Order.delete(orders)
        return super(Dimension, cls).delete(dimensions)


class DimensionColumn(ModelSQL, ModelView, DimensionMixin):
    "Column Dimension"
    __name__ = 'babi.dimension.column'
    _history = True

    @classmethod
    def __setup__(cls):
        super(DimensionColumn, cls).__setup__()
        cls._order.insert(0, ('sequence', 'ASC'))

    def get_internal_name(self, name):
        return 'babi_dimension_column_%d' % self.id


class Measure(ModelSQL, ModelView):
    "Measure"
    __name__ = 'babi.measure'
    _history = True

    report = fields.Many2One('babi.report', 'Report', required=True,
        ondelete='CASCADE')
    sequence = fields.Integer('Sequence')
    name = fields.Char('Name', required=True, translate=True)
    internal_name = fields.Function(fields.Char('Internal Name'),
        'get_internal_name')
    expression = fields.Many2One('babi.expression', 'Expression',
        required=True, domain=[
            ('model', '=', Eval('_parent_report', {}).get('model', 0)),
            ])
    aggregate = fields.Selection(AGGREGATE_TYPES, 'Aggregate', required=True)
    internal_measures = fields.One2Many('babi.internal.measure',
        'measure', 'Internal Measures')
    width = fields.Integer('Width',
        help='Width report columns (%)')

    @classmethod
    def __setup__(cls):
        super(Measure, cls).__setup__()
        t = cls.__table__()
        cls._order.insert(0, ('sequence', 'ASC'))
        cls._sql_constraints += [
            ('report_and_name_unique', Unique(t, t.report, t.name),
                'Measure name must be unique per report.'),
            ]

    @staticmethod
    def order_sequence(tables):
        table, _ = tables[None]
        return [table.sequence == Null, table.sequence]

    @staticmethod
    def default_aggregate():
        return 'sum'

    @depends('expression')
    def on_change_with_name(self):
        return self.expression.name if self.expression else None

    def get_internal_name(self, name):
        return 'babi_measure_%d' % (self.id)

    def get_measure_data(self):
        return {
            'name': self.name,
            'internal_name': self.internal_name,
            'expression': self.expression,
            'ttype': self.ttype,
            'related_model': (self.related_model and
                self.related_model.model),
            'decimal_digits': self.expression.decimal_digits,
            }

    @classmethod
    def update_order(cls, measures):
        Order = Pool().get('babi.order')
        cursor = Transaction().connection.cursor()

        measure_ids = [x.id for x in measures]
        orders = Order.search([
                ('measure', 'in', measure_ids),
                ])
        existing_ids = [x.measure.id for x in orders]

        missing_ids = set(measure_ids) - set(existing_ids)
        to_create = []
        for measure in cls.browse(list(missing_ids)):
            cursor.execute('SELECT MAX(sequence) FROM babi_order WHERE '
                'report=%s' % measure.report.id)
            sequence = cursor.fetchone()[0] or 0
            to_create.append({
                    'report': measure.report.id,
                    'sequence': sequence + 1,
                    'measure': measure.id,
                    })
        with Transaction().set_context({'babi_order_force': True}):
            Order.create(to_create)

    @classmethod
    def create(cls, values):
        measures = super(Measure, cls).create(values)
        cls.update_order(measures)
        return measures

    @classmethod
    def write(cls, *args):
        actions = iter(args)
        to_update = []
        for measures, _ in zip(actions, actions):
            to_update += measures
        cls.update_order(to_update)
        return super(Measure, cls).write(*args)

    @classmethod
    def delete(cls, measures):
        Order = Pool().get('babi.order')
        to_remove = []
        for measure in measures:
            orders = Order.search([
                    ('measure', '=', measure.id),
                    ])
            to_remove += orders
        if to_remove:
            with Transaction().set_context({'babi_order_force': True}):
                Order.delete(to_remove)
        return super(Measure, cls).delete(measures)


class InternalMeasure(ModelSQL, ModelView):
    "Internal Measure"
    __name__ = 'babi.internal.measure'

    execution = fields.Many2One('babi.report.execution', 'Report Execution',
        required=True, ondelete='CASCADE')
    measure = fields.Many2One('babi.measure', 'Measure', required=True,
        ondelete='CASCADE')
    sequence = fields.Integer('Sequence', required=True)
    name = fields.Char('Name', required=True)
    internal_name = fields.Char('Internal Name', required=True)
    expression = fields.Char('Expression')
    aggregate = fields.Selection(AGGREGATE_TYPES, 'Aggregate', required=True)
    ttype = fields.Selection(FIELD_TYPES, 'Field Type',
        required=True)
    related_model = fields.Many2One('ir.model', 'Related Model')
    decimal_digits = fields.Integer('Decimal Digits')
    width = fields.Integer('Width')

    @classmethod
    def __setup__(cls):
        super(InternalMeasure, cls).__setup__()
        cls._order.insert(0, ('sequence', 'ASC'))

    @classmethod
    def __register__(cls, module_name):
        TableHandler = backend.get('TableHandler')
        super(InternalMeasure, cls).__register__(module_name)
        cursor = Transaction().connection.cursor()
        sql_table = cls.__table__()

        # Migration from 3.0: no more relation with reports.
        table = TableHandler(cls, module_name)
        if table.column_exist('report'):
            table.not_null_action('report', action='remove')

        # Migration from int to integer
        cursor.execute(*sql_table.update([Column(sql_table, 'ttype')],
                ['integer'], where=sql_table.ttype == 'int'))
        # Migration from bool to boolean
        cursor.execute(*sql_table.update([Column(sql_table, 'ttype')],
                ['boolean'], where=sql_table.ttype == 'bool'))

    def get_measure_data(self):
        return {
            'name': self.name,
            'internal_name': self.internal_name,
            'expression': self.expression,
            'ttype': self.ttype,
            'related_model': (self.related_model and
                self.related_model.model),
            'decimal_digits': self.decimal_digits,
            }


class Order(ModelSQL, ModelView, sequence_ordered()):
    "Order"
    __name__ = 'babi.order'
    _history = True

    report = fields.Many2One('babi.report', 'Report', required=True,
        ondelete='CASCADE')
    dimension = fields.Many2One('babi.dimension', 'Dimension', readonly=True)
    measure = fields.Many2One('babi.measure', 'Measure', readonly=True)
    order = fields.Selection([
            ('ASC', 'Ascending'),
            ('DESC', 'Descending'),
            ], 'Order', required=True)

    @staticmethod
    def default_order():
        return 'ASC'

    @classmethod
    def __setup__(cls):
        super(Order, cls).__setup__()
        t = cls.__table__()
        cls._sql_constraints += [
            ('report_and_dimension_unique', Unique(t, t.report, t.dimension),
                'Dimension must be unique per report.'),
            ('report_and_measure_unique', Unique(t, t.report, t.measure),
                'Measure must be unique per report.'),
            ('dimension_or_measure', Check(t, Or((
                            (t.dimension == Null) & (t.measure != Null),
                            (t.dimension != Null) & (t.measure == Null)
                            ))),
                'Only dimension or measure can be set.'),
            ]

    @classmethod
    def create(cls, values):
        if not Transaction().context.get('babi_order_force'):
            raise UserError(gettext('babi.cannot_create_order_entry'))
        return super(Order, cls).create(values)

    @classmethod
    def delete(cls, orders):
        if not Transaction().context.get('babi_order_force'):
            raise UserError(gettext('babi.cannot_remove_order_entry'))
        return super(Order, cls).delete(orders)


class ActWindow(metaclass=PoolMeta):
    __name__ = 'ir.action.act_window'

    babi_report = fields.Many2One('babi.report', 'BABI Report')


class Menu(metaclass=PoolMeta):
    __name__ = 'ir.ui.menu'

    babi_report = fields.Many2One('babi.report', 'BABI Report')
    babi_type = fields.Selection([
            (None, ''),
            ('tree', 'Tree'),
            ('list', 'List'),
            ('history', 'History'),
            ('wizard', 'Wizard'),
            ], 'BABI Type', readonly=True)


class Keyword(metaclass=PoolMeta):
    __name__ = 'ir.action.keyword'

    babi_report = fields.Many2One('babi.report', 'BABI Report')
    babi_filter_parameter = fields.Many2One('babi.filter.parameter',
        'BABI Filter Parameter')


class Model(metaclass=PoolMeta):
    __name__ = 'ir.model'

    babi_enabled = fields.Boolean('BI Enabled', help='Check if you want '
        'this model to be available in Business Intelligence reports.')


class OpenChartStart(ModelView):
    "Open Chart Start"
    __name__ = 'babi.open_chart.start'

    graph_type = fields.Selection([
            ('vbar', 'Vertical Bars'),
            ('hbar', 'Horizontal Bars'),
            ('line', 'Line'),
            ('pie', 'Pie'),
            ('report', 'Report'),
            ], 'Graph', required=True, sort=False)
    interpolation = fields.Selection([
            ('linear', 'Linear'),
            ('constant-center', 'Constant Center'),
            ('constant-left', 'Constant Left'),
            ('constant-right', 'Constant Right'),
            ], 'Interpolation',
        states={
            'required': Eval('graph_type') == 'line',
            'invisible': Eval('graph_type') != 'line',
            }, depends=['graph_type'], sort=False)
    show_legend = fields.Boolean('Show Legend',
        states={
            'invisible': (Eval('graph_type') == 'report'),
        }, depends=['graph_type'])
    report = fields.Many2One('babi.report', 'Report',
        states={
            'invisible': (Eval('graph_type') == 'report'),
        }, depends=['graph_type'])
    execution = fields.Many2One('babi.report.execution', 'Execution',
        states={
            'invisible': (Eval('graph_type') == 'report'),
        }, depends=['graph_type'])
    execution_date = fields.DateTime('Execution Time',
        states={
            'invisible': (Eval('graph_type') == 'report'),
        }, depends=['graph_type'])
    dimension = fields.Many2One('babi.dimension', 'Dimension',
        domain=[
            ('report', '=', Eval('report')),
            ],
        context={
            '_datetime': Eval('execution_date'),
            },
        states={
            'required': Eval('graph_type') != 'report',
            'invisible': Eval('graph_type') == 'report',
        }, depends=['report', 'execution_date', 'graph_type'])
    measures = fields.Many2Many('babi.internal.measure', None, None,
        'Measures', required=True,
        domain=[
            ('execution', '=', Eval('execution')),
            ],
        states={
            'required': Eval('graph_type') != 'report',
            'invisible': Eval('graph_type') == 'report',
        }, depends=['execution', 'graph_type'])

    @classmethod
    def view_attributes(cls):
        return [('/form/group[@id="labels"]', 'states',
            {'invisible': Eval('graph_type') != 'report'})]

    @classmethod
    def default_get(cls, fields, with_rec_name=True):
        pool = Pool()
        Execution = pool.get('babi.report.execution')
        model_name = Transaction().context.get('active_model')
        executions = Execution.search([
                ('babi_model.model', '=', model_name),
                ], limit=1)

        result = super(OpenChartStart, cls).default_get(fields, with_rec_name)
        if len(executions) != 1:
            return result
        execution, = executions
        report = execution.report
        Model = pool.get(model_name)
        active_id, = Transaction().context.get('active_ids')
        record = Model(active_id)

        with Transaction().set_context(_datetime=execution.create_date):
            fields = []
            found = False
            for x in report.dimensions:
                if found:
                    fields.append(x.id)
                    continue
                if x.internal_name == str(record.babi_group):
                    found = True

            if not fields:
                # If it was not found it means user clicked on 'root'
                # babi_group
                fields = [x.id for x in report.dimensions]
        return {
            'report': execution.report.id,
            'execution': execution.id,
            'execution_date': execution.date,
            'model': execution.babi_model.id,
            'dimension': fields[0] if fields else None,
            'measures': [x.id for x in execution.internal_measures],
            'graph_type': 'vbar',
            'show_legend': True,
            'interpolation': 'linear',
            }


class EmptyStateAction(StateAction):
    def __init__(self):
        super(EmptyStateAction, self).__init__(None)

    def get_action(self):
        return {}


class OpenChart(Wizard):
    "Open Chart"
    __name__ = 'babi.open_chart'
    start = StateView('babi.open_chart.start',
        'babi.open_chart_start_form_view', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Print', 'print_', 'tryton-ok',
                states={
                    'invisible': (Eval('graph_type') != 'report'),
                },
            ),
            Button('Open', 'open_', 'tryton-ok', default=True,
                states={
                    'invisible': (Eval('graph_type') == 'report'),
                },
            ),
            ])
    open_ = EmptyStateAction()
    print_ = StateReport('babi.report.html_report')

    def do_open_(self, action):
        pool = Pool()

        context = Transaction().context
        model_name = context.get('active_model')
        active_ids = context.get('active_ids')

        Model = pool.get(model_name)

        if len(self.start.measures) > 1 and self.start.graph_type == 'pie':
            raise UserError(gettext('babi.one_measure_in_pie_charts'))

        group_name = self.start.dimension.internal_name
        records = Model.search([
                ('babi_group', '=', group_name),
                ('parent', 'child_of', active_ids),
                ])
        domain = [('id', 'in', [x.id for x in records])]
        domain = json.dumps(domain)
        context = {}
        context['view_type'] = 'graph'
        context['graph_type'] = self.start.graph_type
        context['dimension'] = self.start.dimension.id
        context['measures'] = [x.id for x in self.start.measures]
        context['legend'] = self.start.show_legend
        context['interpolation'] = self.start.interpolation
        context['model_name'] = model_name
        context = json.dumps(context)

        action = {
            'id': -1,
            'name': '%s - %s Chart' % (self.start.execution.rec_name,
                self.start.dimension.rec_name),
            'model': model_name,
            'res_model': model_name,
            'type': 'ir.action.act_window',
            'context_model': None,
            'context_domain': None,
            'pyson_domain': domain,
            'pyson_context': context,
            'pyson_order': '[]',
            'pyson_search_value': '[]',
            'domains': [],
            }
        return action, {}

    def do_print_(self, action):
        context = Transaction().context
        model_name = context.get('active_model')
        active_ids = context.get('active_ids')

        report = self.start.report

        data = {
            'model_name': model_name,
            'report_name': report.name,
            'records': active_ids,
            'cell_level': report.report_cell_level or 3,
            }
        return action, data

    def transition_print_(self):
        return 'end'


class CleanExecutionsStart(ModelView):
    'Clean Execution Start'
    __name__ = 'babi.clean_executions.start'

    date = fields.Date('Date', required=True)


class CleanExecutions(Wizard):
    'Clean Executions'
    __name__ = 'babi.clean_executions'
    start = StateView('babi.clean_executions.start',
        'babi.clean_executions_start_form_view', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Ok', 'clean', 'tryton-ok', default=True),
            ])
    clean = StateTransition()

    def transition_clean(self):
        pool = Pool()
        Execution = pool.get('babi.report.execution')
        Execution.clean(self.start.date)
        return 'end'
