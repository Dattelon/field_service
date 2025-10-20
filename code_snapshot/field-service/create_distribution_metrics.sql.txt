CREATE TABLE IF NOT EXISTS public.distribution_metrics (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL,
    master_id INTEGER,
    assigned_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    round_number SMALLINT NOT NULL,
    candidates_count SMALLINT NOT NULL,
    time_to_assign_seconds INTEGER,
    preferred_master_used BOOLEAN DEFAULT FALSE NOT NULL,
    was_escalated_to_logist BOOLEAN DEFAULT FALSE NOT NULL,
    was_escalated_to_admin BOOLEAN DEFAULT FALSE NOT NULL,
    city_id INTEGER NOT NULL REFERENCES cities(id) ON DELETE CASCADE,
    district_id INTEGER REFERENCES districts(id) ON DELETE SET NULL,
    category VARCHAR(32),
    order_type VARCHAR(32),
    metadata_json JSONB DEFAULT '{}'::jsonb NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_distribution_metrics_order_id ON distribution_metrics(order_id);
CREATE INDEX IF NOT EXISTS idx_distribution_metrics_master_id ON distribution_metrics(master_id);
CREATE INDEX IF NOT EXISTS idx_distribution_metrics_city_id ON distribution_metrics(city_id);
CREATE INDEX IF NOT EXISTS idx_distribution_metrics_district_id ON distribution_metrics(district_id);
CREATE INDEX IF NOT EXISTS ix_distribution_metrics__assigned_at_desc ON distribution_metrics(assigned_at DESC);
CREATE INDEX IF NOT EXISTS ix_distribution_metrics__city_assigned ON distribution_metrics(city_id, assigned_at);
CREATE INDEX IF NOT EXISTS ix_distribution_metrics__performance ON distribution_metrics(round_number, time_to_assign_seconds);

ALTER TABLE distribution_metrics DROP CONSTRAINT IF EXISTS distribution_metrics_master_id_fkey;
ALTER TABLE distribution_metrics DROP CONSTRAINT IF EXISTS distribution_metrics_order_id_fkey;

ALTER TABLE distribution_metrics ADD CONSTRAINT distribution_metrics_master_id_fkey 
  FOREIGN KEY (master_id) REFERENCES masters(id) ON DELETE SET NULL;
ALTER TABLE distribution_metrics ADD CONSTRAINT distribution_metrics_order_id_fkey 
  FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE;
