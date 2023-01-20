# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import fields, dualmethod
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction
from trytond.pyson import Eval


class Cron(metaclass=PoolMeta):
    __name__ = "ir.cron"
    babi_report = fields.Many2One('babi.report', 'Babi Report', states={
            'invisible': Eval('method') != 'babi.report|calculate_babi_report',
            }, depends=['method'])
    babi_table = fields.Many2One('babi.table', 'Babi Table', states={
            'invisible': Eval('method') != 'babi.table|calculate_babi_table',
            }, depends=['method'])

    @classmethod
    def __setup__(cls):
        super(Cron, cls).__setup__()
        cls.method.selection.extend([
                ('babi.report|calculate_babi_report', 'Calculate Babi Report'),
                ('babi.table|calculate_babi_table', 'Calculate Babi Table'),
                ('babi.report.execution|clean', 'Clean Babi Excutions'),
                ])

    @classmethod
    def default_get(cls, fields, with_rec_name=True):
        res = super(Cron, cls).default_get(fields, with_rec_name)
        context = Transaction().context
        if context.get('babi_report'):
            res['interval_type'] = 'days'
            res['interval_number'] = 1
            res['minute'] = 0
            res['hour'] = 5
            res['method'] = 'babi.report|calculate_babi_report'
        if context.get('babi_table'):
            res['interval_type'] = 'days'
            res['interval_number'] = 1
            res['minute'] = 0
            res['hour'] = 5
            res['method'] = 'babi.table|calculate_babi_table'
        return res

    @dualmethod
    def run_once(cls, crons):
        pool = Pool()
        BabiReport = pool.get('babi.report')
        BabiTable = pool.get('babi.table')

        report_crons = [cron for cron in crons if cron.babi_report]
        for cron in report_crons:
            # babi execution require company. Run calculate when has a company
            for company in cron.companies:
                with Transaction().set_context(company=company.id,
                        queue_name='babi'):
                    BabiReport.__queue__.compute(cron.babi_report)

        table_crons = [cron for cron in crons if cron.babi_table]
        for cron in table_crons:
            # babi execution require company. Run calculate when has a company
            for company in cron.companies:
                with Transaction().set_context(company=company.id,
                        queue_name='babi'):
                    BabiTable.__queue__.compute(cron.babi_table)
        return super(Cron, cls).run_once(list(
                set(crons) - set(report_crons) - set(table_crons)))
