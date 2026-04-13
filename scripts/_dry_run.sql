BEGIN;

CREATE TEMP TABLE _wcf_dry_raw (
  vivino_id INTEGER,
  nota_wcf NUMERIC(3,2),
  total_reviews_wcf INTEGER
);

\copy _wcf_dry_raw FROM 'C:/winegod-app/scripts/wcf_results_sample_1000.csv' WITH CSV HEADER

SELECT COUNT(*) AS carregadas FROM _wcf_dry_raw;

UPDATE wines w
SET nota_wcf = d.nota_wcf,
    confianca_nota = CASE
      WHEN d.total_reviews_wcf >= 100 THEN 1.0
      WHEN d.total_reviews_wcf >= 50 THEN 0.8
      WHEN d.total_reviews_wcf >= 25 THEN 0.6
      WHEN d.total_reviews_wcf >= 10 THEN 0.4
      ELSE 0.2
    END,
    winegod_score_type = CASE
      WHEN d.total_reviews_wcf >= 100 THEN 'verified'
      WHEN d.total_reviews_wcf >= 1 THEN 'estimated'
      ELSE 'none'
    END,
    nota_wcf_sample_size = d.total_reviews_wcf
FROM _wcf_dry_raw d
WHERE w.vivino_id = d.vivino_id;

SELECT COUNT(*) AS matched
FROM wines w
JOIN _wcf_dry_raw d ON d.vivino_id = w.vivino_id;

SELECT w.vivino_id, w.nota_wcf, w.vivino_rating,
       w.nota_wcf_sample_size, d.total_reviews_wcf,
       w.confianca_nota, w.winegod_score_type
FROM wines w
JOIN _wcf_dry_raw d ON d.vivino_id = w.vivino_id
ORDER BY w.nota_wcf_sample_size DESC NULLS LAST
LIMIT 10;

ROLLBACK;
