# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from . import configuration
from . import cron
from . import babi
from . import test_model
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
        babi.Model,
        cron.Cron,
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
        table.TableQueryParameter,
        table.TableTag,
        table.TableTagRelation,
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
        pivot.IndexNull,
        pivot.PivotHeaderAxis,
        pivot.PivotHeaderMeasure,
        pivot.PivotHeaderOrder,
        pivot.PivotHeaderSelection,
        pivot.PivotHeaderSelectionCloseField,
        pivot.PivotHeaderSelectionAddField,
        pivot.PivotHeaderRemoveField,
        pivot.PivotHeaderLevelField,
        pivot.PivotSidebarTables,
        pivot.PivotCompute,
        pivot.PivotApply,
        pivot.PivotSave,
        pivot.PivotTable,
        pivot.DownloadReport,
        module='babi', type_='model')
    Pool.register(
        table.ParametrizeTable,
        module='babi', type_='wizard')
    Pool.register(
        table.TableExcel,
        table.PivotExcel,
        table.WarningExcel,
        table.WarningPivotExcel,
        module='babi', type_='report')
