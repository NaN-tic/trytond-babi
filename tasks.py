# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from trytond.transaction import Transaction


def calculate_execution(execution_id, user_id=None):
    'Calculates exectuion data passed by parameters'
    pool = Pool()
    User = pool.get('res.user')
    Execution = pool.get('babi.report.execution')

    if not user_id:
        user, = User.search([
                ('login', '=', 'admin'),
                ])
        user_id = user.id

    with Transaction().set_user(user_id), Transaction().set_context(
            User.get_preferences(context_only=True)):
        execution = Execution(execution_id)
        Execution.calculate([execution])
