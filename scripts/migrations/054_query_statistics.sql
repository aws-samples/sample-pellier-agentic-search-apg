\set ON_ERROR_STOP on

-- Workshop Studio preloads this module in the cluster parameter group.
-- Loading the library and creating the database extension are separate steps.
-- Facilitator readiness requires the extension in the workshop database.
CREATE EXTENSION IF NOT EXISTS pg_stat_statements WITH SCHEMA public;
