import os
import tempfile
import unittest


DB_FILE = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
DB_FILE.close()
os.environ['DATABASE_URL'] = f'sqlite:///{DB_FILE.name}'
os.environ.pop('GROQ_API_KEY', None)

from backend.main import AdvanceRequest, ChatRequest, advance_simulation, chat, engine, is_explicit_approval
from sqlalchemy import text


class AgentTests(unittest.TestCase):
    seller_id = 'SEL-10482'

    def setUp(self):
        with engine.begin() as connection:
            connection.execute(text('DELETE FROM conversations'))
            connection.execute(text('DELETE FROM actions'))
            connection.execute(text('DELETE FROM approvals'))

    def test_approval_is_word_bounded_and_rejects_negation(self):
        self.assertTrue(is_explicit_approval('yes, do it'))
        self.assertTrue(is_explicit_approval('haan, kar do'))
        self.assertFalse(is_explicit_approval('I sold 5 kurtas yesterday'))
        self.assertFalse(is_explicit_approval("don't do it"))

    def test_trace_proposal_and_conversation_are_grounded(self):
        first = chat(ChatRequest(seller_id=self.seller_id, message='Please diagnose the sales drop.', history=[{'role': 'user', 'content': 'context'}]))
        self.assertGreaterEqual(len(first['trace']), 5)
        self.assertTrue(all(item['args'] is not None and item['result_summary'] for item in first['trace']))
        second = chat(ChatRequest(seller_id=self.seller_id, message='Please diagnose the sales drop.', history=[{'role': 'assistant', 'content': first['response']}]))
        proposals = [action for action in second['actions'] if action['status'] == 'proposed']
        self.assertEqual(len(proposals), 1)
        with engine.begin() as connection:
            assistant_count = connection.execute(text("SELECT COUNT(*) FROM conversations WHERE seller_id = :seller_id AND role = 'assistant'"), {'seller_id': self.seller_id}).scalar()
        self.assertEqual(assistant_count, 2)

    def test_advance_is_idempotent(self):
        chat(ChatRequest(seller_id=self.seller_id, message='Please diagnose the drop.', history=[{'role': 'user', 'content': 'context'}]))
        chat(ChatRequest(seller_id=self.seller_id, message='yes, do it', history=[]))
        first = advance_simulation(AdvanceRequest(seller_id=self.seller_id, days=3))
        second = advance_simulation(AdvanceRequest(seller_id=self.seller_id, days=3))
        self.assertEqual(first, second)


if __name__ == '__main__':
    unittest.main()
