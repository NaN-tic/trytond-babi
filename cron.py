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
            'invisible': Eval('method') != 'babi.report|compute',
            'required': Eval('method') == 'babi.report|compute',
            }, ondelete='CASCADE')
    babi_table = fields.Many2One('babi.table', 'Table', states={
            'invisible': Eval('method') != 'babi.table|_compute',
            'required': Eval('method') == 'babi.table|_compute',
            }, ondelete='CASCADE')
    babi_cluster = fields.Many2One('babi.table.cluster', 'Cluster', states={
            'invisible': Eval('method') != 'babi.table.cluster|_compute',
            'required': Eval('method') == 'babi.table.cluster|_compute',
            })
    babi_compute_warnings = fields.Boolean('Compute Warnings', states={
            'invisible': ~Eval('method').in_(['babi.table|_compute',
                    'babi.table.cluster|_compute']),
            })

    @classmethod
    def __register__(cls, module_name):
        cursor = Transaction().connection.cursor()
        babi = cls.__table__()
        handler = cls.__table_handler__(module_name)

        # Tryton 7.2: Rename babi_calculate_warnings to babi_compute_warnings
        if (handler.column_exist('babi_calculate_warnings')
                and not handler.column_exist('babi_compute_warnings')):
            handler.column_rename(
                'babi_calculate_warnings', 'babi_compute_warnings')
        super().__register__(module_name)
        cursor.execute(*babi.update(
                [babi.method], ['babi.report|calculate_babi_report'],
                where=(babi.method == 'babi.report|calculate_reports')
                ))
        cursor.execute(*babi.update(
                [babi.method], ['babi.report|compute'],
                where=(babi.method == 'babi.report|calculate_babi_report')
                ))
        cursor.execute(*babi.update(
                [babi.method], ['babi.table|compute'],
                where=(babi.method == 'babi.tablel|calculate_babi_table')
                ))
        cursor.execute(*babi.update(
                [babi.method], ['babi.table|_compute'],
                where=(babi.method == 'babi.table|compute')
                ))

    @classmethod
    def __setup__(cls):
        super(Cron, cls).__setup__()
        cls.method.selection.extend([
                ('babi.report|compute', 'Compute Business Intelligence Report'),
                ('babi.table|_compute', 'Compute Business Intelligence Table'),
                ('babi.table|clean', 'Delete Tables with Parameters'),
                ('babi.table.cluster|compute',
                    'Compute Business Intelligence Cluster'),
                ('babi.report.execution|clean', 'Clean Babi Executions'),
                ])

    @classmethod
    def default_get(cls, fields, with_rec_name=True):
        res = super(Cron, cls).default_get(fields, with_rec_name)
        context = Transaction().context
        res['interval_type'] = 'days'
        res['interval_number'] = 1
        res['minute'] = 0
        res['hour'] = 5
        if context.get('babi_report'):
            res['method'] = 'babi.report|compute'
        if context.get('babi_table'):
            res['method'] = 'babi.table|_compute'
        if context.get('babi_cluster'):
            res['method'] = 'babi.table.cluster|compute'
        return res

    @dualmethod
    def run_once(cls, crons):
        pool = Pool()
        Report = pool.get('babi.report')
        Table = pool.get('babi.table')
        Cluster = pool.get('babi.table.cluster')

        report_crons = [cron for cron in crons if cron.babi_report]
        for cron in report_crons:
            # babi execution require company. Run compute when has a company
            for company in cron.companies:
                with Transaction().set_context(company=company.id,
                        queue_name=QUEUE_NAME):
                    Report.__queue__._compute(cron.babi_report)

        table_crons = [cron for cron in crons if cron.babi_table]
        for cron in table_crons:
            # babi execution require company. Run compute when has a company
            for company in cron.companies:
                with Transaction().set_context(company=company.id,
                        queue_name=QUEUE_NAME):
                    Table.__queue__._compute(cron.babi_table,
                        compute_warnings=cron.babi_compute_warnings)

        cluster_crons = [cron for cron in crons if cron.babi_cluster]
        for cron in cluster_crons:
            # babi execution require company. Run compute when has a company
            for company in cron.companies:
                with Transaction().set_context(company=company.id,
                        queue_name=QUEUE_NAME):
                    Cluster.__queue__._compute(cron.babi_cluster,
                        compute_warnings=cron.babi_compute_warnings)
        return super().run_once(list(
                set(crons) - set(report_crons) - set(table_crons)
                - set(cluster_crons)))

    @fields.depends('method')
    def on_change_with_babi_compute_warnings(self, name=None):
        if self.method not in ('babi.table|_compute',
                'babi.table.cluster|_compute'):
            return False
        return self.babi_compute_warnings
