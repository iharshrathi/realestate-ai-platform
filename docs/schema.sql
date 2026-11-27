-- PostgreSQL DDL generated from the SQLAlchemy models (backend/app/models).
-- The application creates these tables itself on startup (create_all); this file is for review.

CREATE TABLE marketing_campaigns (
	id SERIAL NOT NULL, 
	name VARCHAR(160) NOT NULL, 
	channel VARCHAR(24) NOT NULL, 
	start_date DATE NOT NULL, 
	end_date DATE, 
	spend_inr BIGINT NOT NULL, 
	notes TEXT, 
	is_synthetic BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_marketing_campaigns PRIMARY KEY (id), 
	CONSTRAINT ck_marketing_campaigns_spend_non_negative CHECK (spend_inr >= 0), 
	CONSTRAINT ck_marketing_campaigns_dates_ordered CHECK (end_date IS NULL OR end_date >= start_date), 
	CONSTRAINT uq_marketing_campaigns_name UNIQUE (name), 
	CONSTRAINT ck_marketing_campaigns_leadsource CHECK (channel IN ('website', 'facebook_ads', 'newspaper', 'direct'))
);

CREATE INDEX ix_marketing_campaigns_channel ON marketing_campaigns (channel);

CREATE TABLE properties (
	id SERIAL NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	location VARCHAR(120) NOT NULL, 
	property_type VARCHAR(24) NOT NULL, 
	price_inr BIGINT NOT NULL, 
	bedrooms INTEGER, 
	area_sqft INTEGER, 
	description TEXT NOT NULL, 
	amenities JSON NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	is_synthetic BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_properties PRIMARY KEY (id), 
	CONSTRAINT ck_properties_price_positive CHECK (price_inr > 0), 
	CONSTRAINT ck_properties_bedrooms_non_negative CHECK (bedrooms IS NULL OR bedrooms >= 0), 
	CONSTRAINT ck_properties_propertytype CHECK (property_type IN ('apartment', 'villa', 'plot', 'commercial')), 
	CONSTRAINT ck_properties_propertystatus CHECK (status IN ('available', 'on_hold', 'sold'))
);

CREATE INDEX ix_properties_location ON properties (location);

CREATE INDEX ix_properties_price_inr ON properties (price_inr);

CREATE INDEX ix_properties_property_type ON properties (property_type);

CREATE INDEX ix_properties_status ON properties (status);

CREATE TABLE users (
	id SERIAL NOT NULL, 
	email VARCHAR(254) NOT NULL, 
	full_name VARCHAR(120) NOT NULL, 
	hashed_password VARCHAR(255) NOT NULL, 
	role VARCHAR(24) NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_users PRIMARY KEY (id), 
	CONSTRAINT ck_users_userrole CHECK (role IN ('admin', 'manager', 'agent'))
);

CREATE UNIQUE INDEX ix_users_email ON users (email);

CREATE TABLE leads (
	id SERIAL NOT NULL, 
	full_name VARCHAR(120) NOT NULL, 
	email VARCHAR(254), 
	phone VARCHAR(20), 
	source VARCHAR(24) NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	campaign_id INTEGER, 
	assigned_to_id INTEGER, 
	latest_probability FLOAT, 
	latest_band VARCHAR(24), 
	scored_at TIMESTAMP WITH TIME ZONE, 
	is_synthetic BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	converted_at TIMESTAMP WITH TIME ZONE, 
	CONSTRAINT pk_leads PRIMARY KEY (id), 
	CONSTRAINT ck_leads_contact_required CHECK (email IS NOT NULL OR phone IS NOT NULL), 
	CONSTRAINT ck_leads_probability_range CHECK (latest_probability IS NULL OR (latest_probability >= 0 AND latest_probability <= 1)), 
	CONSTRAINT ck_leads_leadsource CHECK (source IN ('website', 'facebook_ads', 'newspaper', 'direct')), 
	CONSTRAINT ck_leads_leadstatus CHECK (status IN ('new', 'contacted', 'qualified', 'site_visit', 'negotiation', 'converted', 'lost')), 
	CONSTRAINT fk_leads_campaign_id_marketing_campaigns FOREIGN KEY(campaign_id) REFERENCES marketing_campaigns (id) ON DELETE SET NULL, 
	CONSTRAINT fk_leads_assigned_to_id_users FOREIGN KEY(assigned_to_id) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT ck_leads_scoreband CHECK (latest_band IN ('hot', 'warm', 'cold'))
);

CREATE INDEX ix_leads_assigned_to_id ON leads (assigned_to_id);

CREATE INDEX ix_leads_campaign_id ON leads (campaign_id);

CREATE INDEX ix_leads_converted_at ON leads (converted_at);

CREATE INDEX ix_leads_created_at ON leads (created_at);

CREATE INDEX ix_leads_email ON leads (email);

CREATE INDEX ix_leads_latest_band ON leads (latest_band);

CREATE INDEX ix_leads_latest_probability ON leads (latest_probability);

CREATE INDEX ix_leads_phone ON leads (phone);

CREATE INDEX ix_leads_source ON leads (source);

CREATE INDEX ix_leads_status ON leads (status);

CREATE TABLE agent_logs (
	id SERIAL NOT NULL, 
	run_id VARCHAR(36) NOT NULL, 
	agent_name VARCHAR(60) NOT NULL, 
	action VARCHAR(80) NOT NULL, 
	lead_id INTEGER, 
	triggered_by_id INTEGER, 
	status VARCHAR(24) NOT NULL, 
	input_summary JSON NOT NULL, 
	output_summary JSON NOT NULL, 
	error TEXT, 
	duration_ms INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_agent_logs PRIMARY KEY (id), 
	CONSTRAINT fk_agent_logs_lead_id_leads FOREIGN KEY(lead_id) REFERENCES leads (id) ON DELETE SET NULL, 
	CONSTRAINT fk_agent_logs_triggered_by_id_users FOREIGN KEY(triggered_by_id) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT ck_agent_logs_agentrunstatus CHECK (status IN ('success', 'failed'))
);

