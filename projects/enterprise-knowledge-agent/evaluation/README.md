# RAG Evaluation

The evaluation set measures two deliberately simple, reproducible metrics:

- `Recall@K`: at least one retrieved chunk contains an expected term.
- `Answer Accuracy`: the generated answer contains all expected answer keywords.

Run it after the API is up and a knowledge base contains `samples/company_policy.txt`:

```bash
python scripts/evaluate_rag.py \
  --knowledge-base-id <knowledge-base-id> \
  --include-answers
```

The script prints per-question results and aggregate metrics. In a production system,
the expected answers should be reviewed by domain experts and extended with
faithfulness and citation correctness checks.
