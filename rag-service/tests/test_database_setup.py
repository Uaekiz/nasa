from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.parse import unquote, urlsplit

from psycopg.conninfo import conninfo_to_dict

from app.database_setup import application_url, save_local_configuration
from app.rag_config import APP_DATABASE, APP_ROLE, DatabaseSettings, RagError
from app.vector_store import verify_application_identity


class LocalDatabaseConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / '.env'
        environment = patch.dict(os.environ, {'RAG_DATABASE_URL': '', 'RAG_DB_SCHEMA': ''})
        environment.start()
        self.addCleanup(environment.stop)

    def test_uri_uses_psycopg_format_and_round_trips_special_characters(self):
        password = 'synthetic:@/ #?%\u00fc'
        url = application_url(password)
        parsed = urlsplit(url)
        self.assertEqual(parsed.scheme, 'postgresql')
        self.assertEqual(parsed.username, APP_ROLE)
        self.assertEqual(unquote(parsed.password), password)
        self.assertEqual(parsed.path, '/' + APP_DATABASE)
        self.assertEqual(conninfo_to_dict(url)['password'], password)
        self.assertNotIn(password, repr(DatabaseSettings(url)))

    def test_fill_empty_keys_preserves_other_configuration_and_identical_rerun(self):
        self.path.write_text('# Existing local settings\nRAG_DATABASE_URL=\nOLLAMA_MODEL=existing-model\n', encoding='utf-8')
        preserved_line = self.path.read_bytes().splitlines(keepends=True)[2]
        url = application_url('synthetic-test-password')
        self.assertTrue(save_local_configuration(url, self.path))
        before = self.path.read_bytes()
        self.assertIn(preserved_line, before)
        self.assertIn('RAG_DB_SCHEMA=rag', before.decode('utf-8').splitlines())
        self.assertFalse(save_local_configuration(url, self.path))
        self.assertEqual(self.path.read_bytes(), before)

    def test_existing_connection_is_never_overwritten_or_printed_in_an_error(self):
        self.path.write_text('RAG_DATABASE_URL=postgresql://existing:synthetic-private@host/other\n', encoding='utf-8')
        before = self.path.read_bytes()
        with self.assertRaises(RagError) as caught:
            save_local_configuration(application_url('new-synthetic-password'), self.path)
        self.assertEqual(caught.exception.code, 'CONFIGURATION_CONFLICT')
        self.assertNotIn('synthetic-private', str(caught.exception))
        self.assertNotIn('new-synthetic-password', str(caught.exception))
        self.assertEqual(self.path.read_bytes(), before)

    def test_conflicting_process_environment_is_preserved(self):
        with patch.dict(os.environ, {'RAG_DATABASE_URL': 'postgresql://other'}):
            with self.assertRaises(RagError):
                save_local_configuration(application_url('synthetic'), self.path)
        self.assertFalse(self.path.exists())

    def test_duplicate_configuration_keys_are_rejected_without_rewriting_them(self):
        self.path.write_text('RAG_DATABASE_URL=\nRAG_DATABASE_URL=\n', encoding='utf-8')
        before = self.path.read_bytes()
        with self.assertRaises(RagError) as caught:
            save_local_configuration(application_url('synthetic'), self.path)
        self.assertEqual(caught.exception.code, 'CONFIGURATION_CONFLICT')
        self.assertEqual(self.path.read_bytes(), before)

    def test_requested_rag_schema_is_supported_and_unsafe_schemas_remain_rejected(self):
        self.assertEqual(DatabaseSettings('postgresql://example').schema, 'rag')
        for schema in ('public', 'pg_catalog', 'rag;DROP SCHEMA public'):
            with self.subTest(schema=schema), self.assertRaises(RagError):
                DatabaseSettings('postgresql://example', schema)


class ApplicationIdentityTests(unittest.TestCase):
    def connection(self, **changes):
        identity = {
            'database': APP_DATABASE, 'role': APP_ROLE, 'session_role': APP_ROLE,
            'rolsuper': False, 'rolcreatedb': False, 'rolcreaterole': False,
            'rolreplication': False, 'rolbypassrls': False,
        }
        identity.update(changes)
        connection = Mock()
        connection.execute.return_value.fetchone.return_value = identity
        return connection

    def test_normal_connection_requires_the_application_role_and_target_database(self):
        verify_application_identity(self.connection())
        for changes, code in (
            ({'role': 'postgres', 'session_role': 'postgres'}, 'APPLICATION_ROLE_REQUIRED'),
            ({'database': 'postgres'}, 'WRONG_DATABASE'),
            ({'rolsuper': True}, 'APPLICATION_ROLE_PRIVILEGES'),
        ):
            with self.subTest(changes=changes), self.assertRaises(RagError) as caught:
                verify_application_identity(self.connection(**changes))
            self.assertEqual(caught.exception.code, code)
