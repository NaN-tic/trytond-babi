# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import PoolMeta

__all__ = ['ReportTranslationSet']


class ReportTranslationSet:
    __metaclass__ = PoolMeta
    __name__ = "ir.translation.set"

    def extract_report_jinja(self, content):
        # TODO
        return []
