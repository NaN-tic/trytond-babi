# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import ModelSQL, ModelView, fields, ModelSingleton

__all__ = ['Configuration']


class Configuration(ModelSingleton, ModelSQL, ModelView):
    'Business Intelligence Configuration'
    __name__ = 'babi.configuration'
    default_timeout = fields.Integer('Timeout (s)')
    report_cell_level = fields.Integer('Cell Level',
        help='Start cell level that not has indentation')
