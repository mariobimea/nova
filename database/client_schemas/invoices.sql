-- Invoice Processing Table (Client Database)
--
-- This table lives in the CLIENT database (not NOVA database).
-- NOVA workflows write invoice data here after processing emails.
--
-- To create this table in Railway:
-- 1. Go to your client-db PostgreSQL service in Railway
-- 2. Click "Data" tab
-- 3. Open query console
-- 4. Copy-paste this SQL and execute

CREATE TABLE IF NOT EXISTS invoices (
    id SERIAL PRIMARY KEY,

    -- Email metadata
    email_from VARCHAR(255) NOT NULL,
    email_subject TEXT,
    email_date TIMESTAMP,

    -- PDF information
    pdf_filename VARCHAR(255),
    pdf_content BYTEA,  -- Binary PDF data
    pdf_size_bytes INTEGER,

    -- OCR results
    ocr_text TEXT,
    ocr_method VARCHAR(50),  -- 'pymupdf' or 'tesseract'

    -- Extracted data
    total_amount DECIMAL(10,2),
    currency VARCHAR(10) DEFAULT 'EUR',

    -- Processing metadata
    processed_by_workflow_id INTEGER,  -- Reference to NOVA workflow
    processed_by_execution_id INTEGER,  -- Reference to NOVA execution

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_invoices_email_from ON invoices(email_from);
CREATE INDEX IF NOT EXISTS idx_invoices_total_amount ON invoices(total_amount);
CREATE INDEX IF NOT EXISTS idx_invoices_created_at ON invoices(created_at);

-- Trigger to update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_invoices_updated_at BEFORE UPDATE ON invoices
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Example query: List all invoices over €1000
-- SELECT id, email_from, total_amount, created_at
-- FROM invoices
-- WHERE total_amount > 1000
-- ORDER BY created_at DESC;
