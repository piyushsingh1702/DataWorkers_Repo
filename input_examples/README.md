# Example Inputs and Outputs

This folder contains worked examples that satisfy the hackathon constraint
of providing **at least 3 input examples and 3 output examples**.

Each input is a JSON request body sent to a `POST` endpoint on port 8000;
each output is the corresponding response payload that the platform
returns. Outputs were captured against the bundled mortgage sample dataset.

### Original examples (db_name = `mortgage_demo`)

| #  | Endpoint                                          | Input file                              | Output file                              |
|----|---------------------------------------------------|-----------------------------------------|------------------------------------------|
| 1  | `POST /run`                                       | `input_1_run.json`                      | `output_1_run.json`                      |
| 2  | `POST /api/v1/pipeline/run?...`                   | `input_2_pipeline_run.json`             | `output_2_pipeline_run.json`             |
| 3  | `POST /api/v1/dq-scores/ask?...`                  | `input_3_qa_ask.json`                   | `output_3_qa_ask.json`                   |
| 4  | `GET  /api/v1/dq-scores/trend?...`                | _(query-only — no body)_                | `output_4_trend.json`                    |

### Full endpoint coverage (db_name = `loan1`, snapshot_date = `2025-01-01`)

For GET / query-only endpoints, the input file documents the URL query parameters
under an `_endpoint` / `_query` envelope (it is not a request body).

| #  | Endpoint                                          | Input file                                   | Output file                                  |
|----|---------------------------------------------------|----------------------------------------------|----------------------------------------------|
| 5  | `POST /api/v1/database/setup`                     | `input_5_database_setup.json`                | `output_5_database_setup.json`               |
| 6  | `GET  /api/v1/database/list`                      | `input_6_database_list.json`                 | `output_6_database_list.json`                |
| 7  | `GET  /api/v1/database/snapshots`                 | `input_7_database_snapshots.json`            | `output_7_database_snapshots.json`           |
| 8  | `POST /api/v1/connection/test?...`                | `input_8_connection_test.json`               | `output_8_connection_test.json`              |
| 9  | `POST /api/v1/discovery/run?...`                  | `input_9_discovery_run.json`                 | `output_9_discovery_run.json`                |
| 10 | `GET  /api/v1/discovery/results?...`              | `input_10_discovery_results.json`            | `output_10_discovery_results.json`           |
| 11 | `POST /api/v1/discovery/override`                 | `input_11_discovery_override.json`           | `output_11_discovery_override.json`          |
| 12 | `POST /api/v1/profiling/run?...`                  | `input_12_profiling_run.json`                | `output_12_profiling_run.json`               |
| 13 | `GET  /api/v1/profiling/results?...`              | `input_13_profiling_results.json`            | `output_13_profiling_results.json`           |
| 14 | `POST /api/v1/profiling/override`                 | `input_14_profiling_override.json`           | `output_14_profiling_override.json`          |
| 15 | `POST /api/v1/classification/run?...`             | `input_15_classification_run.json`           | `output_15_classification_run.json`          |
| 16 | `GET  /api/v1/classification/results?...`         | `input_16_classification_results.json`       | `output_16_classification_results.json`      |
| 17 | `POST /api/v1/classification/override`            | `input_17_classification_override.json`      | `output_17_classification_override.json`     |
| 18 | `POST /api/v1/dq-rules/generate?...`              | `input_18_dq_rules_generate.json`            | `output_18_dq_rules_generate.json`           |
| 19 | `GET  /api/v1/dq-rules/results?...`               | `input_19_dq_rules_results.json`             | `output_19_dq_rules_results.json`            |
| 20 | `POST /api/v1/dq-rules/override`                  | `input_20_dq_rules_override.json`            | `output_20_dq_rules_override.json`           |
| 21 | `GET  /api/v1/dq-scores/results?...`              | `input_21_dq_scores_results.json`            | `output_21_dq_scores_results.json`           |
| 22 | `GET  /api/v1/dq-scores/report?...` _(markdown)_  | `input_22_dq_scores_report.json`             | `output_22_dq_scores_report.md`              |
| 23 | `POST /api/v1/dq-scores/ask?...`                  | `input_23_dq_scores_ask.json`                | `output_23_dq_scores_ask.json`               |
| 24 | `GET  /api/v1/dq-scores/trend?...` _(2025-01 → 2025-04)_ | `input_24_dq_scores_trend.json`        | `output_24_dq_scores_trend.json`             |
| 25 | `POST /api/v1/pipeline/run?...`                   | `input_25_pipeline_run.json`                 | `output_25_pipeline_run.json`                |
| 26 | `GET  /api/v1/pipeline/status`                    | `input_26_pipeline_status.json`              | `output_26_pipeline_status.json`             |
| 27 | `POST /run`                                       | `input_27_run.json`                          | `output_27_run.json`                         |

To reproduce:

```bash
# 1. End-to-end run (loads data + executes pipeline)
curl -X POST http://localhost:8000/run \
     -H "Content-Type: application/json" \
     -d @examples/input_1_run.json

# 2. Pipeline against an explicit (db, snapshot)
curl -X POST "http://localhost:8000/api/v1/pipeline/run?db_name=mortgage_demo&snapshot_date=2025-01-01" \
     -H "Content-Type: application/json" \
     -d @examples/input_2_pipeline_run.json

# 3. Scoped Q&A
curl -X POST "http://localhost:8000/api/v1/dq-scores/ask?db_name=mortgage_demo&snapshot_date=2025-01-01" \
     -H "Content-Type: application/json" \
     -d @examples/input_3_qa_ask.json
```

A fourth bonus example covers the cross-snapshot trend endpoint:

```bash
curl "http://localhost:8000/api/v1/dq-scores/trend?db_name=mortgage_demo&snapshot_date_start=2025-01-01&snapshot_date_end=2025-04-01"
```

See `output_4_trend.json` for a representative response shape.
