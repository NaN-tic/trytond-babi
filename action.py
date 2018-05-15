# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import PoolMeta

__all__ = ['ActionReport']


class ActionReport:
    __metaclass__ = PoolMeta
    __name__ = 'ir.action.report'

    @classmethod
    def __setup__(cls):
        super(ActionReport, cls).__setup__()

        jinja_option = ('jinja', 'Jinja')
        if not jinja_option in cls.template_extension.selection:
            cls.template_extension.selection.append(jinja_option)
