-- The client's ERP, reduced to what accounts receivable needs. The world creates it; the platform's ERP
-- connector reads and writes it, the way a connector would read and write SAP FI-AR.
create table customers (kunnr text primary key, name text not null, city text, country text,
                        skonto_pct real not null default 0, skonto_days integer not null default 0,
                        net_days integer not null default 30, payer_kunnr text);
create table customer_ibans (kunnr text not null, iban text not null, primary key (kunnr, iban));
create table items (doc text primary key, kunnr text not null, kind text not null check (kind in ('invoice', 'credit')),
                    doc_date text not null, due text not null, skonto_until text, gross_cents integer not null,
                    po text, refers_to text, status text not null default 'open');
create table postings (id integer primary key, payment_id text not null, doc text, kind text not null
                         check (kind in ('clear', 'skonto', 'deduction', 'on_account')),
                       amount_cents integer not null, reason text, idem_key text not null unique,
                       posted_by text not null, posted_on text not null);
create table dunning (letter_id text primary key, kunnr text not null, docs text not null, level integer not null,
                      sent_on text not null);
create table dunning_blocks (doc text primary key, reason text not null, until text, note text);
