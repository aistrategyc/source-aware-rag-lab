CREATE TABLE memberships (
    tenant_id text NOT NULL,
    user_id text NOT NULL,
    role text NOT NULL CHECK (role IN ('viewer', 'editor')),
    active boolean NOT NULL DEFAULT true,
    PRIMARY KEY (tenant_id, user_id)
);
CREATE TABLE sources (
    tenant_id text NOT NULL,
    id uuid NOT NULL,
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    title text NOT NULL,
    body text NOT NULL,
    deleted boolean NOT NULL DEFAULT false,
    PRIMARY KEY (tenant_id, id)
);
CREATE FUNCTION advance_source_version() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (NEW.title, NEW.body, NEW.deleted, NEW.version)
       IS DISTINCT FROM (OLD.title, OLD.body, OLD.deleted, OLD.version) THEN
        NEW.version := OLD.version + 1;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER sources_version BEFORE UPDATE ON sources
    FOR EACH ROW EXECUTE FUNCTION advance_source_version();
CREATE TABLE search_chunks (
    tenant_id text NOT NULL,
    source_id uuid NOT NULL,
    source_version integer NOT NULL,
    body text NOT NULL,
    search_vector tsvector GENERATED ALWAYS AS (to_tsvector('english', body)) STORED,
    PRIMARY KEY (tenant_id, source_id)
);
CREATE INDEX chunks_search ON search_chunks USING gin(search_vector);
CREATE TABLE proposals (
    id uuid PRIMARY KEY,
    tenant_id text NOT NULL,
    actor_id text NOT NULL,
    source_id uuid NOT NULL,
    source_version integer NOT NULL,
    title text NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
    expires_at timestamptz NOT NULL,
    confirmed_task_id uuid UNIQUE,
    FOREIGN KEY (tenant_id, actor_id) REFERENCES memberships(tenant_id, user_id),
    FOREIGN KEY (tenant_id, source_id) REFERENCES sources(tenant_id, id)
);
CREATE TABLE tasks (
    id uuid PRIMARY KEY,
    tenant_id text NOT NULL,
    actor_id text NOT NULL,
    source_id uuid NOT NULL,
    title text NOT NULL,
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, actor_id) REFERENCES memberships(tenant_id, user_id),
    FOREIGN KEY (tenant_id, source_id) REFERENCES sources(tenant_id, id)
);
ALTER TABLE proposals ADD FOREIGN KEY (tenant_id, confirmed_task_id) REFERENCES tasks(tenant_id, id);
