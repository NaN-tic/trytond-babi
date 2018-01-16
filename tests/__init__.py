# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
try:
    from trytond.modules.babi.tests.test_babi import suite
except ImportError:
    from .test_babi import suite

__all__ = ['suite']
