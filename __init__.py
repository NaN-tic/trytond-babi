# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from . import configuration
from . import cron
from . import babi
from . import test_model
from . import report

def register():
    Pool.register(
        configuration.Configuration,
        babi.Filter,
        babi.FilterParameter,
        babi.Expression,
        babi.Report,
        babi.ReportExecution,
        babi.ReportGroup,
        babi.Dimension,
        babi.DimensionColumn,
        babi.Measure,
        babi.InternalMeasure,
        babi.Order,
        babi.ActWindow,
        babi.Menu,
        babi.Keyword,
        babi.Model,
        cron.Cron,
        babi.OpenChartStart,
        babi.OpenExecutionSelect,
        babi.UpdateDataWizardStart,
        babi.UpdateDataWizardUpdated,
        babi.CleanExecutionsStart,
        test_model.TestBabiModel,
        module='babi', type_='model')
    Pool.register(
        babi.OpenChart,
        babi.OpenExecution,
        babi.CleanExecutions,
        module='babi', type_='wizard')
    Pool.register(
        report.BabiHTMLReport,
        module='babi', type_='report')
