--
-- PostgreSQL database dump
--

\restrict Le803j56FvZjyZzC3lDJRhMrkNFKGLnBqunBuGfrZ1Tv9dgsMr5pvhGCIzLeeGq

-- Dumped from database version 15.14
-- Dumped by pg_dump version 15.14

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: attachment_entity; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.attachment_entity AS ENUM (
    'ORDER',
    'OFFER',
    'COMMISSION',
    'MASTER'
);


--
-- Name: attachment_file_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.attachment_file_type AS ENUM (
    'PHOTO',
    'DOCUMENT',
    'AUDIO',
    'VIDEO',
    'OTHER'
);


--
-- Name: commission_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.commission_status AS ENUM (
    'PENDING',
    'PAID',
    'OVERDUE',
    'WAIT_PAY',
    'REPORTED',
    'APPROVED'
);


--
-- Name: moderation_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.moderation_status AS ENUM (
    'PENDING',
    'APPROVED',
    'REJECTED'
);


--
-- Name: offer_state; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.offer_state AS ENUM (
    'SENT',
    'VIEWED',
    'ACCEPTED',
    'DECLINED',
    'EXPIRED',
    'CANCELED'
);


--
-- Name: order_category; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.order_category AS ENUM (
    'ELECTRICS',
    'PLUMBING',
    'APPLIANCES',
    'WINDOWS',
    'HANDYMAN',
    'ROADSIDE'
);


--
-- Name: order_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.order_status AS ENUM (
    'CREATED',
    'SEARCHING',
    'ASSIGNED',
    'EN_ROUTE',
    'WORKING',
    'PAYMENT',
    'CLOSED',
    'DEFERRED',
    'GUARANTEE',
    'CANCELED'
);


--
-- Name: order_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.order_type AS ENUM (
    'NORMAL',
    'GUARANTEE'
);


--
-- Name: payout_method; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.payout_method AS ENUM (
    'CARD',
    'SBP',
    'YOOMONEY',
    'BANK_ACCOUNT'
);


--
-- Name: referral_reward_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.referral_reward_status AS ENUM (
    'ACCRUED',
    'PAID',
    'CANCELED'
);


--
-- Name: shift_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.shift_status AS ENUM (
    'SHIFT_OFF',
    'SHIFT_ON',
    'BREAK'
);


