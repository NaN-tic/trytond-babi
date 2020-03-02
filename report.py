# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import os
import json
from datetime import datetime
from trytond.pool import Pool
from trytond.transaction import Transaction
from trytond.rpc import RPC
from trytond.protocols.jsonrpc import JSONDecoder
from trytond.report import Report
from trytond.i18n import gettext

__all__ = ['BabiHTMLReport']


class BabiHTMLReport(Report):
    __name__ = 'babi.report.html_report'

    @classmethod
    def __setup__(cls):
        super(BabiHTMLReport, cls).__setup__()
        cls.__rpc__['execute'] = RPC(False)

    @classmethod
    def prepare(cls, ids, data):
        Model = Pool().get(data['model_name'])

        records = []
        parameters = {}

        def get_childs(record):
            childs = []
            for r in Model.search([
                    # ('babi_group', '=', group_name),
                    ('parent', '=', record.id),
                    ]):
                childs.append(get_childs(r))
            return {
                'record': record,
                'childs': childs,
                }

        for record in Model.search([
                ('id', 'in', data['records']),
                ]):
            records.append(get_childs(record))

        return records, parameters

    @classmethod
    def format_filter(cls, execution):
        pool = Pool()
        Lang = pool.get('ir.lang')

        if not execution.filter_values:
            return []

        locale = Transaction().context.get(
            'report_lang', Transaction().language).split('_')[0]
        lang, = Lang.search([
                ('code', '=', locale or 'en'),
                ])

        filter_data = json.loads(execution.filter_values,
            object_hook=JSONDecoder())
        parameters = dict((p.id, p) for p in
            execution.report.filter.parameters)
        res = []
        for key in sorted(filter_data.keys()):
            parameter = parameters[int(key.split('_')[-1:][0])]
            value = filter_data[key]
            if parameter.ttype == 'date':
                value = lang.strftime(value)
            elif parameter.ttype in ('float', 'numeric'):
                value = lang.format('%.2f', value, grouping=True)
            elif parameter.ttype == 'integer':
                value = lang.format('%d', value, grouping=True)
            elif parameter.ttype == 'boolean':
                value = (gettext('babi.msg_true') if value else
                    gettext('babi.msg_false'))
            elif parameter.ttype == 'many2many':
                Model = pool.get(parameter.related_model.model)
                record = []
                if value:
                    record.append(Model(value[0]).rec_name)
                if len(value) > 2:
                    record.append('...')
                if len(value) > 1:
                    record.append(Model(value[-1]).rec_name)
                value = ', '.join(record)
            elif parameter.ttype == 'many2one':
                Model = pool.get(parameter.related_model.model)
                value = Model(value).rec_name

            res.append('%s: %s' % (parameter.name, value))
        return res

    @classmethod
    def execute(cls, ids, data):
        Execution = Pool().get('babi.report.execution')
        context = Transaction().context
        context['report_lang'] = Transaction().language
        context['report_translations'] = os.path.join(
            os.path.dirname(__file__), 'report', 'translations')

        execution_id = data['model_name'].split('_')[-1]
        execution = Execution(execution_id)
        filters = cls.format_filter(execution)
        report = execution.report

        headers = [{
                    'internal_name': d.internal_name,
                    'type': 'dimension',
                    'group_by': d.group_by,
                    'name': d.name,
                    'width': d.width or '',
                    'text-align': 'right' if d.expression.ttype in (
                        'integer', 'float', 'numeric') else 'left',
                    'decimal_digits': d.expression.decimal_digits,
                    } for d in report.dimensions]
        headers += [{
                    'internal_name': m.internal_name,
                    'type': 'measure',
                    'group_by': False,
                    'name': m.name,
                    'width': m.width or '',
                    'text-align': 'right' if m.expression.ttype in (
                        'integer', 'float', 'numeric') else 'left',
                    'decimal_digits': m.expression.decimal_digits,
                    } for m in report.measures]

        with Transaction().set_context(**context):
            records, parameters = cls.prepare(ids, data)

            return super(BabiHTMLReport, cls).execute(data['records'], {
                    'name': 'babi.report.html_report',
                    'filters': filters,
                    'model': data['model_name'],
                    'headers': headers,
                    'report_name': report.rec_name,
                    'records': records,
                    'parameters': parameters,
                    'output_format': 'pdf',
                    'report_options': {
                        'now': datetime.now(),
                        'cell_level': data['cell_level'],
                        }
                    })
