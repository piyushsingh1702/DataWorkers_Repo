# Example Inputs and Outputs

This folder contains worked examples that satisfy the hackathon constraint
of providing **at least 3 input examples and 3 output examples**.

Each input is a JSON request body sent to a `POST` endpoint on port 8000;
each output is the corresponding response payload that the platform
returns. Outputs were captured against the bundled mortgage sample dataset.

| # | Endpoint                                | Input file                           | Output file                          |
|---|-----------------------------------------|--------------------------------------|--------------------------------------|
| 1 | `POST /run`                             | `input_1_run.json`                   | `output_1_run.json`                  |
| 2 | `POST /api/v1/pipeline/run?...`         | `input_2_pipeline_run.json`          | `output_2_pipeline_run.json`         |
| 3 | `POST /api/v1/dq-scores/ask?...`        | `input_3_qa_ask.json`                | `output_3_qa_ask.json`               |

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
