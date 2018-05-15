# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from . import action
from . import configuration
from . import cron
from . import babi
from . import translation
from . import test_model


def register():
    Pool.register(
        action.ActionReport,
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
        translation.ReportTranslationSet,
        module='babi', type_='wizard')
    Pool.register(
        babi.BabiHTMLReport,
        module='babi', type_='report')
