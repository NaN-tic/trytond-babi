# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import fields, dualmethod
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction


class Cron(metaclass=PoolMeta):
    __name__ = "ir.cron"
    babi_report = fields.Many2One('babi.report', 'Babi Report')

    @classmethod
    def __setup__(cls):
        super(Cron, cls).__setup__()
        cls.method.selection.extend([
            ('babi.report|calculate_babi_report', 'Calculate Babi Report'),
            ('babi.report.execution|clean', 'Clean Babi Excutions'),
        ])

    @classmethod
    def default_get(cls, fields, with_rec_name=True):
        User = Pool().get('res.user')
        res = super(Cron, cls).default_get(fields, with_rec_name)
        admin_user, = User.search([('login', '=', 'admin')])
        context = Transaction().context
        if context.get('babi_report', False):
            res['user'] = admin_user.id
            res['interval_type'] = 'days'
            res['repeat_missed'] = False
            res['function'] = 'babi.report|calculate_babi_report'
        return res

    @dualmethod
    def run_once(cls, crons):
        BabiReport = Pool().get('babi.report')

        babi_crons = [cron for cron in crons if cron.babi_report]
        for cron in babi_crons:
            # babi execution require company. Run calculate when has a company
            for company in cron.companies:
                with Transaction().set_context(company=company.id,
                        queue_name='babi'):
                    BabiReport.__queue__.compute(cron.babi_report)
        return super(Cron, cls).run_once(list(set(crons) - set(babi_crons)))
