from trytond.pool import PoolMeta


class ModelAccess(metaclass=PoolMeta):
    __name__ = 'ir.model.access'

    @classmethod
    def get_access(cls, models):
        # remove models that start babi_execution_
        models = [model for model in models
            if not model.startswith('babi_execution_')]
        return super().get_access(models)
