"""Add versioned document corpora, chunks and exact pgvector retrieval."""

from alembic import op

revision = "0005_retrieval"
down_revision = "0004_analytics"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE corpus_versions (
            id uuid PRIMARY KEY,
            corpus_name text NOT NULL CHECK (btrim(corpus_name) <> ''),
            version integer NOT NULL CHECK (version > 0),
            evidence_kind text NOT NULL CHECK (
                evidence_kind IN ('development-fixture', 'approved')
            ),
            manifest_sha256 catalog_sha256 NOT NULL,
            manifest jsonb NOT NULL CHECK (jsonb_typeof(manifest) = 'object'),
            chunk_config_sha256 catalog_sha256 NOT NULL,
            chunk_config jsonb NOT NULL CHECK (jsonb_typeof(chunk_config) = 'object'),
            status text NOT NULL DEFAULT 'pending' CHECK (
                status IN ('pending', 'indexing', 'ready', 'failed')
            ),
            expected_documents integer NOT NULL CHECK (expected_documents > 0),
            expected_chunks integer NOT NULL CHECK (expected_chunks >= 0),
            started_at timestamptz,
            finished_at timestamptz,
            last_error text,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (corpus_name, version),
            UNIQUE (manifest_sha256),
            UNIQUE (id, expected_documents, expected_chunks)
        )
    """)
    op.execute("""
        CREATE TABLE corpus_documents (
            id uuid PRIMARY KEY,
            corpus_version_id uuid NOT NULL REFERENCES corpus_versions(id),
            document_key text NOT NULL CHECK (btrim(document_key) <> ''),
            document_version text NOT NULL CHECK (btrim(document_version) <> ''),
            title text NOT NULL CHECK (btrim(title) <> ''),
            source_location text NOT NULL CHECK (btrim(source_location) <> ''),
            content_sha256 catalog_sha256 NOT NULL,
            byte_count bigint NOT NULL CHECK (byte_count > 0),
            media_type text NOT NULL CHECK (btrim(media_type) <> ''),
            metadata jsonb NOT NULL CHECK (jsonb_typeof(metadata) = 'object'),
            ordinal integer NOT NULL CHECK (ordinal >= 0),
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (corpus_version_id, document_key),
            UNIQUE (corpus_version_id, ordinal),
            UNIQUE (corpus_version_id, content_sha256),
            UNIQUE (id, corpus_version_id)
        )
    """)
    op.execute("""
        CREATE TABLE document_chunks (
            id uuid PRIMARY KEY,
            corpus_version_id uuid NOT NULL,
            document_id uuid NOT NULL,
            ordinal integer NOT NULL CHECK (ordinal >= 0),
            section_title text NOT NULL,
            start_character integer NOT NULL CHECK (start_character >= 0),
            end_character integer NOT NULL CHECK (end_character > start_character),
            text text NOT NULL CHECK (btrim(text) <> ''),
            text_sha256 catalog_sha256 NOT NULL,
            metadata jsonb NOT NULL CHECK (jsonb_typeof(metadata) = 'object'),
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (document_id, ordinal),
            FOREIGN KEY (document_id, corpus_version_id)
                REFERENCES corpus_documents(id, corpus_version_id),
            UNIQUE (id, corpus_version_id)
        )
    """)
    op.execute("""
        CREATE TABLE retrieval_indexes (
            id uuid PRIMARY KEY,
            corpus_version_id uuid NOT NULL REFERENCES corpus_versions(id),
            profile_sha256 catalog_sha256 NOT NULL,
            embedding_backend text NOT NULL CHECK (btrim(embedding_backend) <> ''),
            embedding_model text NOT NULL CHECK (btrim(embedding_model) <> ''),
            embedding_revision text NOT NULL CHECK (btrim(embedding_revision) <> ''),
            dimensions integer NOT NULL CHECK (dimensions > 0),
            pooling text NOT NULL CHECK (btrim(pooling) <> ''),
            normalization text NOT NULL CHECK (
                normalization IN ('none', 'l2')
            ),
            query_prefix text NOT NULL,
            document_prefix text NOT NULL,
            status text NOT NULL DEFAULT 'pending' CHECK (
                status IN ('pending', 'indexing', 'ready', 'failed')
            ),
            expected_chunks integer NOT NULL CHECK (expected_chunks >= 0),
            indexed_chunks integer NOT NULL DEFAULT 0
                CHECK (indexed_chunks >= 0 AND indexed_chunks <= expected_chunks),
            started_at timestamptz,
            finished_at timestamptz,
            last_error text,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (corpus_version_id, profile_sha256),
            UNIQUE (id, corpus_version_id),
            CHECK (
                (status IN ('ready')) = (finished_at IS NOT NULL AND last_error IS NULL)
            ),
            CHECK (
                status <> 'failed' OR (
                    finished_at IS NOT NULL AND btrim(last_error) <> ''
                )
            )
        )
    """)
    op.execute("""
        CREATE TABLE chunk_embeddings (
            index_id uuid NOT NULL,
            corpus_version_id uuid NOT NULL,
            chunk_id uuid NOT NULL,
            vector_dimensions integer NOT NULL CHECK (vector_dimensions > 0),
            embedding vector NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (index_id, chunk_id),
            FOREIGN KEY (index_id, corpus_version_id)
                REFERENCES retrieval_indexes(id, corpus_version_id),
            FOREIGN KEY (chunk_id, corpus_version_id)
                REFERENCES document_chunks(id, corpus_version_id)
        )
    """)
    op.execute("""
        CREATE INDEX retrieval_indexes_ready_idx
        ON retrieval_indexes(corpus_version_id, status)
    """)
    op.execute("""
        CREATE INDEX chunk_embeddings_corpus_idx
        ON chunk_embeddings(corpus_version_id, index_id)
    """)
    op.execute("""
        CREATE FUNCTION retrieval_embedding_guard() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            expected_dimensions integer;
        BEGIN
            SELECT dimensions
            INTO expected_dimensions
            FROM retrieval_indexes
            WHERE id = NEW.index_id
              AND corpus_version_id = NEW.corpus_version_id;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'embedding index or corpus differs'
                    USING ERRCODE = '23503';
            END IF;
            IF NEW.vector_dimensions <> expected_dimensions
               OR vector_dims(NEW.embedding) <> expected_dimensions THEN
                RAISE EXCEPTION 'embedding dimension differs from index profile'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END
        $$
    """)
    op.execute("""
        CREATE TRIGGER chunk_embeddings_dimension_guard
        BEFORE INSERT ON chunk_embeddings
        FOR EACH ROW EXECUTE FUNCTION retrieval_embedding_guard()
    """)
    op.execute("""
        CREATE FUNCTION retrieval_guard_lineage() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF ROW(
                NEW.id, NEW.corpus_name, NEW.version, NEW.evidence_kind,
                NEW.manifest_sha256, NEW.manifest, NEW.chunk_config_sha256,
                NEW.chunk_config, NEW.expected_documents, NEW.expected_chunks
            ) IS DISTINCT FROM ROW(
                OLD.id, OLD.corpus_name, OLD.version, OLD.evidence_kind,
                OLD.manifest_sha256, OLD.manifest, OLD.chunk_config_sha256,
                OLD.chunk_config, OLD.expected_documents, OLD.expected_chunks
            ) THEN
                RAISE EXCEPTION 'corpus lineage is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END
        $$
    """)
    op.execute("""
        CREATE TRIGGER corpus_versions_lineage_immutable
        BEFORE UPDATE ON corpus_versions
        FOR EACH ROW EXECUTE FUNCTION retrieval_guard_lineage()
    """)
    op.execute("""
        CREATE FUNCTION retrieval_index_guard_lineage() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF ROW(
                NEW.id, NEW.corpus_version_id, NEW.profile_sha256,
                NEW.embedding_backend, NEW.embedding_model, NEW.embedding_revision,
                NEW.dimensions, NEW.pooling, NEW.normalization,
                NEW.query_prefix, NEW.document_prefix, NEW.expected_chunks
            ) IS DISTINCT FROM ROW(
                OLD.id, OLD.corpus_version_id, OLD.profile_sha256,
                OLD.embedding_backend, OLD.embedding_model, OLD.embedding_revision,
                OLD.dimensions, OLD.pooling, OLD.normalization,
                OLD.query_prefix, OLD.document_prefix, OLD.expected_chunks
            ) THEN
                RAISE EXCEPTION 'retrieval index lineage is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END
        $$
    """)
    op.execute("""
        CREATE TRIGGER retrieval_indexes_lineage_immutable
        BEFORE UPDATE ON retrieval_indexes
        FOR EACH ROW EXECUTE FUNCTION retrieval_index_guard_lineage()
    """)
    for table in ("corpus_documents", "document_chunks", "chunk_embeddings"):
        op.execute(f"""
            CREATE TRIGGER {table}_immutable
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION catalog_reject_mutation()
        """)
    op.execute("""
        CREATE TRIGGER corpus_versions_delete_immutable
        BEFORE DELETE ON corpus_versions
        FOR EACH ROW EXECUTE FUNCTION catalog_reject_mutation()
    """)
    op.execute("""
        CREATE TRIGGER retrieval_indexes_delete_immutable
        BEFORE DELETE ON retrieval_indexes
        FOR EACH ROW EXECUTE FUNCTION catalog_reject_mutation()
    """)


def downgrade():
    for table in (
        "chunk_embeddings",
        "retrieval_indexes",
        "document_chunks",
        "corpus_documents",
        "corpus_versions",
    ):
        op.drop_table(table)
    op.execute("DROP FUNCTION retrieval_index_guard_lineage()")
    op.execute("DROP FUNCTION retrieval_guard_lineage()")
    op.execute("DROP FUNCTION retrieval_embedding_guard()")
