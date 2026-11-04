import sys
import unittest
import tempfile
import os
from unittest.mock import Mock

from group_menu import GroupMenu, HistoryPicker, team_status
from agent_sounds import Sounds


def menu_index(menu, label):
    return next(index for index in range(menu.index('end') + 1)
                if menu.type(index) != 'separator' and menu.entrycget(index, 'label') == label)


class TeamStatusTests(unittest.TestCase):
    def test_hidden_sessions_still_count_but_tool_waits_and_stale_errors_are_not_attention(self):
        entries = {
            'wait': {'state':'working','chat':{'activity':{'phase':'Esperando una herramienta'}}},
            'ask': {'state':'working','chat':{'activity':{'phase':'Esperando intervención'}}},
            'old': {'state':'sleeping','chat':{'activity':{'actions':[{'outcome':'error'}]}}},
            'stale': {'state':'working','unavailable':True,'chat':{'activity':{'actions':[{'outcome':'error'}]}}},
        }
        self.assertEqual(team_status(entries, excluded={'ask','old'}),
                         dict(total=4,working=2,resting=1,unknown=1,attention=1,visible=2))
        self.assertEqual(team_status(entries, hidden=True)['visible'], 0)
        self.assertEqual(team_status({})['total'], 0)


@unittest.skipUnless(sys.platform in ('win32','darwin') or os.environ.get('DISPLAY'), 'Native desktop display')
class GroupMenuTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        self.root.destroy()

    def test_visibility_labels_and_individual_controls_remain_accessible(self):
        hidden = [False]
        excluded = set()
        entries = {'a': {'chat_title': 'Example', 'chat': {'provider': 'claude'}}}
        details = Mock()
        def toggle(): hidden[0] = not hidden[0]
        def toggle_one(key): excluded.add(key) if key not in excluded else excluded.remove(key)
        menu = GroupMenu(self.root, details, entries, lambda: hidden[0], lambda: excluded,
                         toggle, toggle_one, Mock(), Mock())
        event = Mock(x_root=100, y_root=100)
        menu.popup(event)
        menu.menu.invoke(menu_index(menu.menu, 'Ocultar avatares'))
        menu.popup(event)
        self.assertIsNotNone(menu_index(menu.menu, 'Mostrar avatares'))
        self.assertEqual(menu.window.winfo_exists(), 1)
        menu.avatar_menu.invoke(0)
        self.assertEqual(excluded, {'a'})
        menu.popup(event)
        self.assertFalse(menu.variables[0].get())
        menu.menu.invoke(menu_index(menu.menu, 'Mostrar avatares'))
        self.assertFalse(hidden[0])
        self.assertEqual(excluded, {'a'})
        self.assertEqual(details.popup_menu.call_count, 3)

    def test_group_controls_are_available_even_with_no_avatars(self):
        quiet, shutdown, place, show_all = Mock(), Mock(), Mock(), Mock()
        menu = GroupMenu(self.root, Mock(), {}, lambda: False, set, Mock(), Mock(), Mock(), Mock(),
                         show_all=show_all,set_quiet=quiet,place_group=place,shutdown=shutdown)
        menu.popup(Mock(x_root=100,y_root=100))
        self.assertEqual(menu.menu.entrycget(menu_index(menu.menu,'Mostrar todos los avatares'),'state'),'disabled')
        menu.menu.invoke(menu_index(menu.menu,'Modo tranquilo'))
        quiet.assert_called_once_with(True)
        menu.placement_menu.invoke(menu_index(menu.placement_menu,'Arriba centro'))
        place.assert_called_once_with('top')
        menu.menu.invoke(menu_index(menu.menu,'Apagar Agentlings'))
        shutdown.assert_called_once_with()

    def test_reveal_all_is_distinct_from_global_visibility_toggle(self):
        entries = {'a':{'state':'working','chat_title':'Example','chat':{}}}
        excluded = {'a'}
        toggle = Mock()
        menu = GroupMenu(self.root,Mock(),entries,lambda:False,lambda:excluded,toggle,Mock(),Mock(),Mock(),
                         show_all=excluded.clear)
        menu.popup(Mock(x_root=100,y_root=100))
        menu.menu.invoke(menu_index(menu.menu,'Mostrar todos los avatares'))
        self.assertEqual(excluded,set())
        toggle.assert_not_called()
        menu.popup(Mock(x_root=100,y_root=100))
        self.assertEqual(menu.summary['visible'],1)
        self.assertEqual(menu.menu.entrycget(menu_index(menu.menu,'Mostrar todos los avatares'),'state'),'disabled')

    def test_indicator_clears_error_after_recovery_and_ignores_unavailable_state(self):
        entry = {'state':'working','chat_title':'Example','chat':{'activity':{'actions':[{'outcome':'error'}]}}}
        menu = GroupMenu(self.root,Mock(),{'a':entry},lambda:False,set,Mock(),Mock(),Mock(),Mock())
        menu.refresh_indicator()
        self.assertEqual(menu.summary['attention'],1)
        self.assertEqual(menu.canvas.itemcget(menu.outline,'outline'),'#f0bd75')
        entry['chat']['activity']['actions'][0]['outcome'] = 'success'
        menu.refresh_indicator()
        self.assertEqual(menu.summary['attention'],0)
        self.assertEqual(menu.canvas.itemcget(menu.outline,'outline'),'#77e4c8')
        entry['unavailable'] = True
        menu.refresh_indicator()
        self.assertEqual(menu.summary['unknown'],1)
        self.assertEqual(menu.canvas.itemcget(menu.outline,'outline'),'#869bb2')

    def test_history_filter_excludes_existing_and_show_requires_explicit_selection(self):
        selected = Mock()
        picker = HistoryPicker(self.root, Mock(), selected, lambda: {'current'})
        record = {'id': 'old', 'provider': 'claude', 'title': 'Build verification', 'updated_at': 100}
        picker.results.put(([record, dict(record, id='current')], []))
        picker.poll()
        self.assertEqual(picker.tree.get_children(), ('old',))
        selected.assert_not_called()
        picker.query.set('codex')
        self.assertFalse(picker.tree.get_children())
        picker.query.set('verification')
        picker.tree.selection_set('old')
        picker.choose()
        selected.assert_called_once_with(record)
        self.assertEqual(picker.window.state(), 'withdrawn')

    def test_history_preserves_selection_explains_empty_search_and_blocks_stale_choice(self):
        current = set()
        selected = Mock()
        picker = HistoryPicker(self.root,Mock(),selected,lambda:current)
        record = {'id':'old','provider':'claude','title':'Build verification','updated_at':100}
        picker.results.put(([record],['Historial parcialmente disponible.']))
        picker.poll()
        picker.focus_results()
        picker.query.set('  verification  ')
        self.assertEqual(picker.tree.selection(),('old',))
        self.assertIn('parcialmente',picker.message.get())
        picker.loading = True
        picker.sync_buttons()
        picker.choose()
        selected.assert_not_called()
        self.assertTrue(picker.choose_button.instate(['disabled']))
        picker.loading = False
        picker.query.set('no matches')
        self.assertIn('Sin coincidencias',picker.message.get())
        self.assertTrue(picker.choose_button.instate(['disabled']))
        picker.query.set('')
        picker.focus_results()
        current.add('old')
        picker.choose()
        selected.assert_not_called()
        self.assertFalse(picker.tree.get_children())
        self.assertIn('No hay sesiones',picker.message.get())

    def test_sound_menu_controls_persist_and_quiet_disables_preview(self):
        with tempfile.TemporaryDirectory() as directory:
            player = Mock()
            sounds = Sounds(directory, player=player)
            quiet = [False]
            group = GroupMenu(self.root, Mock(), {}, lambda: False, set,
                              Mock(), Mock(), Mock(), Mock(), sounds, lambda: quiet[0])
            event = Mock(x_root=100, y_root=100)
            group.popup(event)
            self.assertEqual(group.menu.entrycget('end', 'label'), 'Sonidos')
            menu = group.sound_menu
            menu.menu.invoke(5)
            self.assertEqual(Sounds(directory, player=player).volume, 50)
            menu.menu.invoke(0)
            self.assertFalse(Sounds(directory, player=player).enabled)
            group.popup(event)
            self.assertEqual(menu.menu.entrycget(9, 'state'), 'disabled')
            menu.menu.invoke(0)
            group.popup(event)
            menu.menu.invoke(9)
            self.assertIsNotNone(player.call_args.args[0])
            quiet[0] = True
            group.popup(event)
            self.assertEqual(menu.menu.entrycget(9, 'state'), 'disabled')
            self.assertEqual(menu.menu.entrycget('end', 'label'), 'Pausados por modo tranquilo')


if __name__ == '__main__':
    unittest.main()
