from lxml import etree
from trytond.pool import PoolMeta, Pool
from trytond.model import fields, ModelSQL, ModelView
from trytond.ir.action import ActionMixin


class View(metaclass=PoolMeta):
    __name__ = 'ir.ui.view'

    @classmethod
    def get_rng(cls, type_):
        rng = super().get_rng(type_)
        if type_ in ('form', 'list-form'):
            widgets = rng.xpath(
                '//ns:define/ns:optional/ns:attribute'
                '/ns:name[.="widget"]/following-sibling::ns:choice',
                namespaces={'ns': 'http://relaxng.org/ns/structure/1.0'})[0]
            subelem = etree.SubElement(widgets,
                '{http://relaxng.org/ns/structure/1.0}value')
            subelem.text = 'chart'
        return rng


class Action(metaclass=PoolMeta):
    __name__ = 'ir.action'

    @classmethod
    def get_action_values(self, type_, action_ids, columns=None):
        pool = Pool()
        ActionDashboard = pool.get('babi.action.dashboard')

        actions = super().get_action_values(type_, action_ids, columns)
        if type_ == 'babi.action.dashboard':
            boards = {x.id: x for x in ActionDashboard.browse(action_ids)}
            for values in actions:
                values['dashboard'] = boards[values['id']].dashboard.id
        return actions


class ActionDashboard(ActionMixin, ModelSQL, ModelView):
    "Action Act Dashboard"
    __name__ = 'babi.action.dashboard'
    dashboard = fields.Many2One('babi.dashboard', 'Dashboard', required=True,
        ondelete='CASCADE')
    action = fields.Many2One('ir.action', 'Action', ondelete='CASCADE')

    @staticmethod
    def default_type():
        return 'babi.action.dashboard'


class Menu(metaclass=PoolMeta):
    __name__ = 'ir.ui.menu'

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls.action.selection.append(('babi.action.dashboard', 'Dashboard'))

    @classmethod
    def _get_action(cls, action_id):
        pool = Pool()
        Action = pool.get('ir.action')
        action = Action(action_id)
        if action.type == 'babi.action.dashboard':
            action = ActionDashboard(action_id)
        return super()._get_action(action)