CREATE INDEX ix_agent_logs_agent_name ON agent_logs (agent_name);

CREATE INDEX ix_agent_logs_created_at ON agent_logs (created_at);

CREATE INDEX ix_agent_logs_lead_id ON agent_logs (lead_id);

CREATE INDEX ix_agent_logs_run_id ON agent_logs (run_id);

CREATE TABLE customer_requirements (
	id SERIAL NOT NULL, 
	lead_id INTEGER NOT NULL, 
	budget_min BIGINT, 
	budget_max BIGINT, 
	preferred_location VARCHAR(120), 
	property_type VARCHAR(24), 
	bedrooms INTEGER, 
	purchase_timeline_days INTEGER, 
	urgency VARCHAR(10), 
	intent VARCHAR(40), 
	loan_preapproved BOOLEAN, 
	notes TEXT, 
	raw_text TEXT, 
	source VARCHAR(24) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_customer_requirements PRIMARY KEY (id), 
	CONSTRAINT ck_customer_requirements_budget_ordered CHECK (budget_min IS NULL OR budget_max IS NULL OR budget_min <= budget_max), 
	CONSTRAINT fk_customer_requirements_lead_id_leads FOREIGN KEY(lead_id) REFERENCES leads (id) ON DELETE CASCADE, 
	CONSTRAINT ck_customer_requirements_propertytype CHECK (property_type IN ('apartment', 'villa', 'plot', 'commercial')), 
	CONSTRAINT ck_customer_requirements_requirementsource CHECK (source IN ('manual', 'nlp', 'chatbot', 'import'))
);

CREATE INDEX ix_customer_requirements_lead_id ON customer_requirements (lead_id);

CREATE TABLE follow_ups (
	id SERIAL NOT NULL, 
	lead_id INTEGER NOT NULL, 
	assigned_to_id INTEGER, 
	channel VARCHAR(24) NOT NULL, 
	message TEXT NOT NULL, 
	template_key VARCHAR(40), 
	priority VARCHAR(24) NOT NULL, 
	rationale TEXT, 
	status VARCHAR(24) NOT NULL, 
	generated_by VARCHAR(24) NOT NULL, 
	due_at TIMESTAMP WITH TIME ZONE, 
	approved_by_id INTEGER, 
	approved_at TIMESTAMP WITH TIME ZONE, 
	sent_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_follow_ups PRIMARY KEY (id), 
	CONSTRAINT fk_follow_ups_lead_id_leads FOREIGN KEY(lead_id) REFERENCES leads (id) ON DELETE CASCADE, 
	CONSTRAINT fk_follow_ups_assigned_to_id_users FOREIGN KEY(assigned_to_id) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT ck_follow_ups_followupchannel CHECK (channel IN ('whatsapp', 'email', 'sms', 'call')), 
	CONSTRAINT ck_follow_ups_priority CHECK (priority IN ('high', 'medium', 'low')), 
	CONSTRAINT ck_follow_ups_followupstatus CHECK (status IN ('draft', 'approved', 'sent', 'completed', 'rejected')), 
	CONSTRAINT ck_follow_ups_followupauthor CHECK (generated_by IN ('human', 'template', 'llm')), 
	CONSTRAINT fk_follow_ups_approved_by_id_users FOREIGN KEY(approved_by_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_follow_ups_lead_id ON follow_ups (lead_id);

CREATE INDEX ix_follow_ups_status_due ON follow_ups (status, due_at);

CREATE TABLE lead_interactions (
	id SERIAL NOT NULL, 
	lead_id INTEGER NOT NULL, 
	type VARCHAR(24) NOT NULL, 
	direction VARCHAR(24) NOT NULL, 
	content TEXT NOT NULL, 
	occurred_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	created_by_id INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_lead_interactions PRIMARY KEY (id), 
	CONSTRAINT fk_lead_interactions_lead_id_leads FOREIGN KEY(lead_id) REFERENCES leads (id) ON DELETE CASCADE, 
	CONSTRAINT ck_lead_interactions_interactiontype CHECK (type IN ('enquiry', 'call', 'email', 'whatsapp', 'sms', 'site_visit', 'meeting', 'note')), 
	CONSTRAINT ck_lead_interactions_interactiondirection CHECK (direction IN ('inbound', 'outbound', 'internal')), 
	CONSTRAINT fk_lead_interactions_created_by_id_users FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_lead_interactions_lead_occurred ON lead_interactions (lead_id, occurred_at);

CREATE TABLE predictions (
	id SERIAL NOT NULL, 
	lead_id INTEGER NOT NULL, 
	probability FLOAT NOT NULL, 
	band VARCHAR(24) NOT NULL, 
	model_version VARCHAR(80) NOT NULL, 
	features JSON NOT NULL, 
	factors JSON NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_predictions PRIMARY KEY (id), 
	CONSTRAINT ck_predictions_probability_range CHECK (probability >= 0 AND probability <= 1), 
	CONSTRAINT fk_predictions_lead_id_leads FOREIGN KEY(lead_id) REFERENCES leads (id) ON DELETE CASCADE, 
	CONSTRAINT ck_predictions_scoreband CHECK (band IN ('hot', 'warm', 'cold'))
);

CREATE INDEX ix_predictions_lead_created ON predictions (lead_id, created_at);
