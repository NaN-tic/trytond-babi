# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from . import configuration
from . import cron
from . import babi
from . import test_model
from . import report
from . import table
from . import dashboard
from . import action
from . import ir
from . import pivot
from . import routes

__all__ = ['register', 'routes']

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
        dashboard.Dashboard,
        dashboard.DashboardItem,
        dashboard.Widget,
        dashboard.WidgetParameter,
        action.View,
        action.Action,
        action.ActionDashboard,
        action.Menu,
        test_model.TestBabiModel,
        table.TableUser,
        table.TableGroup,
        table.TableParameters,
        table.Cluster,
        table.Table,
        table.Field,
        table.TableDependency,
        table.Warning,
        ir.Rule,
        table.Pivot,
        table.RowDimension,
        table.ColumnDimension,
        table.Measure,
        table.Property,
        table.Order,
        pivot.Site,
        pivot.Layout,
        pivot.Index,
        pivot.PivotHeader,
        pivot.PivotHeaderAxis,
        pivot.PivotHeaderMeasure,
        pivot.PivotHeaderOrder,
        pivot.PivotHeaderSelection,
        pivot.PivotTable,
        pivot.DownloadReport,
        pivot.SavePivot,
        pivot.SaveSelectedPivot,
        pivot.PivotSaveModal,
        pivot.PivotRedirect,
        pivot.PivotSelectRedirect,
        pivot.ParametrizePivotTable,
        pivot.ComputeTable,
        pivot.FlashClear,
        pivot.UpdatePivotTitle,
        module='babi', type_='model')
    Pool.register(
        babi.OpenChart,
        babi.OpenExecution,
        babi.CleanExecutions,
        table.ParametrizeTable,
        module='babi', type_='wizard')
    Pool.register(
        report.BabiHTMLReport,
        table.TableExcel,
        table.PivotExcel,
        table.WarningExcel,
        table.WarningPivotExcel,
        module='babi', type_='report')
