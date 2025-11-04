from trytond.transaction import Transaction
from trytond.pool import Pool, PoolMeta


class Rule(metaclass=PoolMeta):
    __name__ = 'ir.rule'

    @classmethod
    def _get_context(cls, model_name):
        pool = Pool()
        User = pool.get('res.user')
        context = super()._get_context(model_name)
        if model_name == 'babi.warning':
            context['employees'] = User.get_employees()
        if model_name in ('babi.warning', 'babi.table'):
            context['user_id'] = Transaction().user
        return context

    @classmethod
    def _get_cache_key(cls, model_name):
        pool = Pool()
        User = pool.get('res.user')
        key = super()._get_cache_key(model_name)
        if model_name & {'babi.warning'}:
            key = (*key, User.get_employees(), Transaction().user)
        return key
