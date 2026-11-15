from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest

from elevated_activity import CodexActivity, unique_match
from kitty_bridge import filtered_windows
from kitty_tabs import match_terminal


class CorrelationTests(unittest.TestCase):
    def test_only_unique_latest_substantial_text_can_bind(self):
        a = 'Distinct assistant progress for the first conversation. '*5
        b = 'Different assistant progress for the second conversation. '*5
        self.assertEqual(unique_match(a, {'a':[a], 'b':[b]}), 'a')
        self.assertEqual(unique_match(a+b, {'a':[a], 'b':[b]}), 'b')
        self.assertIsNone(unique_match(a, {'a':[a], 'b':[a]}))
        self.assertIsNone(unique_match('Done', {'a':['Done']}))
        self.assertIsNone(unique_match(a+'unmatched new message '*20, {'a':[a]}))

    def test_real_log_and_rollout_formats_lifecycle_pid_reuse_and_redaction(self):
        with tempfile.TemporaryDirectory() as folder:
            home=Path(folder); (home/'sessions').mkdir(); path=home/'sessions/one.jsonl'
            prose='A distinct assistant progress message used to correlate this live terminal with its conversation. '*3
            def event(kind, payload):
                return json.dumps({'timestamp':'2026-11-15T12:00:00Z','type':kind,'payload':payload})+'\n'
            path.write_text(event('event_msg',{'type':'task_started','turn_id':'turn1'})+
                event('response_item',{'type':'message','role':'assistant','content':[{'type':'output_text','text':prose}]}))
            with closing(sqlite3.connect(home/'state_5.sqlite')) as db:
                db.execute('create table threads(id,rollout_path,name,title,cwd,archived,attached_thread_parent_id,updated_at)')
                db.execute('insert into threads values(?,?,?,?,?,0,NULL,1)',('one',str(path),'','password secret-value','/project'))
                db.commit()
            with closing(sqlite3.connect(home/'logs_2.sqlite')) as db:
                db.execute('create table logs(id integer primary key, feedback_log_body,process_uuid,thread_id,ts,target)')
                db.execute('insert into logs values(1,?,?,NULL,100,?)',('push_delta: '+json.dumps(prose),'pid:20:unique','codex_tui::markdown_stream'))
                db.commit()
            record={'pid':20,'created_at':99,'provider':'codex'}; reader=CodexActivity(home)
            reader.enrich([record]); self.assertEqual(record['chat']['state'],'working')
            self.assertNotIn('secret-value',record['chat']['title'])
            with path.open('a') as f:f.write(event('event_msg',{'type':'task_complete','turn_id':'turn1'}))
            reader.enrich([record]); self.assertEqual(record['chat']['state'],'sleeping')
            reused={'pid':20,'created_at':101,'provider':'codex'}
            reader.enrich([reused]); self.assertNotIn('chat',reused)


class KittyTests(unittest.TestCase):
    def test_snapshot_removes_commands_environment_and_titles(self):
        tree=[{'id':1,'tabs':[{'id':2,'is_active':True,'windows':[{'id':3,'pid':42,
            'is_active':True,'env':{'SECRET':'hidden'},'cmdline':['secret'],'title':'private'}]}]}]
        rows=filtered_windows(tree,99)
        self.assertEqual(rows,[{'id':3,'tab':2,'os_window':1,'pid':42,'terminal_pid':99,'selected':True}])

    def test_exact_ancestry_and_ambiguous_windows(self):
        pane={'id':3,'tab':2,'os_window':1,'pid':42,'terminal_pid':99,'selected':True}
        client={'shell_pid':42,'terminal_pid':99}
        window=SimpleNamespace(pid=99,hwnd=8,executable='kitty')
        self.assertEqual(match_terminal(client,[window],[pane])['tab_id'],'kitty:3')
        self.assertFalse(match_terminal(dict(client,shell_pid=43),[window],[pane]))
        self.assertFalse(match_terminal(client,[window,window],[pane]))
        self.assertFalse(match_terminal(client,[window],[pane,dict(pane,id=4,os_window=2,pid=43)]))

if __name__ == '__main__':unittest.main()
