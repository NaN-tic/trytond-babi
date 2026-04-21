from datetime import datetime, timedelta
import secrets

from lxml import etree
from trytond.pool import PoolMeta, Pool
from trytond.model import fields, ModelSQL, ModelView
from trytond.ir.action import ActionMixin
from trytond.transaction import Transaction
from trytond.wizard import StateAction, Wizard


class _ChartValidator:
    def __init__(self, validator):
        self._validator = validator

    def _prepare_tree(self, tree):
        tree = etree.fromstring(etree.tostring(tree))
        for field in tree.xpath('.//field[@widget="chart"]'):
            field.set('widget', 'text')
        return tree

    def validate(self, tree):
        return self._validator.validate(self._prepare_tree(tree))

    def assertValid(self, tree):
        return self._validator.assertValid(self._prepare_tree(tree))

    @property
    def error_log(self):
        return self._validator.error_log


class View(metaclass=PoolMeta):
    __name__ = 'ir.ui.view'

    @classmethod
    def _validator(cls, type_):
        validator = super()._validator(type_)
        if type_ in {'form', 'list-form'}:
            validator = _ChartValidator(validator)
            key = (cls.__name__, type_)
            validator = cls._get_validator_cache.set(key, validator)
        return validator


class Action(metaclass=PoolMeta):
    __name__ = 'ir.action'

    @classmethod
    def get_action_values(cls, type_, action_ids, columns=None):
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


class VoyagerOpenSession(ModelSQL, ModelView):
    'Babi Voyager Open Session'
    __name__ = 'babi.voyager.open_session'

    token = fields.Char('Token', required=True)
    user = fields.Many2One('res.user', 'User', required=True,
        ondelete='CASCADE')
    expiration_date = fields.DateTime('Expiration Date', required=True)


class OpenVoyager(Wizard):
    'Open Babi Voyager'
    __name__ = 'babi.open_voyager'
    start_state = 'open_voyager'

    open_voyager = StateAction('babi.act_babi_voyager_url')

    def do_open_voyager(self, action):
        pool = Pool()
        OpenSession = pool.get('babi.voyager.open_session')

        database = Transaction().database.name
        session, = OpenSession.create([{
                    'token': secrets.token_urlsafe(32),
                    'user': Transaction().user,
                    'expiration_date': datetime.now() + timedelta(minutes=5),
                    }])
        action['url'] = f'/{database}/babi/voyager-login/{session.token}'
        return action, {}

    @classmethod
    def transition_open_voyager(cls):
        return 'end'


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