--
-- Name: staff_role; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.staff_role AS ENUM (
    'ADMIN',
    'LOGIST',
    'CITY_ADMIN',
    'GLOBAL_ADMIN'
);


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: admin_audit_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.admin_audit_log (
    id integer NOT NULL,
    admin_id integer,
    master_id integer,
    action character varying(64) NOT NULL,
    payload_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: admin_audit_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.admin_audit_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: admin_audit_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.admin_audit_log_id_seq OWNED BY public.admin_audit_log.id;


--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: attachments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.attachments (
    id integer NOT NULL,
    entity_type public.attachment_entity NOT NULL,
    entity_id bigint NOT NULL,
    file_type public.attachment_file_type NOT NULL,
    file_id character varying(256) NOT NULL,
    file_unique_id character varying(256),
    file_name character varying(256),
    mime_type character varying(128),
    size integer,
    caption text,
    uploaded_by_master_id integer,
    uploaded_by_staff_id integer,
    created_at timestamp with time zone DEFAULT now(),
    document_type character varying(32)
);


--
-- Name: attachments_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.attachments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: attachments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.attachments_id_seq OWNED BY public.attachments.id;


--
-- Name: cities; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cities (
    id integer NOT NULL,
    name character varying(120) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    timezone character varying(64),
    centroid_lat double precision,
    centroid_lon double precision
);


--
-- Name: cities_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.cities_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cities_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.cities_id_seq OWNED BY public.cities.id;


--
-- Name: commissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commissions (
    id integer NOT NULL,
    order_id integer NOT NULL,
    master_id integer NOT NULL,
    amount numeric(10,2) NOT NULL,
    percent numeric(5,2),
    status public.commission_status NOT NULL,
    deadline_at timestamp with time zone NOT NULL,
    paid_at timestamp with time zone,
    blocked_applied boolean DEFAULT false NOT NULL,
    blocked_at timestamp with time zone,
    payment_reference character varying(120),
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    rate numeric(5,2),
    paid_reported_at timestamp with time zone,
    paid_approved_at timestamp with time zone,
    paid_amount numeric(10,2),
    is_paid boolean DEFAULT false NOT NULL,
    has_checks boolean DEFAULT false NOT NULL,
    pay_to_snapshot jsonb
);


--
-- Name: commissions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.commissions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: commissions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.commissions_id_seq OWNED BY public.commissions.id;


--
-- Name: districts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.districts (
    id integer NOT NULL,
    city_id integer NOT NULL,
    name character varying(120) NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    centroid_lat double precision,
    centroid_lon double precision
);


--
-- Name: districts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.districts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: districts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.districts_id_seq OWNED BY public.districts.id;


--
-- Name: geocache; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.geocache (
    query character varying(255) NOT NULL,
    lat double precision,
    lon double precision,
    provider character varying(32),
    confidence integer,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: master_districts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.master_districts (
    master_id integer NOT NULL,
    district_id integer NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: master_invite_codes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.master_invite_codes (
    id integer NOT NULL,
    code character varying(32) NOT NULL,
    city_id integer,
    issued_by_staff_id integer,
    used_by_master_id integer,
    expires_at timestamp with time zone,
    is_revoked boolean DEFAULT false NOT NULL,
    used_at timestamp with time zone,
    comment character varying(255),
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: master_invite_codes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.master_invite_codes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: master_invite_codes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.master_invite_codes_id_seq OWNED BY public.master_invite_codes.id;


--
-- Name: master_skills; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.master_skills (
    master_id integer NOT NULL,
    skill_id integer NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: masters; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.masters (
    id integer NOT NULL,
    tg_user_id bigint,
    full_name character varying(160) NOT NULL,
    phone character varying(32),
    city_id integer,
    rating double precision DEFAULT '5'::double precision NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    is_blocked boolean DEFAULT false NOT NULL,
    blocked_at timestamp with time zone,
    blocked_reason text,
    referral_code character varying(32),
    referred_by_master_id integer,
    last_heartbeat_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    version integer DEFAULT 1 NOT NULL,
    moderation_status public.moderation_status DEFAULT 'PENDING'::public.moderation_status NOT NULL,
    moderation_note text,
    shift_status public.shift_status DEFAULT 'SHIFT_OFF'::public.shift_status NOT NULL,
    break_until timestamp with time zone,
    pdn_accepted_at timestamp with time zone,
    payout_method public.payout_method,
    payout_data jsonb,
    has_vehicle boolean DEFAULT false NOT NULL,
    vehicle_plate character varying(16),
    home_latitude numeric(9,6),
    home_longitude numeric(9,6),
    max_active_orders_override smallint,
    is_on_shift boolean DEFAULT false NOT NULL,
    verified boolean DEFAULT false NOT NULL,
    is_deleted boolean NOT NULL,
    moderation_reason text,
    verified_at timestamp with time zone,
    verified_by integer,
    CONSTRAINT ck_masters__ck_masters__limit_nonneg CHECK (((max_active_orders_override IS NULL) OR (max_active_orders_override >= 0)))
);


--
-- Name: masters_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.masters_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: masters_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.masters_id_seq OWNED BY public.masters.id;


--
-- Name: notifications_outbox; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.notifications_outbox (
    id integer NOT NULL,
    master_id integer NOT NULL,
    event character varying(64) NOT NULL,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    processed_at timestamp with time zone
);


--
-- Name: notifications_outbox_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.notifications_outbox_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: notifications_outbox_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.notifications_outbox_id_seq OWNED BY public.notifications_outbox.id;


--
-- Name: offers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.offers (
    id integer NOT NULL,
    order_id integer NOT NULL,
    master_id integer NOT NULL,
    round_number smallint DEFAULT '1'::smallint NOT NULL,
    state public.offer_state NOT NULL,
    sent_at timestamp with time zone DEFAULT now(),
    responded_at timestamp with time zone,
    expires_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: offers_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.offers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: offers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.offers_id_seq OWNED BY public.offers.id;


--
-- Name: order_autoclose_queue; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.order_autoclose_queue (
    order_id integer NOT NULL,
    closed_at timestamp with time zone NOT NULL,
    autoclose_at timestamp with time zone NOT NULL,
    processed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: order_status_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.order_status_history (
    id integer NOT NULL,
    order_id integer NOT NULL,
    from_status public.order_status,
    to_status public.order_status NOT NULL,
    reason text,
    changed_by_staff_id integer,
    changed_by_master_id integer,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: order_status_history_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.order_status_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: order_status_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.order_status_history_id_seq OWNED BY public.order_status_history.id;


--
-- Name: orders; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.orders (
    id integer NOT NULL,
    city_id integer NOT NULL,
    district_id integer,
    street_id integer,
    house character varying(32),
    apartment character varying(32),
    address_comment text,
    client_name character varying(160),
    client_phone character varying(32),
    status public.order_status DEFAULT 'CREATED'::public.order_status NOT NULL,
    preferred_master_id integer,
    assigned_master_id integer,
    created_by_staff_id integer,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    version integer DEFAULT 1 NOT NULL,
    company_payment numeric(10,2) DEFAULT '0'::numeric NOT NULL,
    guarantee_source_order_id integer,
    order_type public.order_type DEFAULT 'NORMAL'::public.order_type NOT NULL,
    category public.order_category,
    description text,
    late_visit boolean DEFAULT false NOT NULL,
    dist_escalated_logist_at timestamp with time zone,
    dist_escalated_admin_at timestamp with time zone,
    lat numeric(9,6),
    lon numeric(9,6),
    timeslot_start_utc timestamp with time zone,
    timeslot_end_utc timestamp with time zone,
    total_sum numeric(10,2) NOT NULL,
    cancel_reason text,
    no_district boolean NOT NULL,
    type public.order_type NOT NULL,
    geocode_provider character varying(32),
    geocode_confidence integer,
    escalation_logist_notified_at timestamp with time zone,
    escalation_admin_notified_at timestamp with time zone,
    CONSTRAINT ck_orders__timeslot_range CHECK ((((timeslot_start_utc IS NULL) AND (timeslot_end_utc IS NULL)) OR (timeslot_start_utc < timeslot_end_utc)))
);


--
-- Name: orders_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.orders_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: orders_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.orders_id_seq OWNED BY public.orders.id;


--
-- Name: referral_rewards; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.referral_rewards (
    id integer NOT NULL,
    referrer_id integer NOT NULL,
    referred_master_id integer NOT NULL,
    commission_id integer NOT NULL,
    level smallint NOT NULL,
    percent numeric(5,2) NOT NULL,
    amount numeric(10,2) NOT NULL,
    status public.referral_reward_status NOT NULL,
    paid_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: referral_rewards_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.referral_rewards_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: referral_rewards_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.referral_rewards_id_seq OWNED BY public.referral_rewards.id;


--
-- Name: referrals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.referrals (
    id integer NOT NULL,
    master_id integer NOT NULL,
    referrer_id integer NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: referrals_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.referrals_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: referrals_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.referrals_id_seq OWNED BY public.referrals.id;


--
-- Name: settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.settings (
    key character varying(80) NOT NULL,
    value text NOT NULL,
    value_type character varying(16) DEFAULT 'STR'::character varying NOT NULL,
    description text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: skills; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.skills (
    id integer NOT NULL,
    code character varying(64) NOT NULL,
    name character varying(160) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: skills_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.skills_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: skills_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.skills_id_seq OWNED BY public.skills.id;


--
-- Name: staff_access_code_cities; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.staff_access_code_cities (
    access_code_id integer NOT NULL,
    city_id integer NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: staff_access_codes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.staff_access_codes (
    id integer NOT NULL,
    code character varying(16) NOT NULL,
    role public.staff_role NOT NULL,
    city_id integer,
    created_by_staff_id integer,
    used_by_staff_id integer,
    expires_at timestamp with time zone,
    used_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    comment text,
    revoked_at timestamp with time zone
);


--
-- Name: staff_access_codes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.staff_access_codes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: staff_access_codes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.staff_access_codes_id_seq OWNED BY public.staff_access_codes.id;


--
-- Name: staff_cities; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.staff_cities (
    staff_user_id integer NOT NULL,
    city_id integer NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: staff_users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.staff_users (
    id integer NOT NULL,
    tg_user_id bigint,
    username character varying(64),
    full_name character varying(160),
    phone character varying(32),
    role public.staff_role NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    commission_requisites jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: staff_users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.staff_users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: staff_users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.staff_users_id_seq OWNED BY public.staff_users.id;


--
-- Name: streets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.streets (
    id integer NOT NULL,
    city_id integer NOT NULL,
    district_id integer,
    name character varying(200) NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    centroid_lat double precision,
    centroid_lon double precision
);


--
-- Name: streets_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.streets_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: streets_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.streets_id_seq OWNED BY public.streets.id;


--
-- Name: admin_audit_log id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admin_audit_log ALTER COLUMN id SET DEFAULT nextval('public.admin_audit_log_id_seq'::regclass);


--
-- Name: attachments id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attachments ALTER COLUMN id SET DEFAULT nextval('public.attachments_id_seq'::regclass);


--
-- Name: cities id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cities ALTER COLUMN id SET DEFAULT nextval('public.cities_id_seq'::regclass);


--
-- Name: commissions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commissions ALTER COLUMN id SET DEFAULT nextval('public.commissions_id_seq'::regclass);


--
-- Name: districts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.districts ALTER COLUMN id SET DEFAULT nextval('public.districts_id_seq'::regclass);


--
-- Name: master_invite_codes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.master_invite_codes ALTER COLUMN id SET DEFAULT nextval('public.master_invite_codes_id_seq'::regclass);


--
-- Name: masters id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.masters ALTER COLUMN id SET DEFAULT nextval('public.masters_id_seq'::regclass);


--
-- Name: notifications_outbox id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications_outbox ALTER COLUMN id SET DEFAULT nextval('public.notifications_outbox_id_seq'::regclass);


--
-- Name: offers id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.offers ALTER COLUMN id SET DEFAULT nextval('public.offers_id_seq'::regclass);


--
-- Name: order_status_history id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_status_history ALTER COLUMN id SET DEFAULT nextval('public.order_status_history_id_seq'::regclass);


--
-- Name: orders id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders ALTER COLUMN id SET DEFAULT nextval('public.orders_id_seq'::regclass);


--
-- Name: referral_rewards id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_rewards ALTER COLUMN id SET DEFAULT nextval('public.referral_rewards_id_seq'::regclass);


--
-- Name: referrals id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referrals ALTER COLUMN id SET DEFAULT nextval('public.referrals_id_seq'::regclass);


--
-- Name: skills id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.skills ALTER COLUMN id SET DEFAULT nextval('public.skills_id_seq'::regclass);


--
-- Name: staff_access_codes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_access_codes ALTER COLUMN id SET DEFAULT nextval('public.staff_access_codes_id_seq'::regclass);


--
-- Name: staff_users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_users ALTER COLUMN id SET DEFAULT nextval('public.staff_users_id_seq'::regclass);


--
-- Name: streets id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.streets ALTER COLUMN id SET DEFAULT nextval('public.streets_id_seq'::regclass);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: admin_audit_log pk_admin_audit_log; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admin_audit_log
    ADD CONSTRAINT pk_admin_audit_log PRIMARY KEY (id);


--
-- Name: attachments pk_attachments; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attachments
    ADD CONSTRAINT pk_attachments PRIMARY KEY (id);


--
-- Name: cities pk_cities; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cities
    ADD CONSTRAINT pk_cities PRIMARY KEY (id);


--
-- Name: commissions pk_commissions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commissions
    ADD CONSTRAINT pk_commissions PRIMARY KEY (id);


--
-- Name: districts pk_districts; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.districts
    ADD CONSTRAINT pk_districts PRIMARY KEY (id);


--
-- Name: geocache pk_geocache; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.geocache
    ADD CONSTRAINT pk_geocache PRIMARY KEY (query);


--
-- Name: master_districts pk_master_districts; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.master_districts
    ADD CONSTRAINT pk_master_districts PRIMARY KEY (master_id, district_id);


--
-- Name: master_invite_codes pk_master_invite_codes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.master_invite_codes
    ADD CONSTRAINT pk_master_invite_codes PRIMARY KEY (id);


--
-- Name: master_skills pk_master_skills; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.master_skills
    ADD CONSTRAINT pk_master_skills PRIMARY KEY (master_id, skill_id);


--
-- Name: masters pk_masters; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.masters
    ADD CONSTRAINT pk_masters PRIMARY KEY (id);


--
-- Name: notifications_outbox pk_notifications_outbox; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications_outbox
    ADD CONSTRAINT pk_notifications_outbox PRIMARY KEY (id);


--
-- Name: offers pk_offers; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.offers
    ADD CONSTRAINT pk_offers PRIMARY KEY (id);


--
-- Name: order_autoclose_queue pk_order_autoclose_queue; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_autoclose_queue
    ADD CONSTRAINT pk_order_autoclose_queue PRIMARY KEY (order_id);


--
-- Name: order_status_history pk_order_status_history; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_status_history
    ADD CONSTRAINT pk_order_status_history PRIMARY KEY (id);


--
-- Name: orders pk_orders; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT pk_orders PRIMARY KEY (id);


--
-- Name: referral_rewards pk_referral_rewards; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_rewards
    ADD CONSTRAINT pk_referral_rewards PRIMARY KEY (id);


--
-- Name: referrals pk_referrals; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referrals
    ADD CONSTRAINT pk_referrals PRIMARY KEY (id);


--
-- Name: settings pk_settings; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.settings
    ADD CONSTRAINT pk_settings PRIMARY KEY (key);


--
-- Name: skills pk_skills; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.skills
    ADD CONSTRAINT pk_skills PRIMARY KEY (id);


--
-- Name: staff_access_code_cities pk_staff_access_code_cities; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_access_code_cities
    ADD CONSTRAINT pk_staff_access_code_cities PRIMARY KEY (access_code_id, city_id);


--
-- Name: staff_access_codes pk_staff_access_codes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_access_codes
    ADD CONSTRAINT pk_staff_access_codes PRIMARY KEY (id);


--
-- Name: staff_cities pk_staff_cities; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_cities
    ADD CONSTRAINT pk_staff_cities PRIMARY KEY (staff_user_id, city_id);


--
-- Name: staff_users pk_staff_users; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_users
    ADD CONSTRAINT pk_staff_users PRIMARY KEY (id);


--
-- Name: streets pk_streets; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.streets
    ADD CONSTRAINT pk_streets PRIMARY KEY (id);


--
-- Name: cities uq_cities__name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cities
    ADD CONSTRAINT uq_cities__name UNIQUE (name);


--
-- Name: commissions uq_commissions__order_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commissions
    ADD CONSTRAINT uq_commissions__order_id UNIQUE (order_id);


--
-- Name: districts uq_districts__city_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.districts
    ADD CONSTRAINT uq_districts__city_name UNIQUE (city_id, name);


--
-- Name: masters uq_masters__referral_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.masters
    ADD CONSTRAINT uq_masters__referral_code UNIQUE (referral_code);


--
-- Name: masters uq_masters__tg_user_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.masters
    ADD CONSTRAINT uq_masters__tg_user_id UNIQUE (tg_user_id);


--
-- Name: offers uq_offers__order_master; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.offers
    ADD CONSTRAINT uq_offers__order_master UNIQUE (order_id, master_id);


--
-- Name: referral_rewards uq_referral_rewards__commission_level; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_rewards
    ADD CONSTRAINT uq_referral_rewards__commission_level UNIQUE (commission_id, level);


--
-- Name: referrals uq_referrals__master_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referrals
    ADD CONSTRAINT uq_referrals__master_id UNIQUE (master_id);


--
-- Name: skills uq_skills__code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.skills
    ADD CONSTRAINT uq_skills__code UNIQUE (code);


--
-- Name: staff_access_codes uq_staff_access_codes__code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_access_codes
    ADD CONSTRAINT uq_staff_access_codes__code UNIQUE (code);


--
-- Name: streets uq_streets__city_district_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.streets
    ADD CONSTRAINT uq_streets__city_district_name UNIQUE (city_id, district_id, name);


--
-- Name: ix_admin_audit_log_admin_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_admin_audit_log_admin_id ON public.admin_audit_log USING btree (admin_id);


--
-- Name: ix_admin_audit_log_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_admin_audit_log_created_at ON public.admin_audit_log USING btree (created_at);


--
-- Name: ix_admin_audit_log_master_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_admin_audit_log_master_id ON public.admin_audit_log USING btree (master_id);


--
-- Name: ix_attachments__etype_eid; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attachments__etype_eid ON public.attachments USING btree (entity_type, entity_id);


--
-- Name: ix_commissions__ispaid_deadline; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_commissions__ispaid_deadline ON public.commissions USING btree (is_paid, deadline_at);


--
-- Name: ix_districts__city_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_districts__city_id ON public.districts USING btree (city_id);


--
-- Name: ix_geocache_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_geocache_created_at ON public.geocache USING btree (created_at);


--
-- Name: ix_master_districts__district; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_master_districts__district ON public.master_districts USING btree (district_id);


--
-- Name: ix_master_invite_codes__available; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_master_invite_codes__available ON public.master_invite_codes USING btree (code) WHERE ((used_by_master_id IS NULL) AND (is_revoked = false) AND (expires_at IS NULL));


--
-- Name: ix_master_invite_codes__code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_master_invite_codes__code ON public.master_invite_codes USING btree (code);


--
-- Name: ix_master_skills__skill; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_master_skills__skill ON public.master_skills USING btree (skill_id);


--
-- Name: ix_masters__city_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_masters__city_id ON public.masters USING btree (city_id);


--
-- Name: ix_masters__heartbeat; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_masters__heartbeat ON public.masters USING btree (last_heartbeat_at);


--
-- Name: ix_masters__mod_shift; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_masters__mod_shift ON public.masters USING btree (moderation_status, shift_status);


--
-- Name: ix_masters__onshift_verified; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_masters__onshift_verified ON public.masters USING btree (is_on_shift, verified);


--
-- Name: ix_masters__phone; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_masters__phone ON public.masters USING btree (phone);


--
-- Name: ix_masters__referred_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_masters__referred_by ON public.masters USING btree (referred_by_master_id);


--
-- Name: ix_masters__tg_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_masters__tg_user_id ON public.masters USING btree (tg_user_id);


--
-- Name: ix_masters__verified_active_deleted_city; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_masters__verified_active_deleted_city ON public.masters USING btree (verified, is_active, is_deleted, city_id);


--
-- Name: ix_notifications_outbox_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notifications_outbox_created ON public.notifications_outbox USING btree (created_at);


--
-- Name: ix_notifications_outbox_master; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notifications_outbox_master ON public.notifications_outbox USING btree (master_id);


--
-- Name: ix_offers__expires_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_offers__expires_at ON public.offers USING btree (expires_at);


--
-- Name: ix_offers__master_state; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_offers__master_state ON public.offers USING btree (master_id, state);


--
-- Name: ix_offers__order_state; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_offers__order_state ON public.offers USING btree (order_id, state);


--
-- Name: ix_order_autoclose_queue__pending; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_order_autoclose_queue__pending ON public.order_autoclose_queue USING btree (autoclose_at) WHERE (processed_at IS NULL);


--
-- Name: ix_order_status_history__order_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_order_status_history__order_created_at ON public.order_status_history USING btree (order_id, created_at);


--
-- Name: ix_orders__assigned_master; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders__assigned_master ON public.orders USING btree (assigned_master_id);


--
-- Name: ix_orders__category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders__category ON public.orders USING btree (category);


--
-- Name: ix_orders__city_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders__city_id ON public.orders USING btree (city_id);


--
-- Name: ix_orders__city_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders__city_status ON public.orders USING btree (city_id, status);


--
-- Name: ix_orders__created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders__created_at ON public.orders USING btree (created_at);


--
-- Name: ix_orders__district_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders__district_id ON public.orders USING btree (district_id);


--
-- Name: ix_orders__guarantee_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders__guarantee_source ON public.orders USING btree (guarantee_source_order_id);


--
-- Name: ix_orders__phone; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders__phone ON public.orders USING btree (client_phone);


--
-- Name: ix_orders__preferred_master; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders__preferred_master ON public.orders USING btree (preferred_master_id);


--
-- Name: ix_orders__status_city; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders__status_city ON public.orders USING btree (status, city_id);


--
-- Name: ix_orders__status_city_timeslot_start; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders__status_city_timeslot_start ON public.orders USING btree (status, city_id, timeslot_start_utc);


--
-- Name: ix_orders__street_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders__street_id ON public.orders USING btree (street_id);


--
-- Name: ix_ref_rewards__referred; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ref_rewards__referred ON public.referral_rewards USING btree (referred_master_id);


--
-- Name: ix_ref_rewards__referrer_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ref_rewards__referrer_created ON public.referral_rewards USING btree (referrer_id, created_at);


--
-- Name: ix_ref_rewards__referrer_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ref_rewards__referrer_status ON public.referral_rewards USING btree (referrer_id, status);


--
-- Name: ix_referrals__master; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_referrals__master ON public.referrals USING btree (master_id);


--
-- Name: ix_referrals__referrer; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_referrals__referrer ON public.referrals USING btree (referrer_id);


--
-- Name: ix_staff_access_codes__code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_staff_access_codes__code ON public.staff_access_codes USING btree (code);


--
-- Name: ix_staff_access_codes__code_available; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_staff_access_codes__code_available ON public.staff_access_codes USING btree (code) WHERE ((used_by_staff_id IS NULL) AND (revoked_at IS NULL));


--
-- Name: ix_staff_cities__city_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_staff_cities__city_id ON public.staff_cities USING btree (city_id);


--
-- Name: ix_staff_cities__staff_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_staff_cities__staff_user_id ON public.staff_cities USING btree (staff_user_id);


--
-- Name: ix_staff_code_cities__city; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_staff_code_cities__city ON public.staff_access_code_cities USING btree (city_id);


--
-- Name: ix_staff_code_cities__code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_staff_code_cities__code ON public.staff_access_code_cities USING btree (access_code_id);


--
-- Name: ix_staff_users__tg_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_staff_users__tg_user_id ON public.staff_users USING btree (tg_user_id);


--
-- Name: ix_streets__city_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_streets__city_id ON public.streets USING btree (city_id);


--
-- Name: ix_streets__district_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_streets__district_id ON public.streets USING btree (district_id);


--
-- Name: uix_offers__order_accepted_once; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uix_offers__order_accepted_once ON public.offers USING btree (order_id) WHERE (state = 'ACCEPTED'::public.offer_state);


--
-- Name: admin_audit_log fk_admin_audit_log__admin_id__staff_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admin_audit_log
    ADD CONSTRAINT fk_admin_audit_log__admin_id__staff_users FOREIGN KEY (admin_id) REFERENCES public.staff_users(id) ON DELETE SET NULL;


--
-- Name: admin_audit_log fk_admin_audit_log__master_id__masters; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admin_audit_log
    ADD CONSTRAINT fk_admin_audit_log__master_id__masters FOREIGN KEY (master_id) REFERENCES public.masters(id) ON DELETE SET NULL;


--
-- Name: attachments fk_attachments__uploaded_by_master_id__masters; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attachments
    ADD CONSTRAINT fk_attachments__uploaded_by_master_id__masters FOREIGN KEY (uploaded_by_master_id) REFERENCES public.masters(id) ON DELETE SET NULL;


--
-- Name: attachments fk_attachments__uploaded_by_staff_id__staff_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attachments
    ADD CONSTRAINT fk_attachments__uploaded_by_staff_id__staff_users FOREIGN KEY (uploaded_by_staff_id) REFERENCES public.staff_users(id) ON DELETE SET NULL;


--
-- Name: commissions fk_commissions__master_id__masters; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commissions
    ADD CONSTRAINT fk_commissions__master_id__masters FOREIGN KEY (master_id) REFERENCES public.masters(id) ON DELETE CASCADE;


--
-- Name: commissions fk_commissions__order_id__orders; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commissions
    ADD CONSTRAINT fk_commissions__order_id__orders FOREIGN KEY (order_id) REFERENCES public.orders(id) ON DELETE CASCADE;


--
-- Name: districts fk_districts__city_id__cities; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.districts
    ADD CONSTRAINT fk_districts__city_id__cities FOREIGN KEY (city_id) REFERENCES public.cities(id) ON DELETE CASCADE;


--
-- Name: master_districts fk_master_districts__district_id__districts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.master_districts
    ADD CONSTRAINT fk_master_districts__district_id__districts FOREIGN KEY (district_id) REFERENCES public.districts(id) ON DELETE CASCADE;


--
-- Name: master_districts fk_master_districts__master_id__masters; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.master_districts
    ADD CONSTRAINT fk_master_districts__master_id__masters FOREIGN KEY (master_id) REFERENCES public.masters(id) ON DELETE CASCADE;


--
-- Name: master_invite_codes fk_master_invite_codes__city_id__cities; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.master_invite_codes
    ADD CONSTRAINT fk_master_invite_codes__city_id__cities FOREIGN KEY (city_id) REFERENCES public.cities(id) ON DELETE SET NULL;


--
-- Name: master_invite_codes fk_master_invite_codes__issued_by_staff_id__staff_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.master_invite_codes
    ADD CONSTRAINT fk_master_invite_codes__issued_by_staff_id__staff_users FOREIGN KEY (issued_by_staff_id) REFERENCES public.staff_users(id) ON DELETE SET NULL;


--
-- Name: master_invite_codes fk_master_invite_codes__used_by_master_id__masters; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.master_invite_codes
    ADD CONSTRAINT fk_master_invite_codes__used_by_master_id__masters FOREIGN KEY (used_by_master_id) REFERENCES public.masters(id) ON DELETE SET NULL;


--
-- Name: master_skills fk_master_skills__master_id__masters; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.master_skills
    ADD CONSTRAINT fk_master_skills__master_id__masters FOREIGN KEY (master_id) REFERENCES public.masters(id) ON DELETE CASCADE;


--
-- Name: master_skills fk_master_skills__skill_id__skills; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.master_skills
    ADD CONSTRAINT fk_master_skills__skill_id__skills FOREIGN KEY (skill_id) REFERENCES public.skills(id) ON DELETE CASCADE;


--
-- Name: masters fk_masters__city_id__cities; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.masters
    ADD CONSTRAINT fk_masters__city_id__cities FOREIGN KEY (city_id) REFERENCES public.cities(id) ON DELETE SET NULL;


--
-- Name: masters fk_masters__referred_by_master_id__masters; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.masters
    ADD CONSTRAINT fk_masters__referred_by_master_id__masters FOREIGN KEY (referred_by_master_id) REFERENCES public.masters(id) ON DELETE SET NULL;


--
-- Name: masters fk_masters__verified_by__staff_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.masters
    ADD CONSTRAINT fk_masters__verified_by__staff_users FOREIGN KEY (verified_by) REFERENCES public.staff_users(id) ON DELETE SET NULL;


--
-- Name: notifications_outbox fk_notifications_outbox__master_id__masters; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications_outbox
    ADD CONSTRAINT fk_notifications_outbox__master_id__masters FOREIGN KEY (master_id) REFERENCES public.masters(id) ON DELETE CASCADE;


--
-- Name: offers fk_offers__master_id__masters; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.offers
    ADD CONSTRAINT fk_offers__master_id__masters FOREIGN KEY (master_id) REFERENCES public.masters(id) ON DELETE CASCADE;


--
-- Name: offers fk_offers__order_id__orders; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.offers
    ADD CONSTRAINT fk_offers__order_id__orders FOREIGN KEY (order_id) REFERENCES public.orders(id) ON DELETE CASCADE;


--
-- Name: order_autoclose_queue fk_order_autoclose_queue__order_id__orders; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_autoclose_queue
    ADD CONSTRAINT fk_order_autoclose_queue__order_id__orders FOREIGN KEY (order_id) REFERENCES public.orders(id) ON DELETE CASCADE;


--
-- Name: order_status_history fk_order_status_history__changed_by_master_id__masters; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_status_history
    ADD CONSTRAINT fk_order_status_history__changed_by_master_id__masters FOREIGN KEY (changed_by_master_id) REFERENCES public.masters(id) ON DELETE SET NULL;


--
-- Name: order_status_history fk_order_status_history__changed_by_staff_id__staff_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_status_history
    ADD CONSTRAINT fk_order_status_history__changed_by_staff_id__staff_users FOREIGN KEY (changed_by_staff_id) REFERENCES public.staff_users(id) ON DELETE SET NULL;


--
-- Name: order_status_history fk_order_status_history__order_id__orders; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_status_history
    ADD CONSTRAINT fk_order_status_history__order_id__orders FOREIGN KEY (order_id) REFERENCES public.orders(id) ON DELETE CASCADE;


--
-- Name: orders fk_orders__assigned_master_id__masters; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT fk_orders__assigned_master_id__masters FOREIGN KEY (assigned_master_id) REFERENCES public.masters(id) ON DELETE SET NULL;


--
-- Name: orders fk_orders__city_id__cities; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT fk_orders__city_id__cities FOREIGN KEY (city_id) REFERENCES public.cities(id) ON DELETE RESTRICT;


--
-- Name: orders fk_orders__created_by_staff_id__staff_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT fk_orders__created_by_staff_id__staff_users FOREIGN KEY (created_by_staff_id) REFERENCES public.staff_users(id) ON DELETE SET NULL;


--
-- Name: orders fk_orders__district_id__districts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT fk_orders__district_id__districts FOREIGN KEY (district_id) REFERENCES public.districts(id) ON DELETE SET NULL;


--
-- Name: orders fk_orders__guarantee_source_order_id__orders; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT fk_orders__guarantee_source_order_id__orders FOREIGN KEY (guarantee_source_order_id) REFERENCES public.orders(id) ON DELETE SET NULL;


--
-- Name: orders fk_orders__preferred_master_id__masters; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT fk_orders__preferred_master_id__masters FOREIGN KEY (preferred_master_id) REFERENCES public.masters(id) ON DELETE SET NULL;


--
-- Name: orders fk_orders__street_id__streets; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT fk_orders__street_id__streets FOREIGN KEY (street_id) REFERENCES public.streets(id) ON DELETE SET NULL;


--
-- Name: referral_rewards fk_referral_rewards__commission_id__commissions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_rewards
    ADD CONSTRAINT fk_referral_rewards__commission_id__commissions FOREIGN KEY (commission_id) REFERENCES public.commissions(id) ON DELETE CASCADE;


--
-- Name: referral_rewards fk_referral_rewards__referred_master_id__masters; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_rewards
    ADD CONSTRAINT fk_referral_rewards__referred_master_id__masters FOREIGN KEY (referred_master_id) REFERENCES public.masters(id) ON DELETE CASCADE;


--
-- Name: referral_rewards fk_referral_rewards__referrer_id__masters; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_rewards
    ADD CONSTRAINT fk_referral_rewards__referrer_id__masters FOREIGN KEY (referrer_id) REFERENCES public.masters(id) ON DELETE CASCADE;


--
-- Name: referrals fk_referrals__master_id__masters; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referrals
    ADD CONSTRAINT fk_referrals__master_id__masters FOREIGN KEY (master_id) REFERENCES public.masters(id) ON DELETE CASCADE;


--
-- Name: referrals fk_referrals__referrer_id__masters; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referrals
    ADD CONSTRAINT fk_referrals__referrer_id__masters FOREIGN KEY (referrer_id) REFERENCES public.masters(id) ON DELETE CASCADE;


--
-- Name: staff_access_code_cities fk_staff_access_code_cities__access_code_id__staff_access_codes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_access_code_cities
    ADD CONSTRAINT fk_staff_access_code_cities__access_code_id__staff_access_codes FOREIGN KEY (access_code_id) REFERENCES public.staff_access_codes(id) ON DELETE CASCADE;


--
-- Name: staff_access_code_cities fk_staff_access_code_cities__city_id__cities; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_access_code_cities
    ADD CONSTRAINT fk_staff_access_code_cities__city_id__cities FOREIGN KEY (city_id) REFERENCES public.cities(id) ON DELETE CASCADE;


--
-- Name: staff_access_codes fk_staff_access_codes__city_id__cities; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_access_codes
    ADD CONSTRAINT fk_staff_access_codes__city_id__cities FOREIGN KEY (city_id) REFERENCES public.cities(id) ON DELETE SET NULL;


--
-- Name: staff_access_codes fk_staff_access_codes__issued_by_staff_id__staff_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_access_codes
    ADD CONSTRAINT fk_staff_access_codes__issued_by_staff_id__staff_users FOREIGN KEY (created_by_staff_id) REFERENCES public.staff_users(id) ON DELETE SET NULL;


--
-- Name: staff_access_codes fk_staff_access_codes__used_by_staff_id__staff_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_access_codes
    ADD CONSTRAINT fk_staff_access_codes__used_by_staff_id__staff_users FOREIGN KEY (used_by_staff_id) REFERENCES public.staff_users(id) ON DELETE SET NULL;


--
-- Name: staff_cities fk_staff_cities__city_id__cities; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_cities
    ADD CONSTRAINT fk_staff_cities__city_id__cities FOREIGN KEY (city_id) REFERENCES public.cities(id) ON DELETE CASCADE;


--
-- Name: staff_cities fk_staff_cities__staff_user_id__staff_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_cities
    ADD CONSTRAINT fk_staff_cities__staff_user_id__staff_users FOREIGN KEY (staff_user_id) REFERENCES public.staff_users(id) ON DELETE CASCADE;


--
-- Name: streets fk_streets__city_id__cities; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.streets
    ADD CONSTRAINT fk_streets__city_id__cities FOREIGN KEY (city_id) REFERENCES public.cities(id) ON DELETE CASCADE;


--
-- Name: streets fk_streets__district_id__districts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.streets
    ADD CONSTRAINT fk_streets__district_id__districts FOREIGN KEY (district_id) REFERENCES public.districts(id) ON DELETE SET NULL;


--
-- PostgreSQL database dump complete
--

\unrestrict Le803j56FvZjyZzC3lDJRhMrkNFKGLnBqunBuGfrZ1Tv9dgsMr5pvhGCIzLeeGq

