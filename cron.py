# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import fields, dualmethod
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction
from trytond.pyson import Eval
from .babi import QUEUE_NAME


class Cron(metaclass=PoolMeta):
    __name__ = "ir.cron"
    babi_report = fields.Many2One('babi.report', 'Babi Report', states={
            'invisible': Eval('method') != 'babi.report|calculate_babi_report',
            })
    babi_table = fields.Many2One('babi.table', 'Babi Table', states={
            'invisible': Eval('method') != 'babi.table|calculate_babi_table',
            })
    babi_calculate_warnings = fields.Boolean('Calculate Warnings', states={
        'invisible': Eval('method') != 'babi.table|calculate_babi_table',
            })

    @classmethod
    def __register__(cls, module_name):
        cursor = Transaction().connection.cursor()
        babi = cls.__table__()

        super().__register__(module_name)
        cursor.execute(*babi.update(
                [babi.method], ['babi.report|calculate_babi_report'],
                where=(babi.method == 'babi.report|calculate_reports')
                ))

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
                        queue_name=QUEUE_NAME):
                    BabiReport.__queue__.compute(cron.babi_report)

        table_crons = [cron for cron in crons if cron.babi_table]
        for cron in table_crons:
            # babi execution require company. Run calculate when has a company
            for company in cron.companies:
                with Transaction().set_context(company=company.id,
                        queue_name='babi'):
                    if cron.babi_table.type == 'query':
                        BabiTable.__queue__.compute_warnings(cron.babi_table)
                    else:
                        BabiTable.__queue__._compute(cron.babi_table,
                            create_warnings=cron.babi_calculate_warnings)
        return super(Cron, cls).run_once(list(
                set(crons) - set(report_crons) - set(table_crons)))

    @fields.depends('method')
    def on_change_with_babi_calculate_warnings(self, name=None):
        if self.method != 'babi.table|calculate_babi_table':
            return False
        return self.babi_calculate_warnings
